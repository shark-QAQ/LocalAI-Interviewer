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
    embedding_provider: str | None = None
    huggingface_model: str | None = None


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
    if body.embedding_provider is not None:
        if body.embedding_provider not in ("ollama", "huggingface"):
            raise HTTPException(status_code=400, detail="embedding_provider 只支持 ollama 或 huggingface")
        merged["embedding_provider"] = body.embedding_provider
    if body.huggingface_model is not None:
        merged["huggingface_model"] = body.huggingface_model.strip()

    key = body.deepseek_api_key
    if key is not None:
        if key == CLEAR_SENTINEL:
            merged["deepseek_api_key"] = ""
        else:
            merged["deepseek_api_key"] = key.strip()

    # 切到 DeepSeek 但没 key：直接拦下，避免保存后才在生成时报错
    if merged["provider"] == "deepseek" and not (merged.get("deepseek_api_key") or "").strip():
        raise HTTPException(status_code=400, detail="切换到 DeepSeek 需要先填写 API Key")

    # 切到 HuggingFace embedding 时强制重新加载模型
    old_embed_provider = cur.get("embedding_provider", "ollama")
    new_embed_provider = merged.get("embedding_provider", "ollama")

    try:
        save_llm_settings(merged)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"保存设置失败：{e}")

    # 如果嵌入提供方或模型变了，重置 HuggingFace 模型缓存
    if new_embed_provider == "huggingface" and (
        old_embed_provider != "huggingface" or
        cur.get("huggingface_model") != merged.get("huggingface_model")
    ):
        from .. import embed_client
        embed_client.reload_model()

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


@router.post("/test-embed")
async def test_embedding(body: LlmSettingsBody = None) -> dict[str, Any]:
    """测试嵌入后端连通性（Ollama / HuggingFace）。可传入当前页面选择的嵌入配置进行测试。"""
    from .. import embed_client
    from ..llm_config import LLMRuntimeSettings

    start = time.perf_counter()

    # 如果前端传了嵌入配置，临时覆盖进行测试
    embed_provider = None
    hf_model = None
    if body and body.embedding_provider:
        embed_provider = body.embedding_provider
    if body and body.huggingface_model:
        hf_model = body.huggingface_model

    try:
        # 临时覆盖嵌入配置用于测试
        if embed_provider:
            saved = get_llm_settings()
            fake = saved.model_copy(update={
                "embedding_provider": embed_provider,
                "huggingface_model": hf_model or saved.huggingface_model,
            })
            # 直接用 fake 配置构造嵌入路径
            import asyncio
            if embed_provider == "huggingface":
                model_name = hf_model or saved.huggingface_model
                try:
                    if embed_client._hf_model is None or hf_model:
                        embed_client._hf_model = None  # 强制重载
                        embed_client._hf_model = await asyncio.to_thread(embed_client._load_hf_model, model_name)
                    await asyncio.to_thread(embed_client._hf_model.encode, ["测试嵌入"], normalize_embeddings=True)
                    return {
                        "ok": True,
                        "provider": "huggingface",
                        "model": model_name,
                        "message": f"HuggingFace {model_name} 就绪",
                        "latency_ms": int((time.perf_counter() - start) * 1000),
                        "embed_test": True,
                    }
                except Exception as e:
                    return {
                        "ok": False,
                        "provider": "huggingface",
                        "model": model_name,
                        "message": f"HuggingFace 模型不可用: {e}",
                        "latency_ms": int((time.perf_counter() - start) * 1000),
                    }
            else:
                # Ollama
                healthy = await ollama_client.health_check()
                ready = await ollama_client.check_model(settings.embedding_model) if healthy else False
                return {
                    "ok": healthy and ready,
                    "provider": "ollama",
                    "model": settings.embedding_model,
                    "message": (
                        f"Ollama bge-m3 就绪" if ready
                        else f"Ollama 已连接但 {settings.embedding_model} 未拉取" if healthy
                        else f"无法连接 Ollama：{settings.ollama_host}"
                    ),
                    "latency_ms": int((time.perf_counter() - start) * 1000),
                }

        # 未传配置，用已保存的配置
        result = await embed_client.health_check()
        result["latency_ms"] = int((time.perf_counter() - start) * 1000)
        if result["ok"]:
            await embed_client.embed(["测试嵌入"])
            result["embed_test"] = True
        return result
    except Exception as e:
        return {
            "ok": False,
            "provider": embed_provider or get_llm_settings().embedding_provider,
            "message": f"嵌入测试失败: {e}",
            "latency_ms": int((time.perf_counter() - start) * 1000),
        }
