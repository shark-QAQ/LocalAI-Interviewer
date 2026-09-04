"""LLM 提供方的运行时配置（本地 Ollama ⇄ DeepSeek API）。

- 持久化位置：<项目根>/data/llm_settings.json（data/ 已 gitignore，删项目即干净）。
- 来源优先级（按"键"合并）：运行时 json 文件 > 环境变量 APP_* / Settings 默认。
  所以 env/.env 里配的 key 可被设置页覆盖，反之设置页保存的也立即生效。
- 保存即生效：get_llm_settings() 用 (mtime_ns, size) 做内存缓存，文件一变自动重读，无需重启后端。
- 安全：GET/PUT 一律只回脱敏 key（has_key + 尾4位），绝不回明文。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from pydantic import BaseModel

from .config import settings

logger = logging.getLogger(__name__)

_LLM_SETTINGS_PATH: Path = settings.data_dir / "llm_settings.json"

# 允许被设置页覆盖的键
_EDITABLE_FIELDS = {
    "provider",
    "deepseek_api_key",
    "deepseek_base_url",
    "deepseek_model",
    "deepseek_disable_thinking",
    "embedding_provider",
    "huggingface_model",
}

# PUT 语义哨兵：传 "__clear__" = 清除 api_key
CLEAR_SENTINEL = "__clear__"

_cache: tuple[tuple[int, int], "LLMRuntimeSettings"] | None = None


class LLMRuntimeSettings(BaseModel):
    provider: str = "ollama"                      # "ollama" | "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_max_tokens: int = 4096
    deepseek_disable_thinking: bool = True
    embedding_provider: str = "ollama"            # "ollama" | "huggingface"
    huggingface_model: str = "BAAI/bge-m3"
    source: str = "default"                       # "default" | "env" | "file"（诊断用）


def _from_settings() -> LLMRuntimeSettings:
    """从 Settings（含环境变量 APP_* 覆盖）构造基准快照。"""
    return LLMRuntimeSettings(
        provider=settings.llm_provider if settings.llm_provider in ("ollama", "deepseek") else "ollama",
        deepseek_api_key=settings.deepseek_api_key,
        deepseek_base_url=settings.deepseek_base_url or "https://api.deepseek.com",
        deepseek_model=settings.deepseek_model or "deepseek-v4-flash",
        deepseek_max_tokens=settings.deepseek_max_tokens or 4096,
        deepseek_disable_thinking=bool(settings.deepseek_disable_thinking),
        embedding_provider=getattr(settings, "embedding_provider", "ollama") or "ollama",
        huggingface_model=getattr(settings, "huggingface_model", "BAAI/bge-m3") or "BAAI/bge-m3",
    )


def _sig() -> tuple[int, int] | None:
    try:
        st = _LLM_SETTINGS_PATH.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def get_llm_settings() -> LLMRuntimeSettings:
    """取当前有效配置：文件(运行时) > env/Settings 默认。带 mtime 缓存，改文件即失效。"""
    global _cache
    sig = _sig()
    if _cache is not None and _cache[0] == sig:
        return _cache[1]

    base = _from_settings()
    if sig is not None:  # 存在运行时 json，按键覆盖
        try:
            raw = json.loads(_LLM_SETTINGS_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.warning("llm_settings.json 解析失败，回退 env/默认", exc_info=True)
            raw = {}
        updates = {k: v for k, v in raw.items() if k in _EDITABLE_FIELDS and v is not None}
        if updates:
            base = base.model_copy(update=updates)
            base.source = "file"
        elif _cache is None:
            base.source = "default"
    elif _cache is None:
        base.source = "default"

    # 规范化字段
    if base.provider not in ("ollama", "deepseek"):
        base.provider = "ollama"
    if base.embedding_provider not in ("ollama", "huggingface"):
        base.embedding_provider = "ollama"
    if not base.deepseek_base_url.strip():
        base.deepseek_base_url = "https://api.deepseek.com"
    if not base.deepseek_model.strip():
        base.deepseek_model = "deepseek-v4-flash"

    _cache = (sig, base)
    return base


def save_llm_settings(updates: dict) -> LLMRuntimeSettings:
    """把允许的键合并写入 json（原子写），返回最新有效配置。"""
    cur = get_llm_settings().model_dump()
    merged = dict(cur)
    for k, v in (updates or {}).items():
        if k not in _EDITABLE_FIELDS:
            continue
        if k == "provider" and v not in ("ollama", "deepseek"):
            raise ValueError("provider 只支持 ollama 或 deepseek")
        if k == "embedding_provider" and v not in ("ollama", "huggingface"):
            raise ValueError("embedding_provider 只支持 ollama 或 huggingface")
        if k == "deepseek_disable_thinking":
            merged[k] = bool(v) if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "on")
        else:
            merged[k] = str(v).strip() if k not in ("provider", "embedding_provider") else v
    merged.pop("source", None)

    payload = {k: merged[k] for k in _EDITABLE_FIELDS}
    _LLM_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _LLM_SETTINGS_PATH.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, _LLM_SETTINGS_PATH)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    return get_llm_settings()


def mask_key(key: str) -> dict:
    k = (key or "").strip()
    return {"has_key": bool(k), "tail": k[-4:] if k else ""}


def public_view(cfg: LLMRuntimeSettings | None = None) -> dict:
    """对外暴露的脱敏视图：绝不含明文 key。"""
    cfg = cfg or get_llm_settings()
    embed_model = cfg.huggingface_model if cfg.embedding_provider == "huggingface" else settings.embedding_model
    return {
        "provider": cfg.provider,
        "deepseek_model": cfg.deepseek_model,
        "deepseek_base_url": cfg.deepseek_base_url,
        "deepseek_disable_thinking": cfg.deepseek_disable_thinking,
        "deepseek_api_key": mask_key(cfg.deepseek_api_key),
        "embedding": {"provider": cfg.embedding_provider, "model": embed_model},
        "ollama_host": settings.ollama_host,
        "source": cfg.source,
    }
