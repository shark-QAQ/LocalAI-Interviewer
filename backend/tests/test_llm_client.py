import pytest
from app import llm_client
from app.llm_config import save_llm_settings


@pytest.mark.asyncio
async def test_llm_generate_deepseek_dispatch(monkeypatch, enable_api):  # noqa: ARG001
    async def fake_gen(cfg, prompt, system="", temperature=0.7, max_tokens=None):
        assert cfg.provider == "deepseek"
        return f"deep-{prompt}"
    monkeypatch.setattr(llm_client, "_deepseek_generate", fake_gen)
    assert await llm_client.llm_generate("hi", system="sys") == "deep-hi"


@pytest.mark.asyncio
async def test_llm_generate_ollama_dispatch(monkeypatch):
    async def fake_gen(prompt, system="", temperature=0.7, stream=False):
        assert system == "sys"
        return f"oll-{prompt}"
    monkeypatch.setattr(llm_client.ollama_client, "generate", fake_gen)
    assert await llm_client.llm_generate("hi", system="sys") == "oll-hi"


@pytest.mark.asyncio
async def test_llm_generate_stream_deepseek(monkeypatch, enable_api):  # noqa: ARG001
    async def fake_stream(cfg, prompt, system="", temperature=0.7):
        yield "a"
        yield "b"
    monkeypatch.setattr(llm_client, "_deepseek_stream", fake_stream)
    assert [t async for t in llm_client.llm_generate_stream("q")] == ["a", "b"]


@pytest.mark.asyncio
async def test_llm_generate_stream_ollama(monkeypatch):
    async def fake_stream(prompt, system="", temperature=0.7):
        yield "x"
    monkeypatch.setattr(llm_client.ollama_client, "generate_stream", fake_stream)
    assert [t async for t in llm_client.llm_generate_stream("q")] == ["x"]


@pytest.mark.asyncio
async def test_deepseek_generate_missing_key(monkeypatch):
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": ""})
    with pytest.raises(RuntimeError, match="API Key 未配置"):
        await llm_client._deepseek_generate(llm_client.get_llm_settings(), "p")


class _FakeHTTPXClient:
    def __init__(self, resp):
        self._resp = resp
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def post(self, url, json=None, headers=None):
        return self._resp


class _Resp:
    def __init__(self, status_code: int, text: str, payload):
        self.status_code = status_code
        self.text = text
        self._payload = payload
    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_deepseek_generate_key_error_mapping(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda timeout=None: _FakeHTTPXClient(_Resp(401, '{"error":"bad"}', {"error": "bad"})))
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": "sk-x"})
    with pytest.raises(RuntimeError, match="401"):
        await llm_client._deepseek_generate(llm_client.get_llm_settings(), "p")


@pytest.mark.asyncio
async def test_deepseek_generate_parse_success(monkeypatch):
    import httpx
    ok = {"choices": [{"message": {"content": "hi"}}]}
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda timeout=None: _FakeHTTPXClient(_Resp(200, "ok", ok)))
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": "sk-x"})
    assert await llm_client._deepseek_generate(llm_client.get_llm_settings(), "p") == "hi"


@pytest.mark.asyncio
async def test_deepseek_generate_bad_shape_raises(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda timeout=None: _FakeHTTPXClient(_Resp(200, "bad", {"choices": []})))
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": "sk-x"})
    with pytest.raises(RuntimeError, match="格式异常"):
        await llm_client._deepseek_generate(llm_client.get_llm_settings(), "p")


@pytest.mark.asyncio
async def test_test_deepseek_ok_and_error(monkeypatch, enable_api):  # noqa: ARG001
    async def ok_gen(cfg, prompt, system="", temperature=0.7, max_tokens=None):
        return "pong"
    monkeypatch.setattr(llm_client, "_deepseek_generate", ok_gen)
    r = await llm_client.test_deepseek("sk-ok")
    assert r["ok"] is True and r["snippet"] == "pong"

    async def bad_gen(*a, **k):
        raise RuntimeError("DeepSeek API Key 无效或未授权 (401)")
    monkeypatch.setattr(llm_client, "_deepseek_generate", bad_gen)
    r = await llm_client.test_deepseek("sk-bad")
    assert r["ok"] is False and "401" in r["message"]


def test_deepseek_err_mapping():
    assert "401" in llm_client._deepseek_err(401, "x")
    assert "402" in llm_client._deepseek_err(402, "x")
    assert "429" in llm_client._deepseek_err(429, "x")
    assert "500" in llm_client._deepseek_err(500, "boom")
    assert "boom" in llm_client._deepseek_err(500, "boom")


class _ErrClient:
    def __init__(self, exc):
        self._exc = exc
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def post(self, url, json=None, headers=None):
        raise self._exc
    def stream(self, method, url, json=None, headers=None):
        return _ErrStream(self._exc)


class _ErrStream:
    def __init__(self, exc):
        self._exc = exc
    async def __aenter__(self):
        raise self._exc
    async def __aexit__(self, *a):
        return False


@pytest.mark.asyncio
async def test_generate_connect_and_timeout_errors(monkeypatch):
    import httpx
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": "sk-x"})
    cfg = llm_client.get_llm_settings()
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: _ErrClient(httpx.ConnectError("refused")))
    with pytest.raises(RuntimeError, match="无法连接"):
        await llm_client._deepseek_generate(cfg, "p")
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: _ErrClient(httpx.TimeoutException("slow")))
    with pytest.raises(RuntimeError, match="超时"):
        await llm_client._deepseek_generate(cfg, "p")


@pytest.mark.asyncio
async def test_stream_connect_and_timeout_errors(monkeypatch):
    import httpx
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": "sk-x"})
    cfg = llm_client.get_llm_settings()
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: _ErrClient(httpx.ConnectError("refused")))
    with pytest.raises(RuntimeError, match="无法连接"):
        _ = [t async for t in llm_client._deepseek_stream(cfg, "p")]
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout=None: _ErrClient(httpx.TimeoutException("slow")))
    with pytest.raises(RuntimeError, match="超时"):
        _ = [t async for t in llm_client._deepseek_stream(cfg, "p")]
