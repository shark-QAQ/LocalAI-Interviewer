"""LLM 提供方设置接口：GET/PUT /llm/settings、POST /llm/test。

- 配置持久化在 data/llm_settings.json（见 llm_config），改完立即生效、无需重启。
- 任何响应都只回脱敏 key（has_key + tail），绝不回明文。
- POST /test 恒返回 200 + ok 布尔，方便前端直接展示绿/红条。
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..ollama_client import ollama_client
from ..llm_config import CLEAR_SENTINEL, get_llm_settings, public_view, save_llm_settings
from ..llm_client import test_deepseek

router = APIRouter(prefix="/llm", tags=["llm"])


class LlmSettingsBody(BaseModel):
    # None/缺省 = 保持不变；api_key 为空串=保持不变，"__clear__"=清除
    provider: str | None = None
    deepseek_model: str | None = None
    deepseek_base_url: str | None = None
    deepseek_api_key: str | None = None
    deepseek_disable_thinking: bool | None = None


class LlmTestBody(BaseModel):
    # 缺省 = 用当前保存配置；只是“试连快照”，不落盘
    provider: str | None = None
    deepseek_model: str | None = None
    deepseek_base_url: str | None = None
    deepseek_api_key: str | None = None


@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    return public_view()


@router.put("/settings")
async def update_settings(body: LlmSettingsBody) -> dict[str, Any]:
    cur = get_llm_settings().model_dump()
    merged = dict(cur)

    if body.provider is not None:
        if body.provider not in ("ollama", "deepseek"):
            raise HTTPException(status_code=400, detail="provider 只支持 ollama 或 deepseek")
        merged["provider"] = body.provider
    if body.deepseek_model is not None:
        merged["deepseek_model"] = body.deepseek_model.strip()
    if body.deepseek_base_url is not None:
        merged["deepseek_base_url"] = body.deepseek_base_url.strip()
    if body.deepseek_disable_thinking is not None:
        merged["deepseek_disable_thinking"] = body.deepseek_disable_thinking

    key = body.deepseek_api_key
    if key is not None:
        if key == CLEAR_SENTINEL:
            merged["deepseek_api_key"] = ""
        else:
            merged["deepseek_api_key"] = key.strip()

    # 切到 DeepSeek 但没 key：直接拦下，避免保存后才在生成时报错
    if merged["provider"] == "deepseek" and not (merged.get("deepseek_api_key") or "").strip():
        raise HTTPException(status_code=400, detail="切换到 DeepSeek 需要先填写 API Key")

    try:
        save_llm_settings(merged)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"保存设置失败：{e}")
    return public_view()


@router.post("/test")
async def test_connection(body: LlmTestBody) -> dict[str, Any]:
    base = get_llm_settings()
    provider = (body.provider or base.provider).strip().lower()
    start = time.perf_counter()

    if provider == "deepseek":
        key = body.deepseek_api_key
        if key is None:
            key = base.deepseek_api_key
        elif key == CLEAR_SENTINEL:
            key = ""
        else:
            key = key.strip()
        if not key:
            return {
                "ok": False,
                "provider": "deepseek",
                "model": body.deepseek_model or base.deepseek_model,
                "message": "尚未填写 DeepSeek API Key",
                "latency_ms": 0,
                "snippet": "",
            }
        return await test_deepseek(
            api_key=key,
            model=(body.deepseek_model or base.deepseek_model),
            base_url=(body.deepseek_base_url or base.deepseek_base_url),
        )

    # 本地 Ollama
    healthy = await ollama_client.health_check()
    models = await ollama_client.list_models() if healthy else []
    ready = await ollama_client.check_model(settings.llm_model) if healthy else False
    return {
        "ok": healthy and ready,
        "provider": "ollama",
        "model": settings.llm_model,
        "message": (
            f"Ollama 已连接 · {settings.llm_model} {'就绪' if ready else '未拉取'}"
            if healthy
            else f"无法连接 Ollama：{settings.ollama_host}"
        ),
        "latency_ms": int((time.perf_counter() - start) * 1000),
        "models": models,
        "snippet": "",
    }
