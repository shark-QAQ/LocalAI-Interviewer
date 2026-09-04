"""文本生成提供方调度：本地 Ollama ⇄ DeepSeek API。

- `llm_generate` / `llm_generate_stream`：按运行时配置分发。embedding 不在这里，一律走本地 ollama_client.embed。
- DeepSeek 走 OpenAI 兼容 `/chat/completions`；默认模型 deepseek-v4-flash，可在设置页自定义。
- 配置实时读取（见 llm_config.get_llm_settings），切提供方不需要重启。
- 失败不自动静默回退：DeepSeek 出错直接抛友好 RuntimeError，由上层 SSE error / 任务失败承接。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from .config import settings
from .ollama_client import ollama_client
from .llm_config import LLMRuntimeSettings, get_llm_settings

logger = logging.getLogger(__name__)


def _deepseek_err(status: int, body: str) -> str:
    body_snip = " ".join((body or "").split())[:300]
    if status == 401:
        return "DeepSeek API Key 无效或未授权 (401)"
    if status == 402:
        return "DeepSeek 账户余额不足或欠费 (402)"
    if status == 429:
        return "DeepSeek 请求过于频繁或额度不足 (429)"
    return f"DeepSeek 返回 {status}: {body_snip or '（无响应体）'}"


def _deepseek_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }


def _deepseek_messages(system: str, prompt: str) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    if system and system.strip():
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    return msgs


async def _deepseek_generate(
    cfg: LLMRuntimeSettings,
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str:
    key = (cfg.deepseek_api_key or "").strip()
    if not key:
        raise RuntimeError("DeepSeek API Key 未配置：请先在「设置」页填写")
    url = cfg.deepseek_base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg.deepseek_model,
        "messages": _deepseek_messages(system, prompt),
        "temperature": max(0.0, min(2.0, float(temperature))),
        "max_tokens": max_tokens or cfg.deepseek_max_tokens or 4096,
        "stream": False,
    }
    if cfg.deepseek_disable_thinking:
        payload["thinking"] = {"type": "disabled"}
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
            resp = await client.post(url, json=payload, headers=_deepseek_headers(key))
    except httpx.ConnectError:
        raise RuntimeError(f"无法连接 DeepSeek：{cfg.deepseek_base_url}（检查网络/地址）")
    except httpx.TimeoutException:
        raise RuntimeError(f"DeepSeek 请求超时（>{settings.llm_timeout:.0f}s）：{cfg.deepseek_base_url}")
    except httpx.HTTPError as e:
        raise RuntimeError(f"DeepSeek 请求失败：{e}")

    if resp.status_code != 200:
        raise RuntimeError(_deepseek_err(resp.status_code, resp.text[:400]))
    try:
        obj = resp.json()
        content = obj["choices"][0]["message"]["content"]
        return str(content or "").strip()
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError(f"DeepSeek 返回格式异常：{resp.text[:200]}")


async def _deepseek_stream(
    cfg: LLMRuntimeSettings,
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
):
    key = (cfg.deepseek_api_key or "").strip()
    if not key:
        raise RuntimeError("DeepSeek API Key 未配置：请先在「设置」页填写")
    url = cfg.deepseek_base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": cfg.deepseek_model,
        "messages": _deepseek_messages(system, prompt),
        "temperature": max(0.0, min(2.0, float(temperature))),
        "max_tokens": cfg.deepseek_max_tokens or 4096,
        "stream": True,
    }
    if cfg.deepseek_disable_thinking:
        payload["thinking"] = {"type": "disabled"}
    async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
        try:
            async with client.stream(
                "POST", url, json=payload, headers=_deepseek_headers(key)
            ) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "ignore")[:400]
                    raise RuntimeError(_deepseek_err(resp.status_code, body))
                async for line in resp.aiter_lines():
                    line = (line or "").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for ch in obj.get("choices") or []:
                        delta = ch.get("delta") or {}
                        tok = delta.get("content")
                        if tok:
                            yield tok
        except httpx.ConnectError:
            raise RuntimeError(f"无法连接 DeepSeek：{cfg.deepseek_base_url}（检查网络/地址）")
        except httpx.TimeoutException:
            raise RuntimeError(f"DeepSeek 请求超时（>{settings.llm_timeout:.0f}s）：{cfg.deepseek_base_url}")


async def llm_generate(
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
) -> str:
    """文本生成统一入口：按当前配置分发到 DeepSeek 或本地 Ollama。"""
    cfg = get_llm_settings()
    if cfg.provider == "deepseek":
        logger.debug("llm dispatch provider=deepseek model=%s", cfg.deepseek_model)
        return await _deepseek_generate(cfg, prompt, system, temperature)
    logger.debug("llm dispatch provider=ollama model=%s", settings.llm_model)
    return await ollama_client.generate(prompt=prompt, system=system, temperature=temperature)


async def llm_generate_stream(
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
):
    """流式文本生成统一入口；每 token yield 一次 str，语义与 Ollama 流一致。"""
    cfg = get_llm_settings()
    if cfg.provider == "deepseek":
        logger.debug("llm stream dispatch provider=deepseek model=%s", cfg.deepseek_model)
        async for tok in _deepseek_stream(cfg, prompt, system, temperature):
            yield tok
    else:
        logger.debug("llm stream dispatch provider=ollama model=%s", settings.llm_model)
        async for tok in ollama_client.generate_stream(
            prompt=prompt, system=system, temperature=temperature
        ):
            yield tok


async def test_deepseek(
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 16,
) -> dict:
    """连通性试连（POST /llm/test 用；只做一次最小调用，不落盘）。恒返回 {ok,...}。"""
    base = get_llm_settings()
    cfg = base.model_copy(
        update={
            "provider": "deepseek",
            "deepseek_api_key": api_key.strip(),
            "deepseek_model": (model or base.deepseek_model).strip() or base.deepseek_model,
            "deepseek_base_url": (base_url or base.deepseek_base_url).strip() or base.deepseek_base_url,
        }
    )
    start = time.perf_counter()
    try:
        content = await _deepseek_generate(cfg, "ping", system="", temperature=0.0, max_tokens=max_tokens)
        return {
            "ok": True,
            "provider": "deepseek",
            "model": cfg.deepseek_model,
            "message": "连接成功",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "snippet": (content or "")[:200],
        }
    except RuntimeError as e:
        return {
            "ok": False,
            "provider": "deepseek",
            "model": cfg.deepseek_model,
            "message": str(e),
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "snippet": "",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "provider": "deepseek",
            "model": cfg.deepseek_model,
            "message": f"DeepSeek 测试失败：{e}",
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "snippet": "",
        }
