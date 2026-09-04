import pytest
from app.routers import llm as llm_router


def test_settings_get_default(client):
    r = client.get("/api/v1/llm/settings")
    assert r.status_code == 200
    assert r.json()["provider"] == "ollama"


def test_settings_put_and_mask(client):
    r = client.put("/api/v1/llm/settings", json={
        "provider": "deepseek", "deepseek_model": "deepseek-v4-flash",
        "deepseek_api_key": "sk-abc123456", "deepseek_disable_thinking": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "deepseek"
    assert body["deepseek_disable_thinking"] is False
    assert body["deepseek_api_key"] == {"has_key": True, "tail": "3456"}
    assert "sk-abc123456" not in str(r.content)


def test_settings_put_invalid(client):
    r = client.put("/api/v1/llm/settings", json={"provider": "wat"})
    assert r.status_code == 400


def test_settings_deepseek_without_key_rejected(client):
    r = client.put("/api/v1/llm/settings", json={"provider": "deepseek"})
    assert r.status_code == 400


def test_settings_clear_key(client):
    # 先回 ollama 再清 key（deepseek 状态下清 key 会被校验拦下）
    client.put("/api/v1/llm/settings", json={"provider": "deepseek", "deepseek_api_key": "sk-hello0000"})
    r = client.put("/api/v1/llm/settings", json={"provider": "ollama", "deepseek_api_key": "__clear__"})
    assert r.json()["deepseek_api_key"] == {"has_key": False, "tail": ""}
    # deepseek 且无 key -> 400
    r = client.put("/api/v1/llm/settings", json={"provider": "deepseek"})
    assert r.status_code == 400


def test_test_ollama(client, monkeypatch):
    async def healthy():
        return True
    async def models():
        return ["bge-m3:latest", "qwen2.5:7b"]
    async def check(m):
        return True
    monkeypatch.setattr(llm_router.ollama_client, "health_check", healthy)
    monkeypatch.setattr(llm_router.ollama_client, "list_models", models)
    monkeypatch.setattr(llm_router.ollama_client, "check_model", check)
    r = client.post("/api/v1/llm/test", json={"provider": "ollama"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_test_deepseek_without_key(client):
    r = client.post("/api/v1/llm/test", json={"provider": "deepseek"})
    assert r.json()["ok"] is False
    assert "API Key" in r.json()["message"]


def test_test_deepseek_mock(client, monkeypatch):
    async def fake_test(api_key, model=None, base_url=None, max_tokens=16):
        return {"ok": True, "provider": "deepseek", "model": model or "deepseek-v4-flash",
                "message": "连接成功", "latency_ms": 5, "snippet": "pong"}
    monkeypatch.setattr(llm_router, "test_deepseek", fake_test)
    r = client.post("/api/v1/llm/test", json={"provider": "deepseek", "deepseek_api_key": "sk-x"})
    assert r.json()["ok"] is True
