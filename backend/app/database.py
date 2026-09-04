from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Generator

from .config import settings

_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    repo_path       TEXT NOT NULL UNIQUE,
    language        TEXT,
    last_indexed_at DATETIME,
    chunk_count     INTEGER DEFAULT 0,
    indexed_chunks  INTEGER DEFAULT 0,
    total_chunks    INTEGER DEFAULT 0,
    index_started_at DATETIME,
    index_status    TEXT DEFAULT 'idle' CHECK(index_status IN ('idle','processing','completed','failed')),
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(index_status);
CREATE INDEX IF NOT EXISTS idx_projects_path ON projects(repo_path);

CREATE TABLE IF NOT EXISTS resumes (
    id              TEXT PRIMARY KEY,
    candidate_name  TEXT NOT NULL,
    email           TEXT,
    raw_text_hash   TEXT UNIQUE,
    parsed_data     TEXT NOT NULL,
    skills          TEXT NOT NULL,
    years_exp       REAL,
    index_status    TEXT DEFAULT 'idle' CHECK(index_status IN ('idle','processing','completed','failed')),
    chunk_count     INTEGER DEFAULT 0,
    indexed_chunks  INTEGER DEFAULT 0,
    total_chunks    INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interview_sessions (
    id              TEXT PRIMARY KEY,
    resume_id       TEXT NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    project_id      TEXT,
    target_position TEXT,
    difficulty      TEXT DEFAULT 'mid' CHECK(difficulty IN ('junior','mid','senior','hell')),
    max_rounds      INTEGER DEFAULT 8,
    current_round   INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'init' CHECK(status IN ('init','questioning','evaluating','terminated','reported')),
    context_summary TEXT,
    started_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at        DATETIME,
    expired_at      DATETIME
);

CREATE INDEX IF NOT EXISTS idx_sessions_resume ON interview_sessions(resume_id);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON interview_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON interview_sessions(status);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    round_num       INTEGER NOT NULL,
    role            TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system_eval')),
    content         TEXT NOT NULL,
    tokens_used     INTEGER,
    score_json      TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_round ON messages(session_id, round_num);

CREATE TABLE IF NOT EXISTS function_graph (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    caller_func     TEXT NOT NULL,
    callee_func     TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    call_line       INTEGER,
    call_count      INTEGER DEFAULT 1,
    UNIQUE(project_id, caller_func, callee_func, file_path)
);

CREATE INDEX IF NOT EXISTS idx_graph_caller ON function_graph(project_id, caller_func);
CREATE INDEX IF NOT EXISTS idx_graph_callee ON function_graph(project_id, callee_func);

CREATE TABLE IF NOT EXISTS cram_tasks (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    resume_id       TEXT REFERENCES resumes(id) ON DELETE SET NULL,
    focus_areas     TEXT,
    format          TEXT DEFAULT 'markdown',
    status          TEXT DEFAULT 'pending' CHECK(status IN ('pending','processing','completed','failed')),
    result_content  TEXT,
    word_count      INTEGER,
    error_msg       TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at    DATETIME
);

CREATE INDEX IF NOT EXISTS idx_cram_status ON cram_tasks(status);

CREATE TABLE IF NOT EXISTS materials (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    original_filename TEXT,
    file_ext          TEXT,
    kind              TEXT DEFAULT 'file',
    file_hash         TEXT UNIQUE,
    size              INTEGER DEFAULT 0,
    index_status      TEXT DEFAULT 'idle' CHECK(index_status IN ('idle','processing','completed','failed')),
    chunk_count       INTEGER DEFAULT 0,
    indexed_chunks    INTEGER DEFAULT 0,
    total_chunks      INTEGER DEFAULT 0,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_materials_status ON materials(index_status);
CREATE INDEX IF NOT EXISTS idx_materials_created ON materials(created_at);
"""


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(settings.db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = _get_connection()
    try:
        conn.executescript(_DDL)
        for col, typ in [("indexed_chunks", "INTEGER DEFAULT 0"), ("total_chunks", "INTEGER DEFAULT 0"), ("index_started_at", "DATETIME")]:
            try:
                conn.execute(f"ALTER TABLE projects ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass
        for col, typ in [("index_status", "TEXT DEFAULT 'idle'"), ("chunk_count", "INTEGER DEFAULT 0"), ("indexed_chunks", "INTEGER DEFAULT 0"), ("total_chunks", "INTEGER DEFAULT 0")]:
            try:
                conn.execute(f"ALTER TABLE resumes ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass
        # migrate difficulty CHECK constraint to include 'hell'
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS interview_sessions_new (
                    id TEXT PRIMARY KEY,
                    resume_id TEXT NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
                    project_id TEXT,
                    target_position TEXT,
                    difficulty TEXT DEFAULT 'mid' CHECK(difficulty IN ('junior','mid','senior','hell')),
                    max_rounds INTEGER DEFAULT 8,
                    current_round INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'init' CHECK(status IN ('init','questioning','evaluating','terminated','reported')),
                    context_summary TEXT,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    ended_at DATETIME,
                    expired_at DATETIME
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO interview_sessions_new
                SELECT * FROM interview_sessions
            """)
            conn.execute("DROP TABLE IF EXISTS interview_sessions")
            conn.execute("ALTER TABLE interview_sessions_new RENAME TO interview_sessions")
        except sqlite3.OperationalError:
            pass
        # 会话支持“一次勾选多个项目”，所选项目 id(JSON 数组) 存在 project_ids 列
        try:
            conn.execute("ALTER TABLE interview_sessions ADD COLUMN project_ids TEXT")
        except sqlite3.OperationalError:
            pass
        # 面试“提问侧重”预设（深挖/均衡/广度一条轴），用于题面类别调度与报告
        try:
            conn.execute("ALTER TABLE interview_sessions ADD COLUMN focus TEXT DEFAULT 'balanced'")
        except sqlite3.OperationalError:
            pass
        # 资料支持“单个文件 / 整个文件夹”两种形态
        try:
            conn.execute("ALTER TABLE materials ADD COLUMN kind TEXT DEFAULT 'file'")
        except sqlite3.OperationalError:
            pass
        # 修复 project_id 外键：允许空字符串（纯简历面试）
        try:
            fk_info = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='interview_sessions'").fetchone()
            if fk_info and "NOT NULL REFERENCES projects" in fk_info[0]:
                conn.execute("PRAGMA foreign_keys=OFF")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS interview_sessions_tmp (
                        id TEXT PRIMARY KEY,
                        resume_id TEXT NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
                        project_id TEXT,
                        target_position TEXT,
                        difficulty TEXT DEFAULT 'mid' CHECK(difficulty IN ('junior','mid','senior','hell')),
                        max_rounds INTEGER DEFAULT 8,
                        current_round INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'init' CHECK(status IN ('init','questioning','evaluating','terminated','reported')),
                        context_summary TEXT,
                        started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        ended_at DATETIME,
                        expired_at DATETIME,
                        project_ids TEXT,
                        focus TEXT DEFAULT 'balanced'
                    )
                """)
                conn.execute("INSERT OR IGNORE INTO interview_sessions_tmp SELECT * FROM interview_sessions")
                conn.execute("DROP TABLE interview_sessions")
                conn.execute("ALTER TABLE interview_sessions_tmp RENAME TO interview_sessions")
                conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def generate_id() -> str:
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
