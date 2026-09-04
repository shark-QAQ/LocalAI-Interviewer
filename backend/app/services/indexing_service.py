from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from ..config import settings
from ..database import generate_id, get_db, now_iso, row_to_dict
from .. import embed_client
from ..vector_store import vector_store

logger = logging.getLogger(__name__)


def _should_ignore(dir_name: str) -> bool:
    return dir_name in settings.ignored_dirs or dir_name.startswith(".")


def _scan_files(repo_path: Path) -> list[Path]:
    # 单个文件也支持：把它当作只含该文件的“项目”
    if repo_path.is_file():
        return [repo_path] if repo_path.suffix.lower() in settings.allowed_extensions else []
    files: list[Path] = []
    for item in repo_path.rglob("*"):
        if item.is_file():
            if any(part in settings.ignored_dirs or part.startswith(".") for part in item.parts):
                continue
            if item.suffix.lower() in settings.allowed_extensions:
                files.append(item)
    return files


def _read_file_safe(path: Path) -> str:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    return ""


def _detect_language(file_path: Path) -> str:
    ext_map = {
        ".java": "java", ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".go": "go", ".rs": "rust", ".c": "c", ".cpp": "cpp", ".h": "c",
        ".cs": "csharp", ".rb": "ruby", ".php": "php", ".kt": "kotlin",
        ".scala": "scala", ".md": "markdown", ".yaml": "yaml", ".yml": "yaml",
        ".sql": "sql",
    }
    return ext_map.get(file_path.suffix.lower(), "unknown")


def _extract_functions(content: str, lang: str) -> list[dict[str, Any]]:
    functions: list[dict[str, Any]] = []
    patterns = {
        "java": re.compile(
            r"(?:public|private|protected|static|final|synchronized|abstract|native)\s+"
            r"[\w<>\[\],\s]+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{",
            re.MULTILINE,
        ),
        "python": re.compile(r"def\s+(\w+)\s*\([^)]*\)\s*(?:->.*?)?:", re.MULTILINE),
        "javascript": re.compile(r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))", re.MULTILINE),
        "typescript": re.compile(r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*(?::\s*.*?)??\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))", re.MULTILINE),
        "go": re.compile(r"func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(", re.MULTILINE),
    }
    pattern = patterns.get(lang)
    if not pattern:
        return functions

    for m in pattern.finditer(content):
        name = m.group(1) or (m.group(2) if m.lastindex >= 2 else None)
        if name:
            line_num = content[:m.start()].count("\n") + 1
            functions.append({"name": name, "line": line_num})
    return functions


def _chunk_code(content: str, file_path: Path, lang: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    functions = _extract_functions(content, lang)

    if functions:
        lines = content.split("\n")
        for i, func in enumerate(functions):
            start = func["line"] - 1
            end = functions[i + 1]["line"] - 1 if i + 1 < len(functions) else len(lines)
            chunk_text = "\n".join(lines[start:end])
            if len(chunk_text) > 50:
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        "file_path": str(file_path),
                        "chunk_type": "code",
                        "function_name": func["name"],
                        "language": lang,
                        "start_line": start + 1,
                        "end_line": end,
                    },
                })
        return chunks if chunks else _fallback_chunks(content, file_path, lang)

    return _fallback_chunks(content, file_path, lang)


