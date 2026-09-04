"""测试公共夹具。

- 把 APP_DATA_DIR 指向临时目录，让整个应用（db、llm_settings、模板/简历产物）都写进临时区，
  绝不污染真实 data/。
- 每个用例结束后删除 llm_settings.json，恢复默认 ollama。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("APP_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="localai_test_"))))
os.environ.setdefault("APP_RESUME_SAVE_DESKTOP", "0")  # 测试不写真实桌面


def _cleanup_llm_settings() -> None:
    try:
        from app.llm_config import _LLM_SETTINGS_PATH
        if _LLM_SETTINGS_PATH.exists():
            _LLM_SETTINGS_PATH.unlink()
    except Exception:
        pass


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    import shutil
    data = os.environ.get("APP_DATA_DIR")
    if data:
        shutil.rmtree(data, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)  # noqa: F821
def _init_db():
    from app.database import init_db
    init_db()
    yield


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_provider():
    yield
    _cleanup_llm_settings()


@pytest.fixture
def enable_api():
    """把 provider 切到 deepseek，使被门禁的接口放行（key 用假的即可，测试里会 mock LLM）。"""
    from app.llm_config import save_llm_settings
    save_llm_settings({"provider": "deepseek", "deepseek_api_key": "sk-test"})
    yield
