from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ..services import indexing_service, resume_service, interviewer
from ..database import get_db, row_to_dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectInitRequest(BaseModel):
    project_name: str
    code_path: str
    force_rebuild: bool = False


class ProjectInitResponse(BaseModel):
    project_id: str
    status: str
    total_chunks: int = 0
    estimated_time: int = 30


@router.post("/init", response_model=ProjectInitResponse)
async def init_project(req: ProjectInitRequest) -> ProjectInitResponse:
    try:
        result = indexing_service.create_project(req.project_name, req.code_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    project_id = result["project_id"]

    if req.force_rebuild:
        from ..vector_store import vector_store
        vector_store.delete_collection(project_id)
        with get_db() as db:
            db.execute(
                "UPDATE projects SET index_status = 'idle', chunk_count = 0 WHERE id = ?",
                (project_id,),
            )

    asyncio.create_task(_run_indexing(project_id, req.code_path))

    return ProjectInitResponse(
        project_id=project_id,
        status="indexing",
        total_chunks=0,
        estimated_time=30,
    )


async def _run_indexing(project_id: str, code_path: str) -> None:
    try:
        await indexing_service.index_project(project_id, code_path)
    except Exception:
        logger.exception("Background indexing failed for %s", project_id)


@router.get("/{project_id}/status")
async def get_project_status(project_id: str) -> dict[str, Any]:
    project = indexing_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {
        "project_id": project["id"],
        "index_status": project["index_status"],
        "chunk_count": project["chunk_count"],
        "indexed_chunks": project.get("indexed_chunks", 0),
        "total_chunks": project.get("total_chunks", 0),
        "index_started_at": project.get("index_started_at"),
        "last_indexed_at": project["last_indexed_at"],
    }


@router.get("")
async def list_projects() -> list[dict[str, Any]]:
    return indexing_service.list_projects()


@router.get("/list-dirs")
async def list_dirs(path: str = "", files: bool = False, exts: str = "") -> dict[str, Any]:
    """列出指定路径下的子目录（可选附带可导入的文件），用于前端文件夹/文件浏览。

    files=True 时把当前目录内（非隐藏的）普通文件一并返回；
    exts 为逗号分隔的小写扩展名（如 ".py,.md"），提供时只返回这些类型的文件。
    """
    allowed_exts = {e.strip().lower() for e in exts.split(",") if e.strip()} if exts else set()

    if not path:
        import string
        disks = []
        for letter in string.ascii_uppercase:
            p = Path(f"{letter}:\\")
            if p.exists():
                disks.append({"name": f"{letter}:", "path": str(p)})
        return {"parent": "", "dirs": disks, "files": []}

    target = Path(path)
    if not target.exists():
        raise HTTPException(status_code=400, detail="路径不存在")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="不是目录")

    parent = str(target.parent) if str(target.parent) != str(target) else ""
    dirs: list[dict[str, str]] = []
    file_list: list[dict[str, str]] = []
    try:
        for item in sorted(target.iterdir()):
            if item.is_dir():
                if item.name.startswith(".") or item.name in (
                    "__pycache__", "node_modules", ".git", ".venv", "venv", "dist", "build",
                ):
                    continue
                dirs.append({"name": item.name, "path": str(item)})
            elif files and item.is_file() and not item.name.startswith("."):
                if allowed_exts and item.suffix.lower() not in allowed_exts:
                    continue
                file_list.append({"name": item.name, "path": str(item)})
    except PermissionError:
        raise HTTPException(status_code=403, detail="无权限访问该目录")

    return {"parent": parent, "dirs": dirs, "files": file_list}


class RenameRequest(BaseModel):
    name: str


class SearchRequest(BaseModel):
    query: str
    n_results: int = 5


@router.post("/{project_id}/search")
async def search_project(project_id: str, req: SearchRequest) -> dict[str, Any]:
    """在指定项目的向量库中检索与查询相关的代码片段"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="查询内容不能为空")

    project = indexing_service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    from ..vector_store import vector_store
    from ..ollama_client import ollama_client

    try:
        embeddings = await ollama_client.embed([req.query.strip()])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"向量化失败: {e}")
    if not embeddings:
        raise HTTPException(status_code=500, detail="向量化无返回结果")

    try:
        data = vector_store.query(project_id, embeddings[0], n_results=req.n_results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索失败: {e}")

    docs = (data.get("documents") or [[]])[0] or []
    metas = (data.get("metadatas") or [[]])[0] or []
    distances = (data.get("distances") or [[]])[0] or []

    results = []
    for i, text in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        results.append({
            "text": str(text),
            "file_path": meta.get("file_path", ""),
            "chunk_type": meta.get("chunk_type", "code"),
            "function_name": meta.get("function_name", ""),
            "language": meta.get("language", ""),
            "start_line": meta.get("start_line"),
            "end_line": meta.get("end_line"),
            "distance": round(distances[i], 4) if i < len(distances) else None,
        })

    return {"project_id": project_id, "results": results}


@router.put("/{project_id}/rename")
async def rename_project(project_id: str, req: RenameRequest) -> dict[str, Any]:
    with get_db() as db:
        db.execute("UPDATE projects SET name = ? WHERE id = ?", (req.name, project_id))
        if db.total_changes == 0:
            raise HTTPException(status_code=404, detail="项目不存在")
    return {"ok": True}


@router.delete("/{project_id}")
async def delete_project(project_id: str) -> dict[str, Any]:
    from ..vector_store import vector_store
    vector_store.delete_collection(project_id)
    with get_db() as db:
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        if db.total_changes == 0:
            raise HTTPException(status_code=404, detail="项目不存在")
    return {"ok": True}