def _fallback_chunks(content: str, file_path: Path, lang: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    lines = content.split("\n")
    chunk_size = settings.chunk_size // 4
    overlap = settings.chunk_overlap // 4

    for i in range(0, len(lines), chunk_size - overlap):
        chunk_lines = lines[i:i + chunk_size]
        text = "\n".join(chunk_lines)
        if len(text.strip()) > 50:
            chunks.append({
                "text": text,
                "metadata": {
                    "file_path": str(file_path),
                    "chunk_type": "code",
                    "language": lang,
                    "start_line": i + 1,
                    "end_line": min(i + chunk_size, len(lines)),
                },
            })
    return chunks


def _detect_main_language(repo_path: Path) -> str:
    ext_count: dict[str, int] = {}
    candidates = [repo_path] if repo_path.is_file() else repo_path.rglob("*")
    for f in candidates:
        if f.is_file() and f.suffix.lower() in settings.allowed_extensions:
            ext_count[f.suffix.lower()] = ext_count.get(f.suffix.lower(), 0) + 1
    if not ext_count:
        return "unknown"
    top_ext = max(ext_count, key=ext_count.get)
    return _detect_language(Path(f"file{top_ext}"))


async def index_project(project_id: str, repo_path: str) -> dict[str, Any]:
    path = Path(repo_path)
    if path.is_dir():
        root = path
    elif path.is_file():
        if path.suffix.lower() not in settings.allowed_extensions:
            raise ValueError(f"不支持的文件类型: {repo_path}")
        root = path.parent
    else:
        raise ValueError(f"路径不存在: {repo_path}")

    with get_db() as db:
        db.execute(
            "UPDATE projects SET index_status = 'processing', index_started_at = ? WHERE id = ?",
            (now_iso(), project_id),
        )

    try:
        files = _scan_files(path)
        if not files:
            with get_db() as db:
                db.execute(
                    "UPDATE projects SET index_status = 'completed', chunk_count = 0, total_chunks = 0 WHERE id = ?",
                    (project_id,),
                )
            return {"project_id": project_id, "chunks": 0}

        all_chunks: list[dict[str, Any]] = []
        for file_path in files:
            content = _read_file_safe(file_path)
            if not content.strip():
                continue
            lang = _detect_language(file_path)
            relative = file_path.relative_to(root)
            chunks = _chunk_code(content, relative, lang)
            all_chunks.extend(chunks)

        total = len(all_chunks)
        with get_db() as db:
            db.execute("UPDATE projects SET total_chunks = ? WHERE id = ?", (total, project_id))

        if all_chunks:
            ids = [f"{project_id}_{i}" for i in range(len(all_chunks))]
            documents = [c["text"] for c in all_chunks]
            metadatas = [c["metadata"] for c in all_chunks]

            batch_size = 20
            for i in range(0, len(ids), batch_size):
                end = i + batch_size
                batch_docs = documents[i:end]
                embeddings_data = await embed_client.embed(batch_docs)
                vector_store.add_chunks(
                    project_id,
                    ids[i:end],
                    batch_docs,
                    embeddings_data,
                    metadatas[i:end],
                )
                with get_db() as db:
                    db.execute(
                        "UPDATE projects SET indexed_chunks = ? WHERE id = ?",
                        (min(end, total), project_id),
                    )

        lang = _detect_main_language(path)
        with get_db() as db:
            db.execute(
                """UPDATE projects
                   SET index_status = 'completed', chunk_count = ?,
                       last_indexed_at = ?, language = ?
                   WHERE id = ?""",
                (len(all_chunks), now_iso(), lang, project_id),
            )

        return {"project_id": project_id, "chunks": len(all_chunks)}

    except Exception as e:
        logger.exception("Indexing failed for project %s", project_id)
        with get_db() as db:
            db.execute(
                "UPDATE projects SET index_status = 'failed' WHERE id = ?",
                (project_id,),
            )
        raise


def create_project(name: str, repo_path: str) -> dict[str, Any]:
    path = Path(repo_path)
    if path.is_dir():
        pass
    elif path.is_file():
        if path.suffix.lower() not in settings.allowed_extensions:
            raise ValueError(f"不支持的文件类型: {repo_path}")
    else:
        raise ValueError(f"路径不存在: {repo_path}")

    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM projects WHERE repo_path = ?", (repo_path,)
        ).fetchone()
        if existing:
            return {"project_id": existing["id"], "status": "exists"}

        project_id = generate_id()
        db.execute(
            "INSERT INTO projects (id, name, repo_path) VALUES (?, ?, ?)",
            (project_id, name, repo_path),
        )
    return {"project_id": project_id, "status": "created"}


def get_project(project_id: str) -> dict[str, Any] | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return row_to_dict(row)


def list_projects() -> list[dict[str, Any]]:
    with get_db() as db:
        rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [row_to_dict(r) for r in rows]
