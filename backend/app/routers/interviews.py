from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..services import interviewer
from ..services.scope import CAT_LABELS
from ..database import get_db, row_to_dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/interviews", tags=["interviews"])


class SessionCreateRequest(BaseModel):
    resume_id: str
    project_id: str
    target_position: str = ""
    max_rounds: int = 8
    difficulty: str = "mid"
    # 提问侧重（深挖/均衡/广度，一条轴），决定各类别出题占比
    focus: str = "balanced"
    # 勾选的多个代码库（用于综合出题）；缺省只用 project_id
    project_ids: list[str] = []


class InteractRequest(BaseModel):
    user_answer: str | None = None


@router.post("/sessions")
async def create_session(req: SessionCreateRequest) -> dict[str, Any]:
    try:
        session_id = await interviewer.start_interview(
            resume_id=req.resume_id,
            project_id=req.project_id,
            project_ids=req.project_ids,
            target_position=req.target_position,
            max_rounds=req.max_rounds,
            difficulty=req.difficulty,
            focus=req.focus,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "session_id": session_id,
        "status": "waiting_for_question",
        "initial_question": None,
    }


@router.post("/sessions/{session_id}/interact")
async def interact(session_id: str, req: InteractRequest) -> StreamingResponse:
    session = interviewer.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    if session["status"] in ("terminated", "reported"):
        async def done_events():
            yield _sse_event("done", {"final": True, "reason": "面试已结束"})
        return StreamingResponse(done_events(), media_type="text/event-stream")

    with get_db() as db:
        resume_row = db.execute(
            "SELECT skills FROM resumes WHERE id = ?", (session["resume_id"],)
        ).fetchone()
    skills = json.loads(resume_row["skills"]) if resume_row else []

    if req.user_answer is None or req.user_answer.strip() == "":
        async def first_question():
            yield _sse_event("thinking", {"message": "正在分析你的简历和代码库..."})

            question_text = ""
            try:
                async for token in interviewer.generate_greeting(
                    session_id, skills, interviewer.get_session_messages(session_id)
                ):
                    question_text += token
                    yield _sse_event("token", {"content": token})

                with get_db() as db:
                    db.execute(
                        "UPDATE interview_sessions SET status = 'questioning' WHERE id = ?",
                        (session_id,),
                    )
                    db.execute(
                        """INSERT INTO messages (session_id, round_num, role, content, score_json)
                           VALUES (?, 0, 'assistant', ?, NULL)""",
                        (session_id, question_text),
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning("greeting generation failed: %s", e)
                yield _sse_event("error", {"message": str(e)})
                return

            yield _sse_event("greeting", {"content": question_text})
        return StreamingResponse(first_question(), media_type="text/event-stream")

    async def stream_interact():
        yield _sse_event("thinking", {"message": "正在分析你的回答并构思下一题..."})

        try:
            # 单次模型调用同时产出“本条回答评分 + 下一题”，降低延迟
            result = await interviewer.generate_turn(session_id, req.user_answer, skills)
        except Exception as e:
            yield _sse_event("error", {"message": str(e)})
            return

        ev = result["evaluation"]
        if result["is_intro"]:
            # 自我介绍阶段：独立的“自我介绍点评”（表达/内容/匹配），而非代码技术评分
            if ev.get("avg") is not None:
                yield _sse_event("intro_eval", {
                    "score": ev["avg"],
                    "comment": ev["comment"],
                    "dimensions": {
                        "clarity": ev.get("clarity"),
                        "substance": ev.get("substance"),
                        "fit": ev.get("fit"),
                    },
                })
        else:
            yield _sse_event("evaluation", {
                "round": result["answered_round"],
                "score": ev["avg"],
                "comment": ev["comment"],
                "dimensions": {
                    "depth": ev["depth"],
                    "logic": ev["logic"],
                    "integrity": ev["integrity"],
                },
            })

        if result["is_last"]:
            yield _sse_event("done", {"final": True, "reason": "已达最大轮次"})
            return

        # 题目已在 generate_turn 内完成清洗，这里仅按 token 片段回传
        question_text = result.get("question_text") or ""
        sources = result.get("sources") or []
        for i in range(0, len(question_text), 4):
            yield _sse_event("token", {"content": question_text[i : i + 4]})

        with get_db() as db:
            # 随题记录“该题考察类别/技能 + 引用来源”，供后续评分对齐、调度与参考答案追溯
            meta: dict[str, Any] = {
                "sources": sources,
                "skill": result.get("skill") or "",
                "cat": result.get("cat") or "",
            }
            score_json = json.dumps(meta, ensure_ascii=False) if (sources or meta["skill"] or meta["cat"]) else None
            db.execute(
                """INSERT INTO messages (session_id, round_num, role, content, score_json)
                   VALUES (?, ?, 'assistant', ?, ?)""",
                (session_id, result["next_round"], question_text, score_json),
            )

        # 参考答案预生成保留，但“错峰”：延迟 2 秒再后台生成，避免刚出完题就与下一轮争抢本地模型
        async def _delayed_prewarm(sid: str, rnd: int) -> None:
            await asyncio.sleep(2)
            try:
                interviewer.prewarm_reference(sid, rnd)
            except Exception:
                logger.debug("delayed prewarm failed for %s round %s", sid, rnd)

        asyncio.create_task(_delayed_prewarm(session_id, result["next_round"]))

        yield _sse_event("question", {
            "round": result["next_round"],
            "content": question_text,
            "skill": result.get("skill") or "",
            "cat": result.get("cat") or "",
            "cat_label": CAT_LABELS.get(result.get("cat") or "", ""),
            "sources": sources,
        })

    return StreamingResponse(stream_interact(), media_type="text/event-stream")


@router.get("/sessions/{session_id}/report")
async def get_report(session_id: str) -> dict[str, Any]:
    try:
        report = await interviewer.get_report(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return report


class KBSearchRequest(BaseModel):
    query: str
    n_results: int = 8


@router.post("/sessions/{session_id}/kb-search")
async def search_session_kb(session_id: str, req: KBSearchRequest) -> dict[str, Any]:
    """综合检索本场面试的全部知识来源（多项目 + 简历 + 资料），
    并把命中结果归一化为自然语言说明一并返回。"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="查询内容不能为空")
    results = await interviewer.search_session_kb(
        session_id, req.query.strip(), req.n_results
    )
    summary = await interviewer.summarize_knowledge(req.query.strip(), results)
    return {"session_id": session_id, "results": results, "summary": summary}


class ReferenceRequest(BaseModel):
    round: int


@router.post("/sessions/{session_id}/reference")
async def get_reference(session_id: str, req: ReferenceRequest) -> dict[str, Any]:
    """按需为某一轮题目生成高质量标准参考答案（前端点击“查看答案”时调用）。"""
    if req.round <= 0:
        raise HTTPException(status_code=400, detail="题号不合法")
    try:
        ref = await interviewer.generate_reference(session_id, req.round)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"round": req.round, "reference": ref}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session = interviewer.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.get("/sessions")
async def list_sessions() -> list[dict[str, Any]]:
    """最近若干场面试（含进行中/已完成），供品鉴历史列表与续面。"""
    with get_db() as db:
        rows = db.execute(
            """SELECT s.id, s.resume_id, r.candidate_name AS resume_name,
                      s.difficulty, s.focus, s.max_rounds, s.current_round,
                      s.status, s.started_at, s.ended_at
               FROM interview_sessions s
               LEFT JOIN resumes r ON r.id = s.resume_id
               ORDER BY COALESCE(s.ended_at, s.started_at) DESC
               LIMIT 10"""
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = row_to_dict(r)
        d["completed"] = d.get("status") in ("terminated", "reported")
        out.append(d)
    return out


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, Any]:
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM interview_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        db.execute("DELETE FROM interview_sessions WHERE id = ?", (session_id,))
    try:
        interviewer._forget_session(session_id)
    except Exception:
        pass
    return {"ok": True}


@router.get("/sessions/{session_id}/messages")
async def get_session_messages_route(session_id: str) -> list[dict[str, Any]]:
    """拉取某场面试的完整消息（用于“继续面试”时重建聊天界面）。"""
    if not interviewer.get_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = interviewer.get_session_messages(session_id)
    out: list[dict[str, Any]] = []
    for m in msgs:
        meta: dict[str, Any] = {}
        if m.get("score_json"):
            try:
                meta = json.loads(m["score_json"])
            except Exception:
                meta = {}
        out.append({
            "round_num": m["round_num"],
            "role": m["role"],
            "content": m["content"],
            "type": meta.get("type"),
            "cat": meta.get("cat"),
            "skill": meta.get("skill"),
            "sources": meta.get("sources") or [],
            "reference": meta.get("reference") or "",  # 已生成的参考答案（持久化在库里）
            "eval": {k: meta.get(k) for k in ("depth", "logic", "integrity", "clarity", "substance", "fit", "avg") if k in meta},
        })
    return out


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
