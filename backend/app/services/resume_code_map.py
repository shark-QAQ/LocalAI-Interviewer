"""简历项目 ↔ 导入代码库 的映射（自动 + 待人工确认）。

- 高置信的项目：上传/解析简历时**自动**落表，不打扰用户；
- 拿不准的项目：状态为 pending，前端提供手动确认（可选某个代码库，或选“无对应”）。
- 持久化：<项目>/data/resume_code_map.json。键为简历项目名（或其别名），值为代码库名数组；
  值为 [] 表示“用户已明确：该项目无对应代码库”。
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..config import settings


def map_path() -> Any:
    return settings.data_dir / "resume_code_map.json"


def load_map() -> dict[str, list[str]]:
    try:
        with open(map_path(), encoding="utf-8") as f:
            data = json.load(f) or {}
        return {str(k): [x for x in v if isinstance(x, str)] for k, v in data.items() if isinstance(v, list)}
    except Exception:
        return {}


def _save_map(mapping: dict[str, list[str]]) -> None:
    p = map_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")


def map_for_name(project_name: str) -> list[str]:
    """按简历项目名查对应代码库（键做子串匹配，忽略大小写）。"""
    low = (project_name or "").lower()
    out: list[str] = []
    for key, repos in load_map().items():
        if repos and key and key.lower() in low:
            for r in repos:
                if r not in out:
                    out.append(r)
    return out


def project_status(project_name: str) -> str:
    """'mapped' | 'none' | 'pending'。

    只要映射表里能按别名命中代码库就算 mapped；整名记录为 [] 才是明确“无对应”。
    """
    if map_for_name(project_name):
        return "mapped"
    m = load_map()
    if project_name in m and not m[project_name]:
        return "none"
    return "pending"


def set_decision(project_name: str, code_repos: list[str]) -> None:
    """记录用户决策（code_repos 为空即“无对应代码库”）。"""
    m = load_map()
    m[project_name] = list(code_repos)
    _save_map(m)


# 已知代码库 → 中英提示词（新增仓库未命中时用仓库名分词兜底）
_CODE_HINTS: dict[str, list[str]] = {
    "cnn-sem": ["cnn", "sem", "aeye", "睿目", "视", "视觉", "眼", "语义", "模型", "semantic"],
    "govshare-phase2": ["gov", "share", "政务", "政享", "政", "数据", "共享", "中数", "政通"],
    "secops-platform": ["sec", "ops", "安全", "智盾", "盾", "中枢", "安御", "shield", "defense"],
    "tarkovsage": ["tarkov", "塔科夫", "游戏", "智囊", "sage"],
}

_COMPANY_STOP = re.compile(r"（[^）]*公司[^）]*）|科技有限公司|有限公司", re.IGNORECASE)


def _repo_hints(repo_name: str) -> list[str]:
    key = repo_name.lower().replace("_", "-").strip("-")
    if key in _CODE_HINTS:
        return list(_CODE_HINTS[key])
    parts = re.split(r"[^a-z0-9一-鿿]+", key)
    return [t for t in parts if len(t) >= 2]


def _norm(s: str) -> str:
    return (s or "").lower()


def _best_match(pname: str, description: str, repo_names: list[str]) -> tuple[str | None, int]:
    """返回 (最高分仓库或 None, 最高分)。得分必须唯一且为正才算“高置信”。"""
    text = _norm(_COMPANY_STOP.sub(" ", f"{pname} {description}"))
    scored: list[tuple[int, str]] = []
    for repo in repo_names:
        hits = sum(1 for h in _repo_hints(repo) if h and h in text)
        base = repo.split("-")[0].lower()
        if base and base in _norm(pname):
            hits += 3
        scored.append((hits, repo))
    scored.sort(key=lambda x: (-x[0], x[1]))
    top = scored[0][0] if scored else 0
    second = scored[1][0] if len(scored) > 1 else 0
    if top > 0 and top > second:
        return scored[0][1], top
    return None, 0


def auto_assign(
    projects: list[dict[str, str]], code_repos: list[dict[str, str]]
) -> dict[str, list[str]]:
    """只给“高置信唯一匹配”的项目生成映射（一对一）。拿不准的不返回。"""
    repo_names = [r["name"] for r in code_repos if r.get("name")]
    best_for: dict[str, tuple[str | None, int]] = {}
    order: list[str] = []
    for p in projects:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        best_for[name] = _best_match(name, p.get("description") or "", repo_names)
        order.append(name)

    used: set[str] = set()
    out: dict[str, list[str]] = {}
    # 置信度高的优先抢占，保证一对一
    for name in sorted(order, key=lambda n: -best_for[n][1]):
        repo, score = best_for[name]
        if repo and score > 0 and repo not in used:
            used.add(repo)
            out[name] = [repo]
    return out


def ensure_confident(
    projects: list[dict[str, str]], code_repos: list[dict[str, str]]
) -> None:
    """把高置信匹配落表（重复调用幂等）。拿不准的交由前端手动确认。"""
    current = load_map()
    auto = auto_assign(projects, code_repos)
    changed = False
    for name, repos in auto.items():
        if repos and name not in current:
            current[name] = repos
            changed = True
    if changed:
        _save_map(current)


def build_mapping_note(resume_projects: list[dict[str, str]]) -> str:
    """生成给 LLM 的“对应关系 + 禁区”说明（有映射/有明确无映射才返回非空）。"""
    m = load_map()
    if not m:
        return ""
    lines: list[str] = []
    for p in resume_projects[:10]:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        status = project_status(name)
        if status == "mapped":
            lines.append(f"- {name} ↔ 代码库 {'、'.join(map_for_name(name))}")
        elif status == "none":
            lines.append(f"- {name} ↔（已确认无对应代码库，仅按简历经历作答）")
        # pending 的不写进对应关系，避免面试官拿不准的假设提问
    if not lines:
        return ""
    return (
        "本场项目对应关系（务必遵守，禁止张冠李戴）：\n"
        + "\n".join(lines)
        + "\n规则：谈某简历项目时只引它对应代码库；不要把别的代码库说成它的实现，反之亦然。"
    )
