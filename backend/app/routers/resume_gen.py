"""简历生成接口：上传模板 → AI 对话收集 → 生成/下载 docx。

门禁：仅 DeepSeek(API) 可用（与 MBTI 一致）；纯文件持久化，无数据库。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from ..config import settings
from ..llm_config import get_llm_settings
from ..services import resume_gen

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/resume-gen", tags=["resume-gen"])

_GATE_MSG = (
    "简历生成需要 DeepSeek API 保证生成质量。当前为本地模型，请先到「设置」"
    "把文本生成提供方切到 DeepSeek 后再试。"
)

EXAMPLE_PATH = settings.data_dir / "resume_templates" / "_example.docx"


def _require_api() -> None:
    if get_llm_settings().provider != "deepseek":
        raise HTTPException(status_code=403, detail=_GATE_MSG)


class ChatBody(BaseModel):
    message: str


class SessionCreateBody(BaseModel):
    # 二选一：template_id（旧模板/占位模板） 或 template_key（内置模板）
    template_id: str | None = None
    template_key: str | None = None
    resume_id: str | None = None


@router.get("/example-template")
async def example_template():
    _require_api()
    try:
        if not EXAMPLE_PATH.exists():
            resume_gen.build_example_template(EXAMPLE_PATH)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"示例模板生成失败：{e}")
    return FileResponse(
        str(EXAMPLE_PATH),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="简历模板-示例.docx",
    )


@router.post("/example-template/to-desktop")
async def example_template_to_desktop() -> dict[str, Any]:
    """把示例模板直接另存到系统桌面，供“点一下下载到桌面”的反馈。"""
    _require_api()
    try:
        if not EXAMPLE_PATH.exists():
            resume_gen.build_example_template(EXAMPLE_PATH)
        desktop = resume_gen.save_to_desktop(EXAMPLE_PATH, "简历模板-示例.docx")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"示例模板生成失败：{e}")
    if not desktop:
        raise HTTPException(status_code=500, detail="无法保存到桌面（可能是关闭了该功能或桌面不可写）")
    return {"desktop": desktop}


@router.get("/templates")
async def list_templates() -> dict[str, Any]:
    return {"templates": [
        {"key": k, "name": m["name"], "accent": m["accent"], "desc": m["desc"]}
        for k, m in resume_gen.BUILTIN_TEMPLATES.items()
    ]}


@router.get("/templates/{key}/preview", response_class=HTMLResponse)
async def preview_template(key: str) -> HTMLResponse:
    if key not in resume_gen.BUILTIN_TEMPLATES:
        raise HTTPException(status_code=404, detail="模板不存在")
    sample = {
        "姓名": "张凯", "求职意向": "AI 大模型应用工程师",
        "电话": "138-0000-0000", "邮箱": "zk@example.com", "城市": "上海",
        "个人简介": "五年后端与 AI 应用经验，聚焦 RAG 与大模型工程化。",
        "技能": "Python / FastAPI / RAG / LangGraph / Docker",
        "工作经历": "高级后端工程师 · 负责 AI 研判平台架构与工具链接入",
        "项目经历": "安全运营平台 · 特征工程 + 规则兜底 + LangGraph 工作流",
        "教育经历": "某大学 计算机科学与技术 · 本科",
    }
    return HTMLResponse(resume_gen.render_resume_html(key, sample))


@router.post("/upload-template")
async def upload_template(file: UploadFile = File(...)) -> dict[str, Any]:
    _require_api()
    name = file.filename or "template.docx"
    ext = (name.rsplit(".", 1)[-1] if "." in name else "").lower()
    if ext not in ("docx", "doc"):
        raise HTTPException(status_code=400, detail="仅支持 .docx / .doc 简历或模板")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 20MB")
    if not (data.startswith(b"PK\x03\x04") or data.startswith(b"\xd0\xcf\x11\xe0")):
        raise HTTPException(status_code=400, detail="文件不是有效的 Word 文档（.docx/.doc）")
    try:
        # 老式 .doc：本机装有 Word 时自动转为 .docx
        if ext == "doc":
            conv = resume_gen.convert_doc_to_docx_bytes(data)
            if not conv:
                raise ValueError("这是老式 .doc 且本机未安装/无法调用 Word 转换，请先用 Word 另存为 .docx 再上传")
            data = conv
            name = name.rsplit(".", 1)[0] + ".docx"

        placeholders = resume_gen.scan_doc_fields_bytes(data)
        if placeholders:
            return resume_gen.register_template(name, data, placeholders, "placeholder")

        # 统一内置专业模板出稿：上传文件仅作内容参考，不依赖其版式
        info = resume_gen.register_template(name, data, list(resume_gen.BUILTIN_FIELDS), "builtin")
        return info
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"模板处理失败：{e}")


@router.post("/sessions")
async def create_session(body: SessionCreateBody) -> dict[str, Any]:
    _require_api()
    if body.template_key:
        try:
            template_id = resume_gen.ensure_builtin_template(body.template_key)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    elif body.template_id:
        template_id = body.template_id
    else:
        raise HTTPException(status_code=400, detail="请提供 template_id 或 template_key")
    try:
        session = resume_gen.create_session(template_id, body.resume_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    tpl = resume_gen.get_template(template_id) or {}
    fields = tpl.get("fields") or []
    session["template_key"] = (tpl or {}).get("builtin_key") or body.template_key
    resume_gen._save_session(session)
    return {
        "session_id": session["session_id"],
        "template_key": session["template_key"],
        "fields": session["fields"],
        "missing": fields,
        "done": False,
        "question": (
            "你好，我先了解下基本情况——"
            f"请先告诉我你的姓名与求职意向（如不确定可略过，说“继续”我会接着问）。"
        ),
    }


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatBody) -> dict[str, Any]:
    _require_api()
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    try:
        return await resume_gen.chat(session_id, body.message.strip())
    except ValueError as e:
        raise HTTPException(status_code=404 if "不存在" in str(e) else 400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.warning("resume-gen chat failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI 会话出错：{e}")


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    session = resume_gen.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    tpl = resume_gen.get_template(session["template_id"]) or {}
    fields = tpl.get("fields") or []
    return {
        "session_id": session_id,
        "fields": session.get("fields") or {},
        "missing": resume_gen._missing(fields, session.get("fields") or {}),
        "status": session.get("status"),
        "done": session.get("status") == "ready",
    }


@router.get("/sessions/{session_id}/photo")
async def get_photo(session_id: str):
    session = resume_gen.get_session(session_id)
    photo = (session or {}).get("photo_file")
    if not session or not photo:
        raise HTTPException(status_code=404, detail="未上传照片")
    path = resume_gen.GEN_DIR / photo
    if not path.exists():
        raise HTTPException(status_code=404, detail="照片文件缺失")
    return FileResponse(str(path))


@router.get("/sessions/{session_id}/preview", response_class=HTMLResponse)
async def preview_session(session_id: str) -> HTMLResponse:
    """整份简历的 HTML 预览（真内容 + 已传照片），浏览器可直接打印/另存为 PDF。"""
    session = resume_gen.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    key = session.get("template_key") or "classic"
    if key not in resume_gen.BUILTIN_TEMPLATES:
        key = "classic"
    photo_src = f"/api/v1/resume-gen/sessions/{session_id}/photo" if session.get("photo_file") else ""
    html = resume_gen.render_resume_html(key, session.get("fields") or {}, photo_src)
    return HTMLResponse(html)


@router.post("/sessions/{session_id}/photo")
async def upload_photo(session_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    _require_api()
    session = resume_gen.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in ("png", "jpg", "jpeg", "webp"):
        raise HTTPException(status_code=400, detail="仅支持 png/jpg/webp 照片")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="照片不能超过 8MB")
    photo_name = f"{session_id}.photo.{ext}"
    (resume_gen.GEN_DIR / photo_name).write_bytes(data)
    session["photo_file"] = photo_name
    resume_gen._save_session(session)
    return {"ok": True, "photo": photo_name}


@router.post("/sessions/{session_id}/generate")
async def generate(session_id: str) -> dict[str, Any]:
    _require_api()
    try:
        result = resume_gen.generate_docx(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 默认同时另存一份到系统桌面，让用户“直接拿到”简历
    from pathlib import Path
    result["desktop"] = resume_gen.save_to_desktop(Path(result["path"]), result["file_name"])
    return result


@router.get("/sessions/{session_id}/download")
async def download(session_id: str) -> FileResponse:
    session = resume_gen.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    path = resume_gen.GEN_DIR / f"{session_id}.docx"
    if not path.exists():
        raise HTTPException(status_code=404, detail="尚未生成，请先生成简历")
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=session.get("file_name") or "简历.docx",
    )
