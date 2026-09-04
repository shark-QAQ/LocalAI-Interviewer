from __future__ import annotations

import json
import logging
from typing import Any

from ..config import settings
from ..database import generate_id, get_db, now_iso, row_to_dict
from ..ollama_client import ollama_client
from ..llm_client import llm_generate
from ..vector_store import vector_store

logger = logging.getLogger(__name__)

_CRAM_SYSTEM = """你是一位资深技术面试辅导专家。基于候选人的简历技能和项目代码库，生成针对性的八股文备考资料。

要求：
1. 每个技能点生成 3-5 个高频面试题，附带标准答案
2. 答案要结合候选人的项目代码（如果有相关代码片段）
3. 按技能分类，层次分明
4. 输出 Markdown 格式
"""


async def generate_cram_content(
    project_id: str,
    skills: list[str],
    focus_areas: list[str] | None = None,
) -> str:
    areas = focus_areas or skills[:8]

    rag_snippets: list[str] = []
    for area in areas[:5]:
        try:
            embeddings = await ollama_client.embed([area])
            if embeddings:
                results = vector_store.query(project_id, embeddings[0], n_results=2)
                if results and results.get("documents"):
                    docs = results["documents"][0] if results["documents"][0] else []
                    for d in docs[:2]:
                        rag_snippets.append(f"[{area}相关代码]\n{d}")
        except Exception:
            continue

    context = "\n\n---\n\n".join(rag_snippets) if rag_snippets else "（暂无项目代码片段）"

    prompt = f"""候选人技能栈：{', '.join(skills)}
需要重点复习的领域：{', '.join(areas)}

项目相关代码片段：
{context}

请为上述技能栈和重点领域，生成一份完整的八股文备考资料（Markdown格式）。
每个领域 3-5 个问题，每个问题附带详细答案。"""

    content = await llm_generate(
        prompt=prompt, system=_CRAM_SYSTEM, temperature=0.6
    )
    return content.strip()


def create_cram_task(project_id: str, resume_id: str | None = None, focus_areas: list[str] | None = None) -> str:
    task_id = generate_id()
    with get_db() as db:
        db.execute(
            """INSERT INTO cram_tasks (id, project_id, resume_id, focus_areas, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (
                task_id,
                project_id,
                resume_id,
                json.dumps(focus_areas, ensure_ascii=False) if focus_areas else None,
            ),
        )
    return task_id


def get_cram_task(task_id: str) -> dict[str, Any] | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM cram_tasks WHERE id = ?", (task_id,)).fetchone()
        return row_to_dict(row)


async def execute_cram_task(task_id: str) -> None:
    task = get_cram_task(task_id)
    if not task:
        return

    with get_db() as db:
        db.execute("UPDATE cram_tasks SET status = 'processing' WHERE id = ?", (task_id,))

    try:
        with get_db() as db:
            resume_row = db.execute(
                "SELECT skills FROM resumes WHERE id = ?", (task["resume_id"],)
            ).fetchone() if task.get("resume_id") else None

        skills = json.loads(resume_row["skills"]) if resume_row else []
        focus = json.loads(task["focus_areas"]) if task.get("focus_areas") else None

        content = await generate_cram_content(task["project_id"], skills, focus)

        with get_db() as db:
            db.execute(
                """UPDATE cram_tasks
                   SET status = 'completed', result_content = ?,
                       word_count = ?, completed_at = ?
                   WHERE id = ?""",
                (content, len(content), now_iso(), task_id),
            )
    except Exception as e:
        logger.exception("Cram task %s failed", task_id)
        with get_db() as db:
            db.execute(
                "UPDATE cram_tasks SET status = 'failed', error_msg = ? WHERE id = ?",
                (str(e), task_id),
            )
