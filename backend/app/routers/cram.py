from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import cram_service
from ..database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cram", tags=["cram"])


class CramGenerateRequest(BaseModel):
    project_id: str
    resume_id: str | None = None
    focus_areas: list[str] | None = None
    format: str = "markdown"


@router.post("/generate")
async def generate_cram(req: CramGenerateRequest) -> dict[str, Any]:
    with get_db() as db:
        project = db.execute(
            "SELECT id FROM projects WHERE id = ?", (req.project_id,)
        ).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")

    task_id = cram_service.create_cram_task(
        project_id=req.project_id,
        resume_id=req.resume_id,
        focus_areas=req.focus_areas,
    )

    asyncio.create_task(_run_cram_task(task_id))

    return {
        "task_id": task_id,
        "status": "generating",
        "estimated_seconds": 45,
    }


async def _run_cram_task(task_id: str) -> None:
    try:
        await cram_service.execute_cram_task(task_id)
    except Exception:
        logger.exception("Cram task %s failed", task_id)


@router.get("/tasks/{task_id}")
async def get_cram_task(task_id: str) -> dict[str, Any]:
    task = cram_service.get_cram_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "task_id": task["id"],
        "status": task["status"],
        "content": task.get("result_content"),
        "word_count": task.get("word_count"),
        "error_msg": task.get("error_msg"),
    }
