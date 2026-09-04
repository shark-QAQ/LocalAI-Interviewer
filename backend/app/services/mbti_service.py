"""MBTI 职业性格测试服务（仅 DeepSeek/API 提供方开放）。

- 出题：LLM 生成 20 道二选一情景题（E/I、S/N、T/F、J/P 四维各 5）；解析/校验失败自动重试一次，
  再失败回退到内置 20 题题库，保证功能始终可用。
- 判分：按维度票数确定性计算（同卷结果可复现），平票取 E/S/T/J 首字母并标记 borderline。
- 结论：LLM 生成性格描述 + “更合适行业(带百分比)”；解析失败回退内置 16 型行业表。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from ..llm_client import llm_generate

logger = logging.getLogger(__name__)

# 维度定义：code / 中文标签 / 左右字母与名称（前端横条展示用）
DIMENSIONS = [
    {"code": "EI", "label": "能量来源", "left": "E", "left_name": "外向", "right": "I", "right_name": "内向"},
    {"code": "SN", "label": "信息获取", "left": "S", "left_name": "实感", "right": "N", "right_name": "直觉"},
    {"code": "TF", "label": "决策方式", "left": "T", "left_name": "思考", "right": "F", "right_name": "情感"},
    {"code": "JP", "label": "生活态度", "left": "J", "left_name": "判断", "right": "P", "right_name": "感知"},
]
DIM_POLES: dict[str, tuple[str, str]] = {d["code"]: (d["left"], d["right"]) for d in DIMENSIONS}
DIM_LABEL: dict[str, str] = {d["code"]: d["label"] for d in DIMENSIONS}
PER_DIM = 5
TOTAL = 4 * PER_DIM

_TYPE_FULL = {
    "INTJ": "建筑师", "INTP": "逻辑学家", "ENTJ": "指挥官", "ENTP": "辩论家",
    "INFJ": "提倡者", "INFP": "调停者", "ENFJ": "主人公", "ENFP": "竞选者",
    "ISTJ": "物流师", "ISFJ": "守卫者", "ESTJ": "总经理", "ESFJ": "执政官",
    "ISTP": "鉴赏家", "ISFP": "探险家", "ESTP": "企业家", "ESFP": "表演者",
}

# ---------------------------- 出题 ----------------------------

_QUESTION_SYSTEM = """你是资深 MBTI 性格测评命题官。请为一份自测生成二选一情景题，要求贴近真实 MBTI 题目的“偏好倾向”感受。

