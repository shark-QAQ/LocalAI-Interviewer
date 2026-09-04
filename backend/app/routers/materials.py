from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import material_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("")
async def list_materials() -> list[dict[str, Any]]:
    return material_service.list_materials()


class ImportPathRequest(BaseModel):
    path: str
    name: str = ""


@router.post("/import")
async def import_material(req: ImportPathRequest) -> dict[str, Any]:
    """按本地路径导入：文件夹自动吸收其中的全部资料文件；单个文件则只导入该文件。"""
    try:
        return await material_service.import_path(req.name, req.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Material import failed")
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")


class RenameRequest(BaseModel):
    name: str


@router.put("/{material_id}/rename")
async def rename_material(material_id: str, req: RenameRequest) -> dict[str, bool]:
    if not material_service.rename_material(material_id, req.name):
        raise HTTPException(status_code=404, detail="资料不存在")
    return {"ok": True}


@router.delete("/{material_id}")
async def delete_material(material_id: str) -> dict[str, bool]:
    if not material_service.delete_material(material_id):
        raise HTTPException(status_code=404, detail="资料不存在")
    return {"ok": True}
