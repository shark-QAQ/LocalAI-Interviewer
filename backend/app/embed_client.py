"""统一嵌入客户端：支持 Ollama 和 HuggingFace (sentence-transformers) 两种后端。

- 运行时通过 llm_config 的 embedding_provider 字段切换。
- HuggingFace 模式使用 sentence-transformers 加载模型，首次加载较慢，后续从缓存读取。
- Ollama 模式复用原有 /api/embed 接口。
- 所有调用方（indexing_service, resume_service 等）统一使用本模块的 embed() 函数。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_hf_model = None  # lazy-loaded SentenceTransformer instance


def _get_embedding_provider() -> str:
    try:
        from .llm_config import get_llm_settings
        return get_llm_settings().embedding_provider
    except Exception:
        return "ollama"


def _get_hf_model_name() -> str:
    try:
        from .llm_config import get_llm_settings
        return get_llm_settings().huggingface_model
    except Exception:
        return "BAAI/bge-m3"


async def embed(texts: list[str]) -> list[list[float]]:
    """统一嵌入接口，根据 embedding_provider 自动路由。"""
    provider = _get_embedding_provider()
    if provider == "huggingface":
        return await _embed_huggingface(texts)
    return await _embed_ollama(texts)


async def _embed_ollama(texts: list[str]) -> list[list[float]]:
    """通过 Ollama /api/embed 生成嵌入向量。"""
    model = settings.embedding_model
    url = f"{settings.ollama_host}/api/embed"
    payload = {"model": model, "input": texts}
    timeout = settings.embed_timeout
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    embeddings = data.get("embeddings", [])
    if not embeddings:
        logger.warning("Ollama embed 返回空结果，model=%s, input_len=%d", model, len(texts))
    return embeddings


async def _embed_huggingface(texts: list[str]) -> list[list[float]]:
    """通过本地 HuggingFace sentence-transformers 模型生成嵌入向量。"""
    global _hf_model
    import asyncio
    import functools

    model_name = _get_hf_model_name()

    if _hf_model is None:
        logger.info("Loading HuggingFace embedding model: %s (首次加载较慢)...", model_name)
        try:
            _hf_model = await asyncio.to_thread(_load_hf_model, model_name)
            logger.info("HuggingFace embedding model loaded: %s", model_name)
        except Exception:
            logger.exception("Failed to load HuggingFace embedding model: %s", model_name)
            raise

    try:
        result = await asyncio.to_thread(_hf_model.encode, texts, normalize_embeddings=True)
        embeddings = [vec.tolist() for vec in result]
        return embeddings
    except Exception:
        logger.exception("HuggingFace embedding failed, model=%s", model_name)
        raise


def _load_hf_model(model_name: str):
    """在线程中加载 sentence-transformers 模型。"""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name, trust_remote_code=True)


async def health_check() -> dict[str, Any]:
    """检测当前嵌入后端是否可用。"""
    provider = _get_embedding_provider()
    if provider == "huggingface":
        return await _health_huggingface()
    return await _health_ollama()


async def _health_ollama() -> dict[str, Any]:
    try:
        url = f"{settings.ollama_host}/api/tags"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return {"ok": True, "provider": "ollama", "message": "Ollama 可连接"}
    except Exception as e:
        return {"ok": False, "provider": "ollama", "message": f"Ollama 不可达: {e}"}


async def _health_huggingface() -> dict[str, Any]:
    global _hf_model
    import asyncio

    model_name = _get_hf_model_name()
    try:
        if _hf_model is None:
            _hf_model = await asyncio.to_thread(_load_hf_model, model_name)
        # quick encode test
        await asyncio.to_thread(_hf_model.encode, ["test"], normalize_embeddings=True)
        return {"ok": True, "provider": "huggingface", "model": model_name, "message": f"HuggingFace {model_name} 就绪"}
    except Exception as e:
        return {"ok": False, "provider": "huggingface", "model": model_name, "message": f"HuggingFace 模型不可用: {e}"}


def reload_model() -> None:
    """强制重新加载 HuggingFace 模型（切换模型后调用）。"""
    global _hf_model
    _hf_model = None