硬性要求：
1. 只输出一个 JSON 数组，不要任何解释、前后缀或代码块标记。
2. 数组里每个对象的 dim 必须与 user 提示指定的维度一致；题数与选项要求以 user 提示为准。
3. 每题字段：{"dim": "<EI|SN|TF|JP>", "text": "<引导语/场景，第一人称，20~40字>", "opA": "<选项A>", "opB": "<选项B>", "poleA": "<A对应字母>", "poleB": "<B对应字母>"}
4. poleA/poleB 必须且只能取该 dim 的两个字母（EI→E/I，SN→S/N，TF→T/F，JP→J/P）。
5. 选项须是“你更偏向怎么做”，无对错、不评判；避免含糊、双关与明显常识矛盾。
6. text 只描述情境与两难，不含“选项”“请选择”等引导词以外的元说明。"""


def _extract_json_array(raw: str) -> list[Any]:
    if not raw:
        return []
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _validate_questions(questions: list[Any]) -> bool:
    if not isinstance(questions, list) or len(questions) != TOTAL:
        return False
    cnt: dict[str, int] = {}
    for q in questions:
        if not isinstance(q, dict):
            return False
        dim = q.get("dim")
        if dim not in DIM_POLES:
            return False
        cnt[dim] = cnt.get(dim, 0) + 1
        pole_a, pole_b = str(q.get("poleA", "")), str(q.get("poleB", ""))
        left, right = DIM_POLES[dim]
        if pole_a not in (left, right) or pole_b not in (left, right):
            return False
        if pole_a == pole_b:
            return False
        if not (q.get("text") and q.get("opA") and q.get("opB")):
            return False
    return all(cnt.get(d, 0) == PER_DIM for d in DIM_POLES)


def _valid_one(q: Any) -> bool:
    """校验单题结构是否合法。"""
    if not isinstance(q, dict):
        return False
    dim = q.get("dim")
    if dim not in DIM_POLES:
        return False
    left, right = DIM_POLES[dim]
    pole_a, pole_b = str(q.get("poleA", "")), str(q.get("poleB", ""))
    if pole_a not in (left, right) or pole_b not in (left, right) or pole_a == pole_b:
        return False
    return bool(q.get("text") and q.get("opA") and q.get("opB"))


async def _llm_dim_questions(dim: str) -> list[Any]:
    """单个维度并行出题：一次调用只生成 5 道，显著降低等待时间。"""
    left, right = DIM_POLES[dim]
    prompt = (
        f'请只输出一个 JSON 数组：{PER_DIM} 道题的题目，每道题的 "dim" 都必须等于 '
        f'"{dim}"（该维两极为 {left}/{right}，poleA/poleB 只能取这两极）。只输出数组本身。'
    )
    for attempt in (1, 2):
        try:
            raw = await llm_generate(prompt=prompt, system=_QUESTION_SYSTEM, temperature=0.8)
            items = _extract_json_array(raw)
            valid = [it for it in items if _valid_one(it) and it.get("dim") == dim]
            if len(valid) >= PER_DIM:
                return valid[:PER_DIM]
        except Exception:
            logger.warning("MBTI %s 维度出题异常(第 %s 次)", dim, attempt, exc_info=True)
    return []


# 内置兜底题库（LLM 连续失败时使用，保证功能可用）
_FALLBACK_QUESTIONS: list[dict[str, str]] = [
    # E/I（能量来源）
    {"dim": "EI", "text": "忙碌一天后，你更想怎样恢复精力？", "opA": "约朋友出门热闹一场", "opB": "独自安静待着充电", "poleA": "E", "poleB": "I"},
    {"dim": "EI", "text": "团队讨论时，你通常更享受哪种状态？", "opA": "边想边说，随时插话碰撞", "opB": "先听清楚再组织发言", "poleA": "E", "poleB": "I"},
    {"dim": "EI", "text": "面对陌生人多的聚会，你更接近哪种感受？", "opA": "越聊越来劲、主动搭话", "opB": "略感消耗、更喜欢小圈子", "poleA": "E", "poleB": "I"},
    {"dim": "EI", "text": "工作中遇到问题，你第一反应更倾向？", "opA": "找人一起讨论来想清楚", "opB": "自己先琢磨出方案再说", "poleA": "E", "poleB": "I"},
    {"dim": "EI", "text": "你更愿意被别人怎样形容？", "opA": "热情外放、善于交往", "opB": "沉稳内敛、专注自省", "poleA": "E", "poleB": "I"},
    # S/N（信息获取）
    {"dim": "SN", "text": "学新东西时，你更偏向从哪儿入手？", "opA": "看具体操作和实际案例", "opB": "先抓整体框架和可能性", "poleA": "S", "poleB": "N"},
    {"dim": "SN", "text": "描述一件事时，你更关注？", "opA": "确切的事实、细节和步骤", "opB": "背后规律、趋势与联想", "poleA": "S", "poleB": "N"},
    {"dim": "SN", "text": "做决定时，你更依赖？", "opA": "眼前能验证的数据经验", "opB": "灵光一现的直觉预感", "poleA": "S", "poleB": "N"},
    {"dim": "SN", "text": "你看重工作里哪个方面？", "opA": "把眼前任务一步不差做好", "opB": "探索新玩法与改进空间", "poleA": "S", "poleB": "N"},
    {"dim": "SN", "text": "读说明文档时，你更习惯？", "opA": "照步骤逐条执行", "opB": "跳过细节先想为什么这样", "poleA": "S", "poleB": "N"},
    # T/F（决策方式）
    {"dim": "TF", "text": "朋友倾诉烦恼时，你更常先给出？", "opA": "客观分析和解决方案", "opB": "共情安慰和情绪支持", "poleA": "T", "poleB": "F"},
    {"dim": "TF", "text": "做重要决策时，你更重视？", "opA": "逻辑一致与利弊得失", "opB": "对人的影响和内心感受", "poleA": "T", "poleB": "F"},
    {"dim": "TF", "text": "指出同事问题时，你更偏向？", "opA": "就事论事直说问题", "opB": "先照顾对方情绪再委婉提", "poleA": "T", "poleB": "F"},
    {"dim": "TF", "text": "评价一个方案，你更先问？", "opA": "它是否合理高效", "opB": "大家用起来是否舒服", "poleA": "T", "poleB": "F"},
    {"dim": "TF", "text": "与人意见不合时，你更想？", "opA": "辩清道理分出对错", "opB": "尽量维持和气不伤感情", "poleA": "T", "poleB": "F"},
    # J/P（生活态度）
    {"dim": "JP", "text": "面对出行计划，你更接近？", "opA": "提前订好行程按点执行", "opB": "到了再说、随遇而安", "poleA": "J", "poleB": "P"},
    {"dim": "JP", "text": "工作截止前，你通常？", "opA": "提早规划稳步推进", "opB": "临到期限反而迸发效率", "poleA": "J", "poleB": "P"},
    {"dim": "JP", "text": "你的桌面/日程更接近？", "opA": "分门别类、井井有条", "opB": "看似随性但自有章法", "poleA": "J", "poleB": "P"},
    {"dim": "JP", "text": "规则流程变化时，你更倾向？", "opA": "尽快定下来照做", "opB": "保留灵活、边走边看", "poleA": "J", "poleB": "P"},
    {"dim": "JP", "text": "你喜欢的工作节奏更偏向？", "opA": "按计划清单一项项勾掉", "opB": "弹性安排、允许即兴", "poleA": "J", "poleB": "P"},
]


def _fallback_for(dim: str) -> list[dict[str, str]]:
    return [dict(q) for q in _FALLBACK_QUESTIONS if q["dim"] == dim]


async def generate_questions() -> list[Any]:
    """返回 20 题：四个维度各自“并行”出一批 5 题（等待≈一次小请求），
    某维度失败则用内置同维 5 题补齐，保证总 20 题且每维 5 题。"""
    dims = list(DIM_POLES.keys())
    batches = await asyncio.gather(*[_llm_dim_questions(d) for d in dims])
    combined: list[Any] = []
    for dim, got in zip(dims, batches):
        if len(got) < PER_DIM:
            logger.warning("MBTI %s 维度出题失败，用内置题库补齐", dim)
            got = _fallback_for(dim)
        combined.extend(got)
    return combined


# ---------------------------- 判分 ----------------------------

def _tie_first(dim: str) -> str:
    left, _right = DIM_POLES[dim]
    return left  # E/S/T/J


def compute_type(answers: list[dict[str, str]]) -> dict[str, Any]:
    """确定性计分：返回 type/type_full/dimensions/borderline。"""
    counts: dict[str, dict[str, int]] = {}
    for d in DIM_POLES:
        counts[d] = {DIM_POLES[d][0]: 0, DIM_POLES[d][1]: 0}
    for a in answers or []:
        dim = a.get("dim")
        pole = a.get("pole")
        if dim in counts and pole in counts[dim]:
            counts[dim][pole] += 1

    type_letters: list[str] = []
    borderline = False
    dimensions: list[dict[str, Any]] = []
    for meta in DIMENSIONS:
        dim = meta["code"]
        left, right = DIM_POLES[dim]
        c_left, c_right = counts[dim][left], counts[dim][right]
        if c_left == c_right:
            pick = _tie_first(dim)
            borderline = True
        else:
            pick = left if c_left > c_right else right
        type_letters.append(pick)
        left_pct = round(100 * c_left / PER_DIM)
        right_pct = round(100 * c_right / PER_DIM)
        dimensions.append({
            "dim": dim,
            "label": meta["label"],
            "left": left, "left_name": meta["left_name"], "left_pct": left_pct,
            "right": right, "right_name": meta["right_name"], "right_pct": right_pct,
            "pick": pick,
        })

    type_code = "".join(type_letters)
    return {
        "type": type_code,
        "type_full": _TYPE_FULL.get(type_code, type_code),
        "dimensions": dimensions,
        "borderline": borderline,
    }


# ---------------------------- 结论 ----------------------------

_SUMMARY_SYSTEM = """你是一位懂 MBTI 又务实的职业规划顾问。请基于给定性格类型与倾向百分比，输出一份简短职业画像。

