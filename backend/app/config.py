from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    project_name: str = "LocalAI-Interviewer"
    base_url: str = "http://localhost:8000"
    api_prefix: str = "/api/v1"

    data_dir: Path = Path(__file__).resolve().parent.parent.parent / "data"
    db_path: Path = data_dir / "db" / "interview.db"
    chroma_dir: Path = data_dir / "chroma_data"
    upload_dir: Path = data_dir / "uploads"
    # 生成简历时是否自动另存一份到系统桌面（本地工具默认开；测试用 APP_RESUME_SAVE_DESKTOP=0 关闭）
    resume_save_desktop: bool = True

    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    llm_model: str = "qwen2.5:7b"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024

    # 文本生成提供方：ollama（本地）/ deepseek（API）。默认 ollama，可在设置页运行时切换。
    llm_provider: str = "ollama"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_max_tokens: int = 4096
    # 该网关默认会先输出一长段“思考”再作答，出题/评分/品鉴延迟高。
    # 默认关闭思考以大幅提速（如需深度推理可设 APP_DEEPSEEK_DISABLE_THINKING=false）
    deepseek_disable_thinking: bool = True

    llm_timeout: float = 120.0
    embed_timeout: float = 300.0
    max_history_rounds: int = 3
    default_max_rounds: int = 8
    session_expire_hours: int = 2

    chunk_size: int = 1500
    chunk_overlap: int = 200

    eval_weights_depth: float = 0.4
    eval_weights_logic: float = 0.3
    eval_weights_integrity: float = 0.3

    allowed_extensions: set[str] = {
        ".java", ".py", ".js", ".ts", ".go", ".md", ".yaml", ".yml", ".sql",
        ".kt", ".scala", ".rs", ".c", ".cpp", ".h", ".cs", ".rb", ".php",
    }
    ignored_dirs: set[str] = {
        ".git", "node_modules", "__pycache__", "target", "build", "dist",
        ".idea", ".vscode", "venv", ".venv", "env", ".env",
    }

    model_config = {"env_prefix": "APP_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.db_path.parent.mkdir(parents=True, exist_ok=True)
settings.chroma_dir.mkdir(parents=True, exist_ok=True)
settings.upload_dir.mkdir(parents=True, exist_ok=True)
