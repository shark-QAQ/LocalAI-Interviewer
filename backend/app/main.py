from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .ollama_client import ollama_client
from .config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Initializing database...")
    init_db()

    from .llm_config import get_llm_settings
    llm_cfg = get_llm_settings()
    embed_provider = llm_cfg.embedding_provider

    logger.info("Embedding provider: %s", embed_provider)
    if embed_provider == "ollama":
        logger.info("Checking Ollama connection for embeddings...")
        healthy = await ollama_client.health_check()
        if healthy:
            logger.info("Ollama connected successfully")
            models = await ollama_client.list_models()
            logger.info("Available models: %s", models)
            if not await ollama_client.check_model(settings.embedding_model):
                logger.warning("Embedding model '%s' not found! Run: ollama pull %s", settings.embedding_model, settings.embedding_model)
            if llm_cfg.provider == "ollama" and not await ollama_client.check_model(settings.llm_model):
                logger.warning("LLM model '%s' not found! Run: ollama pull %s", settings.llm_model, settings.llm_model)
        else:
            logger.warning("Ollama not reachable at %s - 向量嵌入不可用；文本生成按提供方配置决定", settings.ollama_host)
    else:
        logger.info("Embedding via HuggingFace: %s", llm_cfg.huggingface_model)
        try:
            from . import embed_client
            result = await embed_client.health_check()
            if result["ok"]:
                logger.info("HuggingFace embedding model ready: %s", llm_cfg.huggingface_model)
            else:
                logger.warning("HuggingFace embedding model not ready: %s", result.get("message", "unknown error"))
        except Exception as e:
            logger.warning("HuggingFace embedding init failed: %s", e)

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title=settings.project_name,
    description="本地化智能面试官 - 基于本地代码库+简历动态生成八股文并模拟真实技术面试",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .routers import projects, resumes, materials, interviews, cram, llm, mbti, resume_gen  # noqa: E402

app.include_router(projects.router, prefix=settings.api_prefix)
app.include_router(resumes.router, prefix=settings.api_prefix)
app.include_router(materials.router, prefix=settings.api_prefix)
app.include_router(interviews.router, prefix=settings.api_prefix)
app.include_router(cram.router, prefix=settings.api_prefix)
app.include_router(llm.router, prefix=settings.api_prefix)
app.include_router(mbti.router, prefix=settings.api_prefix)
app.include_router(resume_gen.router, prefix=settings.api_prefix)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/diagnose")
async def diagnose() -> dict[str, Any]:
    from .config import settings
    from .ollama_client import ollama_client as oc
    from .llm_config import get_llm_settings
    from . import embed_client
    cfg = get_llm_settings()
    healthy = await oc.health_check()
    models = await oc.list_models() if healthy else []
    embed_health = await embed_client.health_check()
    return {
        "ollama_host": settings.ollama_host,
        "ollama_healthy": healthy,
        "available_models": models,
        # 嵌入提供方
        "embedding_provider": cfg.embedding_provider,
        "embedding_model": cfg.huggingface_model if cfg.embedding_provider == "huggingface" else settings.embedding_model,
        "embedding_model_ready": embed_health.get("ok", False),
        # 文本生成提供方
        "llm_provider": cfg.provider,
        "ollama_llm_model": settings.llm_model,
        "ollama_llm_model_ready": await oc.check_model(settings.llm_model) if healthy else False,
        "deepseek_model": cfg.deepseek_model,
        "deepseek_key_set": bool((cfg.deepseek_api_key or "").strip()),
    }


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.project_name,
        "docs": "/docs",
        "health": "/health",
    }
