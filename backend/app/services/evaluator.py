from __future__ import annotations

import json
import logging
from typing import Any

from ..config import settings
from ..llm_client import llm_generate
from .scope import CATEGORIES, CAT_LABELS

logger = logging.getLogger(__name__)

_EVAL_SYSTEM = """你是一位资深技术面试官。你需要从三个维度评估候选人的回答：
1. 技术深度（depth）：是否涉及底层原理、源码级理解、性能考量
2. 逻辑清晰度（logic）：回答是否条理清晰、有理有据
3. 解决方案完整性（integrity）：是否覆盖边界条件、异常处理、可扩展性

请严格按以下JSON格式返回评分（不要包含任何其他文字）：
{"depth": <1-10>, "logic": <1-10>, "integrity": <1-10>, "comment": "<50字以内的评价>"}
"""

_EVAL_TEMPLATE = """当前面试轮次：第{round_num}轮
考察技能：{skill}
候选人回答：
{answer}

参考上下文（代码片段）：
{context}

请评估该回答质量。"""

# 自我介绍阶段尚未涉及具体技术题，不能用“代码技术”维度打分，
# 改为从表达、内容、匹配三个非技术维度点评。
_INTRO_SYSTEM = """你是一位资深技术面试官。候选人刚刚做完自我介绍，此时还没有任何技术题，
因此不要用“技术深度/逻辑/完整性”这类代码维度去评分。请从以下三个维度给出简短、具体的现场点评：
1. 表达清晰度（clarity）：条理是否清楚、重点是否突出、语气是否自然
2. 内容充实度（substance）：是否讲清了背景、项目经历、技术栈或亮点
3. 岗位匹配度（fit）：介绍内容是否贴合目标岗位与简历上的技能

请严格按以下JSON格式返回评分（不要包含任何其他文字）：
{"clarity": <1-10>, "substance": <1-10>, "fit": <1-10>, "comment": "<60字以内的点评，可指出介绍里可补充的方向>"}
"""