只输出一个 JSON 对象：{"summary": "<60~120字，描述该类型的工作风格/优势/成长提醒>", "industries": [{"name": "<行业名>", "pct": <0-100整数，表示适合度>， "why": "<一句话理由，≤20字>"} × 4]}
要求：行业要真实常见、名称具体（如“软件研发/产品经理/心理咨询/数据科学”），pct 与 why 自洽、不要编造离谱数字。"""

# LLM 结论失败时的内置兜底：按 16 型给 3 个行业与约略适合度
_FALLBACK_INDUSTRY: dict[str, list[dict[str, Any]]] = {
    "INTJ": [{"name": "战略/架构类岗位", "pct": 92, "why": "长于系统设计与长远规划"}, {"name": "数据科学", "pct": 86, "why": "逻辑严密喜钻研"}, {"name": "独立研究", "pct": 80, "why": "偏好深度独立工作"}],
    "INTP": [{"name": "软件研发", "pct": 90, "why": "热爱抽象与原理"}, {"name": "研究与算法", "pct": 88, "why": "探索欲强"}, {"name": "数据分析", "pct": 82, "why": "抽丝剥茧解决问题"}],
    "ENTJ": [{"name": "企业/项目管理", "pct": 92, "why": "天生的组织与决策者"}, {"name": "创业/新业务", "pct": 87, "why": "目标导向敢拍板"}, {"name": "咨询顾问", "pct": 84, "why": "全局视角强"}],
    "ENTP": [{"name": "产品/创新岗", "pct": 90, "why": "点子多爱挑战"}, {"name": "创业", "pct": 86, "why": "拥抱不确定"}, {"name": "市场策略", "pct": 82, "why": "善于说服与发散"}],
    "INFJ": [{"name": "心理咨询/教练", "pct": 90, "why": "共情且有使命感"}, {"name": "内容与策划", "pct": 84, "why": "洞察人心善表达"}, {"name": "公益/教育", "pct": 82, "why": "价值观驱动"}],
    "INFP": [{"name": "内容创作", "pct": 88, "why": "理想与文字感强"}, {"name": "心理/人文服务", "pct": 85, "why": "温和有同理心"}, {"name": "自由职业", "pct": 80, "why": "需要弹性与意义"}],
    "ENFJ": [{"name": "团队管理/HR", "pct": 91, "why": "善于凝聚与激励"}, {"name": "教育/培训", "pct": 87, "why": "乐于成就他人"}, {"name": "品牌/公关", "pct": 82, "why": "人脉与感染力"}],
    "ENFP": [{"name": "市场营销", "pct": 88, "why": "热情点子多"}, {"name": "创意/内容", "pct": 86, "why": "表达欲强"}, {"name": "社群运营", "pct": 83, "why": "擅长连接人群"}],
    "ISTJ": [{"name": "财务/审计", "pct": 90, "why": "严谨细致守规则"}, {"name": "工程/质量管控", "pct": 86, "why": "重视可靠与流程"}, {"name": "公务员/运营", "pct": 83, "why": "稳定执行强"}],
    "ISFJ": [{"name": "医疗/护理", "pct": 88, "why": "耐心体贴有责任心"}, {"name": "行政/后勤", "pct": 84, "why": "细致可靠"}, {"name": "教育辅导", "pct": 82, "why": "乐于默默支持他人"}],
    "ESTJ": [{"name": "运营管理", "pct": 91, "why": "讲规矩重效率"}, {"name": "供应链/生产", "pct": 87, "why": "组织推进力强"}, {"name": "质量管理", "pct": 84, "why": "标准意识强"}],
    "ESFJ": [{"name": "人力资源", "pct": 88, "why": "亲和重协作"}, {"name": "客户成功", "pct": 85, "why": "体贴周到"}, {"name": "社区/服务运营", "pct": 82, "why": "乐于维系关系"}],
    "ISTP": [{"name": "工程/运维", "pct": 90, "why": "动手能力强应变快"}, {"name": "技术支持", "pct": 86, "why": "擅长拆解实际问题"}, {"name": "制造/自动化", "pct": 82, "why": "务实现场导向"}],
    "ISFP": [{"name": "设计/美学岗", "pct": 88, "why": "审美细腻"}, {"name": "手作/餐饮", "pct": 82, "why": "享受专注创作"}, {"name": "关怀型服务", "pct": 80, "why": "温和低调"}],
    "ESTP": [{"name": "销售/商务拓展", "pct": 91, "why": "行动力与说服力强"}, {"name": "创业/快消运营", "pct": 85, "why": "随机应变"}, {"name": "运动/极限行业", "pct": 80, "why": "爱挑战爱刺激"}],
    "ESFP": [{"name": "演艺/娱乐", "pct": 88, "why": "表现力与感染力强"}, {"name": "销售/客户关系", "pct": 85, "why": "热情开朗"}, {"name": "活动策划", "pct": 83, "why": "会来事氛围好"}],
}


async def summarize(type_code: str, dimensions: list[dict[str, Any]]) -> dict[str, Any]:
    """LLM 生成性格总结与行业推荐；解析失败回退内置行业表。"""
    dim_lines = []
    for d in dimensions:
        picked = d["pick"]
        other = d["right"] if picked == d["left"] else d["left"]
        picked_name = d["left_name"] if picked == d["left"] else d["right_name"]
        picked_pct = d["left_pct"] if picked == d["left"] else d["right_pct"]
        dim_lines.append(f"- {d['label']}：倾向 {picked}({picked_name}) {picked_pct}%，另一极 {other} 占 {100 - picked_pct}%")
    prompt = (
        f"被测 MBTI 类型：{type_code}（{_TYPE_FULL.get(type_code, type_code)}）\n"
        "维度倾向：\n" + "\n".join(dim_lines) +
        "\n\n请输出职业画像 JSON（summary + industries[4]）。"
    )
    try:
        raw = await llm_generate(prompt=prompt, system=_SUMMARY_SYSTEM, temperature=0.6)
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            obj = json.loads(raw[start : end + 1])
            summary = str(obj.get("summary") or "").strip()
            inds = obj.get("industries")
            if summary and isinstance(inds, list) and inds:
                cleaned: list[dict[str, Any]] = []
                for it in inds[:4]:
                    if isinstance(it, dict) and it.get("name"):
                        try:
                            pct = max(0, min(100, int(float(it.get("pct", 70)))))
                        except (TypeError, ValueError):
                            pct = 70
                        cleaned.append({
                            "name": str(it["name"])[:40],
                            "pct": pct,
                            "why": str(it.get("why") or "")[:30],
                        })
                if cleaned:
                    return {"summary": summary, "industries": cleaned}
    except Exception:
        logger.warning("MBTI 结论生成解析失败，回退内置行业表", exc_info=True)

    fb = _FALLBACK_INDUSTRY.get(type_code) or _FALLBACK_INDUSTRY.get("INTJ")
    fallback_summary = (
        f"你测得为 {type_code}（{_TYPE_FULL.get(type_code, '')}）。"
        "倾向于有计划地发挥自身优势，建议优先考虑与性格匹配的行业并持续积累可迁移能力。"
    )
    return {"summary": fallback_summary, "industries": list(fb or [])}
