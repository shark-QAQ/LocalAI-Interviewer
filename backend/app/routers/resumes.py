from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from ..services import resume_service
from ..services.resume_code_map import ensure_confident, project_status, set_decision
from ..database import get_db, row_to_dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.get("")
async def list_resumes() -> list[dict[str, Any]]:
    return resume_service.list_resumes()


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    candidate_name: str | None = Form(None),
    skip_vectorize: bool = Form(False),
    use_llm: bool = Form(False),
) -> dict[str, Any]:
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过10MB")

    header = content[:8]
    if not (header[:3] == b'%PDF' or header[:4] == b'PK\x03\x04'):
        raise HTTPException(status_code=400, detail="仅支持 PDF、DOCX 格式简历")

    try:
        result = await resume_service.upload_resume(
            content,
            file.filename or "unknown",
            skip_vectorize=skip_vectorize,
            use_llm=use_llm,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Resume upload failed")
        raise HTTPException(status_code=500, detail=f"简历解析失败: {e}")

    return result


class RenameRequest(BaseModel):
    name: str


@router.put("/{resume_id}/rename")
async def rename_resume(resume_id: str, req: RenameRequest) -> dict[str, Any]:
    if not resume_service.rename_resume(resume_id, req.name):
        raise HTTPException(status_code=404, detail="简历不存在")
    return {"ok": True}


@router.delete("/{resume_id}")
async def delete_resume(resume_id: str) -> dict[str, Any]:
    if not resume_service.delete_resume(resume_id):
        raise HTTPException(status_code=404, detail="简历不存在")
    return {"ok": True}


@router.get("/{resume_id}")
async def get_resume(resume_id: str) -> dict[str, Any]:
    resume = resume_service.get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    return resume


@router.get("/{resume_id}/code-mapping")
async def get_code_mapping(resume_id: str) -> dict[str, Any]:
    """简历项目 ↔ 代码库 映射状态：先自动落高置信项，再把拿不准的标成 pending 给前端确认。"""
    resume = resume_service.get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    projects = (resume.get("parsed_data") or {}).get("projects") or []

    with get_db() as db:
        code_repos = [
            row_to_dict(r)
            for r in db.execute(
                "SELECT id, name FROM projects WHERE index_status = 'completed' AND chunk_count > 0 ORDER BY created_at"
            ).fetchall()
        ]
    try:
        ensure_confident(projects, code_repos)
    except Exception:
        logger.exception("auto resume-code mapping failed")
    return {
        "projects": [{"name": p["name"], "status": project_status(p["name"])} for p in projects],
        "code_repos": [r["name"] for r in code_repos],
    }


class CodeMappingRequest(BaseModel):
    project_name: str
    code_repo: str | None = None


@router.post("/{resume_id}/code-mapping")
async def set_code_mapping(resume_id: str, req: CodeMappingRequest) -> dict[str, Any]:
    """手动确认某简历项目的映射（code_repo 为空即“无对应代码库”）。"""
    resume = resume_service.get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    if not req.project_name.strip():
        raise HTTPException(status_code=400, detail="项目名不能为空")
    repos = [req.code_repo] if (req.code_repo or "").strip() else []
    set_decision(req.project_name.strip(), repos)
    return {"ok": True, "status": "none" if not repos else "mapped"}
