from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self) -> None:
        self._base_url = settings.ollama_host
        self._llm_model = settings.llm_model
        self._embedding_model = settings.embedding_model
        self._timeout = settings.llm_timeout
        self._embed_timeout = settings.embed_timeout

    async def _request(self, method: str, path: str, timeout: float | None = None, **kwargs: Any) -> Any:
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=timeout or self._timeout) as client:
                resp = await client.request(method, url, **kwargs)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise RuntimeError(
                    f"Ollama API 404: {path} 不存在。请确认 Ollama 版本 >= 0.1.20 且模型已拉取。"
                    f"当前可用模型: {await self.list_models()}"
                )
            raise

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
        stream: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._llm_model,
            "prompt": prompt,
            "options": {"temperature": temperature},
            "stream": stream,
        }
        if system:
            payload["system"] = system

        # 说明：不再加全局锁。Ollama 服务端自带请求队列，
        # 去掉锁后 embed(bge-m3) 可与生成(qwen)并行，避免长生成阻塞其他请求。
        data = await self._request("POST", "/api/generate", json=payload)
        return data.get("response", "")

    async def generate_stream(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.7,
    ):
        payload: dict[str, Any] = {
            "model": self._llm_model,
            "prompt": prompt,
            "options": {"temperature": temperature},
            "stream": True,
        }
        if system:
            payload["system"] = system

        url = f"{self._base_url}/api/generate"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.strip():
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield token
                        if chunk.get("done"):
                            break

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self._embedding_model, "input": texts}
        data = await self._request("POST", "/api/embed", timeout=self._embed_timeout, json=payload)
        embeddings = data.get("embeddings", [])
        return embeddings

    async def health_check(self) -> bool:
        try:
            await self._request("GET", "/api/tags")
            return True
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        try:
            data = await self._request("GET", "/api/tags")
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    async def check_model(self, model: str) -> bool:
        models = await self.list_models()
        return any(model in m for m in models)


ollama_client = OllamaClient()