def parse_json_object(raw: str) -> dict[str, Any] | None:
    """从模型输出中尽力解析出一个 JSON 对象；解析失败返回 None。

    兼容常见的 ```json ... ``` 代码块包裹，以及回复前后夹带说明文字的情况。
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()
    # 去掉 ```json / ``` 代码块包裹
    if text.startswith("```"):
        text = text[3:]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _to_score(value: Any, default: float = 5.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    return max(1.0, min(10.0, score))


def _flag(value: Any) -> bool:
    """把模型输出的 true/1/"1"/"true" 规整为布尔。"""
    return value in (True, 1, "1", "true", "True", "TRUE")


def _axis_avg(depth: float, logic: float, integrity: float) -> float:
    return (
        depth * settings.eval_weights_depth
        + logic * settings.eval_weights_logic
        + integrity * settings.eval_weights_integrity
    )


# 命中“门控”后各维的上限：答非所问/有硬伤/实质为空，一律不得高于此分
_GATE_CEIL = 3.0


def finalize_answer_eval(
    obj: dict[str, Any], answer: str | None = None
) -> dict[str, Any]:
    """把“技术问答”评分 JSON 规整为 {depth, logic, integrity, correctness, avg, comment}。

    新规则：correctness=切题度与正确性，off_topic / critical_error 是模型如实上报的门控；
    命中门控，或回答本身过短（<8 字，纯寒暄/不知道/乱答）时，各维一律钳到 ≤3，
    从“代码层”兜底，不再指望模型自觉压分。
    """
    depth = _to_score(obj.get("depth"))
    logic = _to_score(obj.get("logic"))
    integrity = _to_score(obj.get("integrity"))

    corr_raw = obj.get("correctness")
    corr: float | None = None if corr_raw is None else _to_score(corr_raw)
    off = _flag(obj.get("off_topic"))
    crit = _flag(obj.get("critical_error"))

    reasons: list[str] = []
    if off:
        reasons.append("答非所问：回答与所问问题几乎无关")
    if crit:
        reasons.append("关键点/结论存在明显错误或与参考要点相悖")
    if answer is not None and len(str(answer).strip()) < 8:
        reasons.append("回答过短，未实质作答")

    if reasons:
        depth = min(depth, _GATE_CEIL)
        logic = min(logic, _GATE_CEIL)
        integrity = min(integrity, _GATE_CEIL)
        if corr is not None:
            corr = min(corr, _GATE_CEIL)

    # 平均分 = 0.4 × 切题正确 + 0.6 × 三轴质感（模型未给 correctness 时退回纯三轴，兼容旧输出）
    avg = _axis_avg(depth, logic, integrity)
    if corr is not None:
        avg = 0.4 * corr + 0.6 * avg

    comment = str(obj.get("comment") or "评估完成")[:200]
    if reasons:
        prefix = "；".join(reasons)
        comment = (prefix + "。" + comment)[:220]

    out: dict[str, Any] = {
        "depth": round(depth, 1),
        "logic": round(logic, 1),
        "integrity": round(integrity, 1),
        "avg": round(avg, 1),
        "comment": comment,
    }
    if corr is not None:
        out["correctness"] = round(corr, 1)
    if off or crit:
        out["off_topic"] = off
        out["critical_error"] = crit
    return out


def finalize_intro_eval(
    obj: dict[str, Any], answer: str | None = None
) -> dict[str, Any]:
    """把“自我介绍点评” JSON 规整为 {type, clarity, substance, fit, avg, comment}。"""
    clarity = _to_score(obj.get("clarity"))
    substance = _to_score(obj.get("substance"))
    fit = _to_score(obj.get("fit"))

    reasons: list[str] = []
    if _flag(obj.get("off_topic")):
        reasons.append("答非所问：介绍与岗位/技术面试几乎无关或无实质内容")
    if answer is not None and len(str(answer).strip()) < 8:
        reasons.append("回答过短，未实质作答（仅按实际输入评，不因简历好看而抬分）")
    if reasons:
        clarity = min(clarity, _GATE_CEIL)
        substance = min(substance, _GATE_CEIL)
        fit = min(fit, _GATE_CEIL)

    avg = (clarity + substance + fit) / 3.0
    comment = str(obj.get("comment") or "自我介绍点评完成")[:200]
    if reasons:
        comment = (reasons[0] + "。" + comment)[:220]
    return {
        "type": "self_intro",
        "clarity": round(clarity, 1),
        "substance": round(substance, 1),
        "fit": round(fit, 1),
        "avg": round(avg, 1),
        "comment": comment,
    }


async def evaluate_answer(
    round_num: int,
    skill: str,
    answer: str,
    context: str = "",
) -> dict[str, Any]:
    prompt = _EVAL_TEMPLATE.format(
        round_num=round_num, skill=skill, answer=answer, context=context
    )

    raw = await llm_generate(
        prompt=prompt, system=_EVAL_SYSTEM, temperature=0.3
    )

    obj = parse_json_object(raw)
    if obj is None:
        logger.warning("Failed to parse evaluation, using defaults")
        return {
            "depth": 5.0,
            "logic": 5.0,
            "integrity": 5.0,
            "avg": 5.0,
            "comment": "评估解析失败，请人工复查",
        }
    return finalize_answer_eval(obj)


async def evaluate_introduction(
    intro_text: str,
    target_position: str = "",
    skills: list[str] | None = None,
) -> dict[str, Any]:
    """对候选人的自我介绍做一次非技术维度的独立点评。

    返回带 ``type: "self_intro"`` 标记的结果，报告与技能覆盖会据此将其排除。
    模型输出解析失败时返回 ``avg=None``，由上层决定不展示该卡片。
    """
    skills = skills or []
    prompt = f"""目标岗位：{target_position or '（未指定）'}
候选人简历技能：{', '.join(skills[:10]) if skills else '（无）'}

候选人自我介绍：
{intro_text[:800]}

