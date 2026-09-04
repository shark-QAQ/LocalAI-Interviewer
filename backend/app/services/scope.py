"""面试提问范围（类别 + 会话侧重计划）。

类别决定“本题允许怎么取材”：project 才允许围绕候选人代码库深挖，
stack / design / basics 需脱离具体代码库，面向技术栈原理、场景设计与通用 CS 基础。
纯函数模块，无任何依赖，interviewer / evaluator / routers 共用。
"""

from __future__ import annotations

# 各类别的取值必须保持稳定：会写入 messages.score_json 与报告
CATEGORIES = ["project", "stack", "design", "basics"]

CAT_LABELS = {
    "project": "项目深挖",
    "stack": "技术栈原理",
    "design": "场景与系统设计",
    "basics": "通用CS基础",
}

# 会话级“提问侧重”：一条 深挖(depth) ↔ 广度(breadth) 的滑杆，
# 三档只有“项目深挖占多少”在变，其余类别按固定比例分摊，档位之间不重叠。
FOCUS_LABELS = {
    "depth": "深挖为主",
    "balanced": "均衡并重",
    "breadth": "广度为主",
}

# 各侧重下四类别的权重（近似；build_round_plan 会按题数取整分配）
_FOCUS_WEIGHTS: dict[str, dict[str, float]] = {
    "depth": {"project": 0.60, "stack": 0.20, "design": 0.12, "basics": 0.08},
    "balanced": {"project": 0.40, "stack": 0.25, "design": 0.20, "basics": 0.15},
    "breadth": {"project": 0.20, "stack": 0.30, "design": 0.20, "basics": 0.30},
}


def build_round_plan(n_questions: int, focus: str = "balanced") -> list[str]:
    """按侧重为 n_questions 道技术题生成确定性的类别序列。

    采用“加权公平轮转”：先按权重+取整分配各类别配额，再每次挑‘离配额最落后’
    的类别填一道，使各类别尽量均匀铺开；若首题不是 project 且有 project 配额，
    把第一道换为 project 做热身。结果长度恒等于 n_questions。
    """
    weights = _FOCUS_WEIGHTS.get(focus, _FOCUS_WEIGHTS["balanced"])
    n = max(1, int(n_questions))

    # 按权重分配配额，余数补给小数部分最大的类别
    cnt = {c: int(weights[c] * n) for c in CATEGORIES}
    rem = n - sum(cnt.values())
    for c in sorted(CATEGORIES, key=lambda c: weights[c] * n - cnt[c], reverse=True)[:rem]:
        cnt[c] += 1

    used = {c: 0 for c in CATEGORIES}
    plan: list[str] = []
    for _ in range(n):
        eligible = [c for c in CATEGORIES if used[c] < cnt[c]]
        # 已用比例最小者（配额内“最欠配”）先出
        best = min(eligible, key=lambda c: used[c] / cnt[c])
        plan.append(best)
        used[best] += 1

    # 开场热身题固定为项目深挖（若计划里含 project）
    if plan and plan[0] != "project" and "project" in plan:
        i = plan.index("project")
        plan[0], plan[i] = plan[i], plan[0]
    return plan
