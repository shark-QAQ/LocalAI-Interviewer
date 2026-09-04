import json
import pytest
from app.llm_config import (
    CLEAR_SENTINEL,
    _LLM_SETTINGS_PATH,
    get_llm_settings,
    mask_key,
    public_view,
    save_llm_settings,
)


def test_default_is_ollama_without_file():
    cfg = get_llm_settings()
    assert cfg.provider == "ollama"
    v = public_view(cfg)
    assert v["provider"] == "ollama"
    assert v["deepseek_api_key"] == {"has_key": False, "tail": ""}
    assert v["embedding"]["provider"] == "ollama"


def test_save_persists_and_reflects(enable_api):  # noqa: ARG001
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": "sk-abcdef1234", "deepseek_model": "deepseek-v4-flash"})
    cfg = get_llm_settings()
    assert cfg.provider == "deepseek"
    assert cfg.deepseek_model == "deepseek-v4-flash"
    assert cfg.deepseek_api_key == "sk-abcdef1234"
    assert _LLM_SETTINGS_PATH.exists()
    raw = json.loads(_LLM_SETTINGS_PATH.read_text(encoding="utf-8"))
    assert raw["deepseek_api_key"] == "sk-abcdef1234"


def test_public_view_masks_key(enable_api):  # noqa: ARG001
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": "sk-abcdef1234"})
    v = public_view()
    assert v["deepseek_api_key"] == {"has_key": True, "tail": "1234"}
    # 明文不得出现在对外视图里
    assert "sk-abcdef1234" not in json.dumps(v, ensure_ascii=False)


def test_save_partial_and_sentinel_is_opaque_in_config():
    # llm_config 不做 __clear__ 语义（那是 router 层）；只做“按键更新”
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": "sk-hello9999"})
    save_llm_settings({"deepseek_model": "other-model"})
    cfg = get_llm_settings()
    assert cfg.deepseek_model == "other-model"
    assert cfg.deepseek_api_key == "sk-hello9999"  # 未传 api_key 保持
    save_llm_settings({"deepseek_api_key": CLEAR_SENTINEL})
    assert get_llm_settings().deepseek_api_key == CLEAR_SENTINEL  # 原样存储，由 router 解释


def test_save_invalid_provider():
    with pytest.raises(ValueError):
        save_llm_settings({"provider": "openai"})


def test_mask_key_edge():
    assert mask_key("") == {"has_key": False, "tail": ""}
    assert mask_key(None) == {"has_key": False, "tail": ""}
    assert mask_key("sk-x") == {"has_key": True, "tail": "sk-x"}


def test_env_default_model_is_deepseek_v4_flash():
    cfg = get_llm_settings()
    assert cfg.deepseek_model == "deepseek-v4-flash"
    assert cfg.deepseek_base_url == "https://api.deepseek.com"
    assert cfg.deepseek_disable_thinking is True


def test_thinking_flag_roundtrip(enable_api):  # noqa: ARG001
    assert public_view()["deepseek_disable_thinking"] is True
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": "sk-x", "deepseek_disable_thinking": False})
    assert get_llm_settings().deepseek_disable_thinking is False
    assert public_view()["deepseek_disable_thinking"] is False
    save_llm_settings({"deepseek_disable_thinking": True})
    assert get_llm_settings().deepseek_disable_thinking is True