请对这段自我介绍做点评。"""
    raw = await llm_generate(
        prompt=prompt, system=_INTRO_SYSTEM, temperature=0.3
    )

    obj = parse_json_object(raw)
    if obj is None:
        logger.warning("Failed to parse self-introduction evaluation")
        return {
            "type": "self_intro",
            "clarity": None,
            "substance": None,
            "fit": None,
            "avg": None,
            "comment": "（自我介绍点评生成失败）",
        }
    return finalize_intro_eval(obj)


async def generate_report(
    messages: list[dict[str, Any]], skills: list[str]
) -> dict[str, Any]:
    scores = [json.loads(m["score_json"]) for m in messages if m.get("score_json")]
    if not scores:
        return {
            "avg_score": 0,
            "radar_data": {"labels": [], "values": []},
            "category_stats": [],
            "strength_tags": [],
            "weakness_tags": [],
            "improvement_suggestion": "暂无评估数据",
        }

    avg_score = sum(s["avg"] for s in scores) / len(scores)

    # 各类别覆盖统计（项目深挖/技术栈原理/场景与系统设计/通用CS基础）
    stat: dict[str, dict[str, float]] = {c: {"count": 0, "sum": 0.0} for c in CATEGORIES}
    for s in scores:
        cat = s.get("cat")
        if cat not in stat:
            cat = "project"  # 旧数据兜底
        stat[cat]["count"] += 1
        stat[cat]["sum"] += float(s.get("avg", 0) or 0)
    category_stats = [
        {
            "cat": c,
            "label": CAT_LABELS.get(c, c),
            "count": int(stat[c]["count"]),
            "avg": round(stat[c]["sum"] / stat[c]["count"], 1) if stat[c]["count"] else None,
        }
        for c in CATEGORIES
    ]

    radar_labels = ["技术深度", "逻辑思维", "项目经验", "沟通表达", "代码规范"]
    # “项目经验”维度改用“项目深挖”类题目的实测均分；无此类题时退回启发式
    proj_n = int(stat["project"]["count"])
    proj_avg = stat["project"]["sum"] / proj_n if proj_n else None
    radar_values = [
        sum(s["depth"] for s in scores) / len(scores),
        sum(s["logic"] for s in scores) / len(scores),
        round(min(10, proj_avg), 1) if proj_avg is not None else min(10, avg_score + 1),
        min(10, avg_score + 0.5),
        max(1, avg_score - 1),
    ]
    radar_values = [round(v, 1) for v in radar_values]

    strength_tags: list[str] = []
    weakness_tags: list[str] = []
    for s in scores:
        if s["depth"] >= 7:
            strength_tags.append("技术深度好")
        elif s["depth"] < 5:
            weakness_tags.append("技术深度不足")
        if s["logic"] >= 7:
            strength_tags.append("逻辑清晰")
        elif s["logic"] < 5:
            weakness_tags.append("逻辑需加强")
        if s["integrity"] >= 7:
            strength_tags.append("方案完整")
        elif s["integrity"] < 5:
            weakness_tags.append("方案不够完整")
        corr = s.get("correctness")
        if corr is not None:
            if corr >= 7:
                strength_tags.append("切题准确")
            elif corr < 5:
                weakness_tags.append("答非所问/不够贴合题目")

    strength_tags = list(dict.fromkeys(strength_tags))[:5]
    weakness_tags = list(dict.fromkeys(weakness_tags))[:5]

    coverage_line = "；".join(
        f"{cs['label']} {cs['count']} 题"
        + (f" · 均分 {cs['avg']:.1f}" if cs["avg"] is not None else " · 未考察")
        for cs in category_stats
    )
    suggestion_prompt = f"""基于以下面试评估结果，给出一段简短的复习建议（100字以内）：
平均分：{avg_score:.1f}
优势：{', '.join(strength_tags)}
不足：{', '.join(weakness_tags)}
考察技能：{', '.join(skills)}
各方向覆盖与得分：{coverage_line}
要求：指出明显偏科或未覆盖的方向，并针对其中最弱/缺失的方向给出可执行的补强建议。
"""
    suggestion = await llm_generate(
        prompt=suggestion_prompt,
        system="你是一位职业导师，给出简洁的复习建议。",
        temperature=0.5,
    )

    return {
        "avg_score": round(avg_score, 1),
        "radar_data": {"labels": radar_labels, "values": radar_values},
        "category_stats": category_stats,
        "strength_tags": strength_tags,
        "weakness_tags": weakness_tags,
        "improvement_suggestion": suggestion.strip(),
    }
