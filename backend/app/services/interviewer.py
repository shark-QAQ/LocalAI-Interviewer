from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import logging
import random
import re
from typing import Any

from ..config import settings
from ..database import generate_id, get_db, now_iso, row_to_dict
from .. import embed_client
from ..llm_client import llm_generate, llm_generate_stream
from ..vector_store import vector_store
from .evaluator import (
    finalize_answer_eval,
    finalize_intro_eval,
    generate_report,
    parse_json_object,
)
from .scope import CATEGORIES, CAT_LABELS, build_round_plan
from .resume_code_map import build_mapping_note, map_for_name

logger = logging.getLogger(__name__)

_INTERVIEWER_PERSONA = """你是一位资深技术面试官。基于候选人的简历技能、简历项目经历、项目代码库和对话历史，进行一场真实的技术面试。

面试流程：
1. 开场先简短自我介绍（我是XX，今天负责你的技术面试），请候选人做自我介绍
2. 之后：评估候选人最近一条回答，并基于简历与代码库提出下一道技术问题
3. 每次只问一个问题，问题要具体、有深度
4. 如果上次回答不完整，先追问再出新题
5. 根据候选人的工作年限与所选难度调整深浅（Junior基础些，Senior/地狱要深入源码）
6. 问题要覆盖不同技能点，避免重复同一话题
"""

# 开场白使用的系统提示：直接输出要说的话本身
_INTERVIEW_SYSTEM = _INTERVIEWER_PERSONA + """
（当前是开场白环节）直接输出你要说出口的话本身。
不要输出任何思考过程、分析、解释、JSON、代码示例或引导词。"""

# 技术问答轮次的系统提示：一次调用同时产出“评分 + 下一题”
_TURN_SYSTEM = _INTERVIEWER_PERSONA + """
（当前为候选人刚回答完一条技术题，需要“给本条回答打分”并“提出下一题”）请严格只输出一个 JSON 对象，不要输出任何其它文字、思考、解释或代码：
{"correctness": <1-10>, "off_topic": <true或false>, "critical_error": <true或false>, "depth": <1-10>, "logic": <1-10>, "integrity": <1-10>, "comment": "<60~90字评语，须引用本条回答证据>", "next_question": "<下一道问题全文>"}

要求：
1. 【切题与正确性先行】打分前先在内部对照“上一条问题”与“本题参考要点”（提示中给了才对照），判断：本条回答有没有真的回答所问的问题？结论/机制是否正确，有无关键错误？
   · correctness：对该问题的切题度与正确性。6 及以上＝基本答对所问、无硬伤；4-5＝沾边但偏题、有明显缺失或部分说错；1-3＝答非所问、明显跑偏或结论错误。
   · off_topic：true＝回答与本问几乎无关（泛泛复述别的、没答到点子上）。
   · critical_error：true＝回答存在关键概念/结论性错误，或与参考要点明显相悖。
   只要 off_topic 或 critical_error 为 true，或回答实质为空，depth/logic/integrity/correctness 一律不得超过 3，并让 comment 说清错在哪、缺什么。
2. 评分维度：correctness=切题与正确；depth=技术深度（原理/源码/性能）；logic=逻辑清晰；integrity=方案完整（边界/异常/扩展）。评分与 comment 只针对“最近一条回答”，按给定难度把握松紧。
3. next_question：给候选人的下一道技术问题（回答不完整就追问，完整则换一个新的技能点/角度出题）。
   必须是直接对候选人发问的完整问句，以中文问号“？”结尾；不要包含标题、编号、加粗、“问题如下/下一题/追问”等引导文字，也不要写答案解析。
4. 覆盖要求：优先考察本场尚未覆盖的技能点；严禁与“本场已考话题”重复或相近（同一知识点换个问法也算重复）。
5. 多样性：严格按提示中的“难度考察方式”与“出题类型”出题，让题型、考察角度、问句形态都与前几题明显不同；不要每轮都用“请描述/请谈谈……”这类同一句式开头。
6. 若提示中标注“本轮是最后一轮，不需要下一题”，则只输出评分字段与 comment，省略 next_question。
7. 类别纪律：仅“项目深挖(project)”允许围绕候选人自己的代码库/简历项目实现深挖；“技术栈原理(stack)、场景与系统设计(design)、通用CS基础(basics)”必须脱离候选人的私有代码，面向通用原理、其技术栈方向或岗位方向出题，严禁要求其复述具体文件/函数实现。
8. 可选的附加字段：category 填本题实际所属类别（project/stack/design/basics，尤其当本题是沿用上一题做同类别追问时）；topic 填本题考察的具体主题/技能；若本题是对上一题的“同主题追问”，请如实填 is_followup: true（否则省略）。无法判断时可省略，不影响评分。
9. 评语必须忠于回答原文：候选人已明确提到的方面（安全性、用户友好性、性能、边界、异常等）必须正面认可；若要提建议，只能说“还可就某点再深入/补数据/给反例”，严禁写成“没有提到/未涉及/缺乏……”这类与原文相悖的否定。只有确实完全没覆盖的点才可指缺失，并点名具体缺什么。不要用“回答全面但可更深入探讨某方面”这类空泛套话；要建议就落到具体可补的内容上。
10. 严格评分（据此校准，禁止凭感觉给分，禁止把分挤在 7-9）：
   · 切题正确 correctness：1-3 答非所问/结论错误；4-5 沾边但漏答核心或部分出错；6-7 主答案正确但缺关键限定/边界；8-9 答对所问且要点齐；10 完全命中并给出更优角度。
   · 深度 depth：1-3 概念错误或泛泛无机制；4-5 方向对但讲不清机制或关键点明显缺失；6 讲出主机制但缺关键边界；7-8 机制+边界+“为什么/取舍”，能落到实现、数据或两案对比；9-10 底层实现/量化/可复现，明显超出常规。
   · 逻辑 logic：1-4 混乱/重复/前后矛盾；5-6 有条理但主次不分；7-8 主次分明、因果清楚；9-10 严整、环环相扣、能自证。
   · 完整 integrity（边界/异常/扩展）：1-4 缺关键边界或后果；5-6 只提主要边界、少异常/回滚/扩展；7-8 边界+异常/回滚/扩展基本覆盖；9-10 全链路含可验证步骤与兜底。
   · 难度校准：初级答到 7 已是优；高级/地狱若泛泛或只给常规方案应给 4-6，只有源码级/量化/可证才给 ≥8。
   · 证据：评分与评语必须引用本条回答里的具体内容（“你已提到 X，但缺 Y”）；引不出证据的点不能给高维分。
   · 依据唯一性：只依据候选人“本轮实际输入的文字”打分，严禁把参考要点/简历/资料/题库或对话历史内容当作他已经说过的；内容极少或空泛时对应维度必须给低分（如只写了句问候/寒暄，各维不得超过 4），不得因简历好看或参考要点而抬分。"""

# 开场自我介绍环节的系统提示：一次调用同时产出“自我介绍点评 + 第一道技术题”
_INTRO_TURN_SYSTEM = _INTERVIEWER_PERSONA + """
（当前为候选人刚做完自我介绍、还没有技术题）请严格只输出一个 JSON 对象，不要输出任何其它文字、思考、解释或代码：
{"clarity": <1-10>, "substance": <1-10>, "fit": <1-10>, "off_topic": <true或false>, "comment": "<60~90字评语，须引用其介绍里的具体内容>", "next_question": "<第一道技术问题全文>"}

要求：
1. 自我介绍不是代码题，禁止用“技术深度/逻辑/完整性”给它打代码分。请用三个非技术维度点评：
   clarity=表达清晰，substance=内容充实（背景/项目/技术栈/亮点），fit=与目标岗位和简历技能的匹配。
   comment 指出介绍里可补充的方向。
2. next_question：第一道题是“项目深挖”热身题——基于简历项目经历与代码库生成，直接对候选人发问，以中文问号“？”结尾，
   只放问题本身，不要标题/编号/“问题如下”等引导文字；尽量选一个能带出后续多技能点的话题。
3. 【切题/有效内容先行】先判断这段自我介绍是否真的在“介绍自己”——有无实际的背景、项目、技术或经历，与目标岗位/技术面试是否相关：
   · off_topic=true：内容与岗位/技术面试几乎无关（例如闲聊日常生活、纯寒暄、复读套话而无实质），或基本没提供任何可评的信息。
   只要 off_topic=true，或介绍过短（几个字），clarity/substance/fit 一律不得超过 3。
4. 严格评分（据此校准，禁止凭感觉给分、禁止把分挤在 7-9）：
   · clarity 表达：1-4 冗长绕口、主次不分或跑题；5-6 能听懂但结构平淡、重点不清；7-8 简练有条理、先结论后展开；9-10 清晰凝练、层次分明、节奏得当。
   · substance 内容：1-4 空洞/只报流水账，缺背景/职责/技术点；5-6 讲了几件事但都浅；7-8 背景+职责+技术栈/亮点，且能落到项目细节；9-10 有量化成果、关键职责与技术深度，明显充实。
   · fit 匹配：1-4 与目标岗位/简历技能无关或泛泛；5-6 沾边但未扣住岗位要求；7-8 能点明与目标岗位相关的核心技能与经历；9-10 论证充分、让人明确感到“就是这个人”。
   · 证据：评分与评语必须引用其介绍里的具体内容（“你讲了 X，但没说明你的职责/量化/技术点 Y”）；引不出证据的不给高维分。
   · 依据唯一性：只依据候选人“自我介绍里实际说的话”打分，严禁把简历/题库/历史对话内容当作他已经说过的；内容极少或空泛时对应维度必须给低分（如只写了句问候/寒暄，substance、clarity 不得超过 4），不得因简历好看而抬分。"""

# 点击“查看答案”时单独生成的标准参考答案提示词（简练、覆盖面广、直击要害）
_REFERENCE_SYSTEM = """你是资深后端/系统设计面试官。为题目写一份“参考要点”，供人快速对照。

硬性规则（违反即重写）：
1. 只输出 3~6 个短要点，每个要点 1~2 句，直接说“怎么做 / 为什么 / 关键边界”。
2. 禁止任何铺垫：不要“这道题考察…/好的/首先”，不要复述题目；禁止结尾总结段（如“通过上述措施提升了性能”）和一切空话。
3. 覆盖面：核心方案、关键边界/异常、易踩的坑各至少点一句。
4. 若下方附了真实代码/资料片段，必须结合其中的真实机制作答，不得编造题目来源里不存在的装饰器、API 或库。
5. 全文 150~250 字。直接开始列要点，不要任何多余文字。"""

# 参考答案风格版本：改动生成规范后，旧缓存自动失效并重新生成
_REF_VERSION = 3

# 知识库检索结果 → 自然语言（归一化）总结
_KB_SUMMARY_SYSTEM = """你是代码/资料检索助手。用户搜了一个关键词，下面是检索命中的片段。请把它整理成自然语言反馈给用户。

要求：
1. 直接给出清晰说明，把片段归纳成通顺的自然语言（相关机制如何实现、在哪些代码/资料/文件里体现、彼此关系），不要把原始代码整段贴出来。
2. 引用用「来源 · 文件/函数」标注，简洁、不超过两处/条。
3. 主动忽略压缩/混淆/自动生成的噪音片段（如 minified JS、单一字母函数名、纯打包产物）。
4. 结构紧凑（约 150~250 字），开头第一句先给结论。
5. 确实没找到相关内容时，如实说明“未找到明显相关内容，可换关键词”，不要编造。"""

# 兜底清洗时识别“标题式引导语”的标记；仅在文本前半段命中才裁剪
_QUESTION_HEAD_MARKERS = [
    "技术问题：", "技术问题:", "题目如下：", "题目如下",
    "题目：", "题目:", "问题如下：", "问题如下",
    "问题：", "问题:", "提问：", "提问:",
]

_DIFFICULTY_LABELS = {"junior": "初级", "mid": "中级", "senior": "高级", "hell": "地狱"}

_DIFFICULTY_GUIDES = {
    "junior": "初级：考基础概念、常见 API 与常规流程；问题直白、不设陷阱，必要时提示候选人分步作答。",
    "mid": "中级：考原理与边界；让候选人结合自己的项目说明机制、适用场景与常见坑。",
    "senior": "高级：深入源码与架构；考底层实现、性能/一致性/容错的权衡与可扩展性设计，要求结合真实代码细节。",
    "hell": "地狱：极端并发与故障场景；要求源码级细节、复合故障归因、多方案对比与取舍论证，连续追问。",
}

# 每档难度更强的“尺度锚点”：问题深度 + 给分松紧，拉开档位差距
_DIFFICULTY_SCALE = {
    "junior": (
        "入门档：只出直白的基础题——概念、常见 API、单步流程，一个点一层意思；"
        "不要默认候选人懂源码或复合故障。答清基本要点即可拿高分，别故意刁难。"
    ),
    "mid": (
        "进阶档：每题都要能挖到“原理＋怎么用＋适用/不适用＋一个常见坑”这一层；"
        "只答对方向、讲不到机制或边界，一律只给中低分。"
    ),
    "senior": (
        "高级档：只问能挖到实现/架构层的题——底层数据结构、并发、一致性、性能权衡、扩展设计；"
        "只讲表象或泛泛而谈判不及格，答案必须落到真实代码、量化数字与取舍论证上。"
    ),
    "hell": (
        "地狱档：构造并发极限、分布式故障、极端数据等复合场景，要求给出完整处理链路、"
        "多方案取舍论证与可验证步骤，并继续找漏洞追问反例；给出常规/表面答案即判低分，"
        "只有近乎源码级且可验证的答案才给高分。"
    ),
}

# basics 类别的固定技能标签（不消耗简历技能轮转游标）
_GENERIC_CS_SKILL = "通用计算机基础"

# 各类别的“取材边界 + 考法”，随每轮 prompt 注入，约束模型不要拿候选人私有代码出知识题
_CAT_INSTRUCTIONS = {
    "project": (
        "出题类别＝项目深挖：围绕候选人的简历项目 / 代码库真实实现发问（可结合下方知识库片段求证）。"
        "若上一题属本类别且回答不完整，先就同一实现继续追问；已完整则换该项目另一模块或另一技能点出题。"
    ),
    "stack": (
        "出题类别＝技术栈原理：就候选人某项核心技术栈（简历技能 / 项目主语言 / 项目里用到的框架中间件）考原理层面——"
        "底层机制、实现原理、适用与不适用、与相近技术的对比与取舍。题目应能脱离其代码独立成立，"
        "严禁让候选人复述自己代码库里具体文件/函数的实现，也不要问“你的代码里是怎么写的”。"
    ),
    "design": (
        "出题类别＝场景与系统设计：给出贴近候选人技术方向与量级的场景，考需求拆解、架构与技术选型、数据模型/存储、"
        "关键流程与接口、扩展性与瓶颈权衡、边界与异常。以“如果是你来负责，会怎么设计/重构/排查”的角度发问，"
        "不要求逐行引用其私有代码实现。"
    ),
    "basics": (
        "出题类别＝通用CS基础：考不依赖具体项目/代码库的通用考点，从候选人方向中挑本场尚未覆盖的角度："
        "数据结构与算法、操作系统、计算机网络、数据库原理、并发与多线程、设计模式、语言与编译基础。"
        "例子可以贴近候选人方向，但考察对象必须是通用原理而非其私有实现。"
    ),
}

# 各“发问侧重”（会话级滑杆选择）下，面试官提问的口吻基调——让不同侧重下问句听得出来差别
_FOCUS_VOICE = {
    "depth": "穷根问底——直切项目实现的细节、取舍与边界，多以追问推进；措辞凝练、单刀直入。",
    "balanced": "不偏不倚——先给一句情境或前提，再落到要问的点上；从容清楚，深浅适中。",
    "breadth": "循理而问——从一个概念、原理或场景聊开，留白引导展开；点到即止，便于发挥。",
}

# 所有问句统一的行文要求：文雅直白，不晦涩
_QUESTION_STYLE = (
    "问句行文要求：文雅而直白——用词常见、句意明白、一次只问一件事；"
    "不引生僻典故，不做文言倒装，宁可平实浅显，也不要晦涩绕口。"
)

# 面试官开口（自我介绍/过渡语）的统一讲话风格：有书卷气但仍一听就懂
_SPEAK_STYLE = (
    "讲话风格要求：文雅、带书卷气而直白——措辞雅正、句式自然，可酌用“君、宜、不妨”等轻量古语点缀；"
    "务必让现代人一听即懂，不堆砌生僻字、不做文言倒装、不用网络流行语。"
)

# 各侧重下的“考官人设”，让开场自我介绍也随选择明显不同
_FOCUS_IDENTITY = {
    "depth": "考官人设：严苛而严谨的“考究先生”。开场自陈将追本溯源，就你项目的细节、取舍与边界层层追问，请以真实实现相告。",
    "balanced": "考官人设：温雅持中的面试官。开场自陈本场既问代码与项目，也考原理与见识，不偏不倚，从容切磋。",
    "breadth": "考官人设：博闻广识的“问辩先生”。开场自陈多问技术原理与通识基础，点到即止，请你从容展开。",
}

_DEFAULT_NEXT_QUESTION = "请结合你在简历里写到的项目，挑一个最有技术含量的功能，讲讲它的设计思路，以及你在实现中遇到并解决的一个难题。"

# 各难度对应的“考察方式要求”，拉开难度层级，避免所有题一个模子
_DIFFICULTY_QUESTION = {
    "junior": "基础题：问概念理解、常见 API/用法或一个简单场景的小实现。问题直白、单层，不要考底层源码细节或复合故障，可给候选人口头提示。",
    "mid": "进阶题：让候选人结合简历/项目里的真实场景，讲清某机制的“原理 + 适用/不适用 + 取舍 + 一个常见坑”；可以要求对比两个相近方案的差异。",
    "senior": "深水题：要求深入到底层实现与架构：让候选人解释机制背后的数据结构/并发/内存/一致性等权衡，或抛出扩展点/量级放大，追问“如果更大/更极端会怎样”；可要求溯源到项目源码实现。",
    "hell": "地狱题：构造高难场景——并发极限、分布式故障、复合原因、极端数据等；要求给出完整处理链路、多方案对比与取舍论证、可验证步骤，并可继续追问该方案在更坏情况下的漏洞。",
}

# 按难度开放的“题型”，出题时轮换，让问题形态有差异
_QUESTION_TYPES = {
    "junior": ["概念理解与常见用法", "简单场景的小实现/小选型"],
    "mid": ["结合项目讲原理与机制", "两方案对比与取舍", "边界条件与常见坑", "从简历项目举证"],
    "senior": ["底层源码/数据结构与算法", "架构权衡与扩展设计", "故障/异常根因排查", "量级或并发放大后的设计"],
    "hell": ["分布式/高并发极限故障", "复合原因排查与处理链路", "多方案对比并论证取舍", "源码级深挖与连续追问"],
}

# 模型偶发输出“？？”这类重复问号，统一规整为单个
_TRAILING_QMARK = re.compile(r"[？?]{2,}$")

# 常见问句开头用字：用于识别“0好的/0在…”里那个裸前导 0 是残留而非数字
_QUESTION_START_IDEOGRAPHS = set("好在请关基于下我你这针同首第如当对看的想聊假设现简总先说讲")


def _drop_leading_zero_artifact(text: str) -> str:
    """去掉模型偶发以“0好的/0在…”开头的前导 0，避免问句开头多一个字符。

    只处理“单个 0 + 常见问句开头字”这一残留形态，不影响“10万QPS”“0到1”这类真实数字。
    """
    m = re.match(r"^0\s*(?=[一-鿿])", text)
    if m and m.end() < len(text) and text[m.end()] in _QUESTION_START_IDEOGRAPHS:
        return text[m.end():]
    return text


def _finalize_question_text(text: str) -> str:
    text = text.strip()
    text = _drop_leading_zero_artifact(text)
    text = _lstrip_junk(text)
    return _TRAILING_QMARK.sub(lambda m: m.group(0)[-1], text.strip())


# 会话级状态（单进程内存即可，重启清空）
_session_cursor: dict[str, int] = {}          # 技能轮转游标，保证覆盖广度
_type_cursor: dict[str, int] = {}             # 题型轮转游标，保证问法多样
_used_sources: dict[str, list[str]] = {}      # 本场已引用过的知识片段指纹，避免重复出题取材


def _next_skill(skills: list[str], session_id: str) -> str:
    """轮转选择技能：每个技能先被问过一轮后再循环，覆盖更均匀。"""
    if not skills:
        return "通用技术"
    idx = _session_cursor.get(session_id, 0) % len(skills)
    _session_cursor[session_id] = idx + 1
    return skills[idx]


def _next_question_type(difficulty: str, session_id: str) -> str:
    """按难度轮转题型，让每道题的形态不同。"""
    types = _QUESTION_TYPES.get(difficulty, _QUESTION_TYPES["mid"])
    idx = _type_cursor.get(session_id, 0) % len(types)
    _type_cursor[session_id] = idx + 1
    return types[idx]


def _remember_sources(session_id: str, keys: list[str]) -> None:
    if not keys:
        return
    seen = _used_sources.setdefault(session_id, [])
    for k in keys:
        if k not in seen:
            seen.append(k)
    # 只保留最近的引用，防止长时间会话无限膨胀
    if len(seen) > 1200:
        del seen[: len(seen) - 600]


def _forget_session(session_id: str) -> None:
    _session_cursor.pop(session_id, None)
    _type_cursor.pop(session_id, None)
    _used_sources.pop(session_id, None)
    _QUESTION_VECS.pop(session_id, None)
    _followup_used.pop(session_id, None)


# 参考答案生成去重锁（后台预生成与点击请求可能并发）
_ref_locks: dict[str, asyncio.Lock] = {}


def _lstrip_junk(text: str) -> str:
    """去掉开头空白以及 Markdown/口语里的非内容符号（**、>、-、破折号等）。"""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace() or ch in "-–—*#`~|>·•。，、；：:'\"“”‘’…．.()（）【】[]":
            i += 1
            continue
        break
    return text[i:]


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text[3:]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


# 语义去重阈值：与历史某题余弦相似度达到该值视为“近似重复”
_DUP_COS_THRESHOLD = 0.80
# 历史题缓存达到该数量后才做语义去重（前几轮题少，跳过比对更快）
_DUP_MIN_CACHE = 3

# 每题文本向量缓存（会话 -> 题号 -> 向量），同一会话内热复用，避免重复嵌入
_QUESTION_VECS: dict[str, dict[int, list[float]]] = {}

# 追问节制：会话级已追问次数（重启清空即可）；上限 = ⌊总轮数/3⌋，且不得少于 1 次
_followup_used: dict[str, int] = {}

# 候选人“无法回答/没做过”的常见说法：命中后禁止再追问该主题
_UNANSWER_MARKERS = (
    "不会", "不知道", "不清楚", "不了解", "没做过", "没接触过", "没有接触", "没有做过",
    "没经验", "没有经验", "答不上", "想不出", "记不清", "忘了", "不太会", "不擅长",
    "没法回答", "无法回答", "不能回答", "无能为力", "抱歉", "暂不了解", "未涉及",
)


def _looks_unable(text: str | None) -> bool:
    return any(k in (text or "") for k in _UNANSWER_MARKERS)


def _followup_budget(session: dict[str, Any]) -> int:
    return max(1, int((session.get("max_rounds") or 8) // 3))


def _question_cos(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def _embed_question(text: str) -> list[float] | None:
    try:
        embs = await embed_client.embed([text])
        return embs[0] if embs else None
    except Exception:
        return None


# 文本判重的归一化与阈值：去标点/空格后比较，无内存/模型依赖，重启也生效
_DUP_TEXT_RATIO = 0.90
_TXT_PUNCT_RE = re.compile(r"[，。、；：！？?!（）()\[\]{}<>《》\"'“”‘’\s\-_]")


def _norm_question_text(t: str) -> str:
    return _TXT_PUNCT_RE.sub("", (t or "")).lower()


def _text_dup_round(
    history_messages: list[dict[str, Any]],
    question_text: str,
    limit: int = 10,
) -> int | None:
    """基于“已问题目原文”的判重：去标点/空白后完全一致或高度相似即命中。

    逐字对比 + difflib 相似度都来自持久化的历史消息，不依赖进程内存
    （旧的向量去重 _QUESTION_VECS 在后端 reload 后会被清空，是重复复发的根因）。
    返回最早命中的题号。
    """
    text = _norm_question_text(question_text)
    if len(text) < 10:
        return None
    hits: list[tuple[float, int]] = []
    rounds = [m for m in history_messages if m["role"] == "assistant" and (m.get("round_num") or 0) > 0]
    rounds = rounds[-limit:]
    for m in rounds:
        other = _norm_question_text(m.get("content"))
        if len(other) < 10:
            continue
        if other == text:
            return m.get("round_num")
        ratio = difflib.SequenceMatcher(None, text, other).ratio()
        if ratio >= _DUP_TEXT_RATIO:
            hits.append((ratio, m.get("round_num") or 0))
    if not hits:
        return None
    hits.sort(key=lambda x: x[0], reverse=True)
    return hits[0][1]


async def _dup_round(
    history_messages: list[dict[str, Any]],
    question_text: str,
    session_id: str,
    qvec: list[float] | None = None,
) -> int | None:
    """若 question_text 与历史某题“逐字相同或语义近似”，返回最早命中那轮的题号；否则 None。

    qvec 可传入已算好的本题向量（调用方在语义去重开启时先嵌入一次，检查/缓存共用，省一次调用）。
    """
    text = re.sub(r"\s+", "", question_text or "").strip("，。？！?！ ")
    if len(text) < 10:
        return None

    # 1) 逐字相同
    for m in history_messages:
        if m["role"] != "assistant" or (m.get("round_num") or 0) <= 0:
            continue
        other = re.sub(r"\s+", "", m.get("content") or "").strip("，。？！?！ ")
        if other == text:
            return m.get("round_num")

    # 2) 语义近似（只对比已缓存的历史题向量）
    cache = _QUESTION_VECS.get(session_id)
    if not cache:
        return None
    if qvec is None:
        qvec = await _embed_question(question_text)
    if qvec is None:
        return None
    best_round: int | None = None
    best_sim = 0.0
    for rnum, v in cache.items():
        sim = _question_cos(qvec, v)
        if sim > best_sim:
            best_sim, best_round = sim, rnum
    return best_round if best_sim >= _DUP_COS_THRESHOLD else None


def _clean_question_text(raw: str) -> str:
    """把模型输出的题目文本整理成“只含问题本身”。

    首选把整个输出当 JSON 解析（next_question/question 字段）；失败时启发式掐前缀与尾注。
    """
    text = (raw or "").strip()
    if not text:
        return ""

    # 若是 JSON，直接取题目字段（可能夹在 {"next_question": ...} 里）
    result = ""
    obj = parse_json_object(text)
    if obj is not None:
        q = obj.get("next_question") or obj.get("question") or obj.get("问题")
        if isinstance(q, str):
            cleaned = _lstrip_junk(q.strip())
            if cleaned:
                result = cleaned

    if not result:
        # —— 兜底：启发式清理 ——
        text = _strip_code_fence(text)
        text = _lstrip_junk(text)

        last_q = max(text.rfind("？"), text.rfind("?"))
        if last_q < 0:
            # 没有问号，不像问句；保守返回
            result = text or raw.strip()
        else:
            text = text[: last_q + 1]

            # 掐掉前半段出现的“问题如下/题目：/技术问题：”等标题式引导语
            half = len(text) // 2
            cut = -1
            for marker in _QUESTION_HEAD_MARKERS:
                idx = text.rfind(marker)
                if 0 <= idx <= half:
                    cut = max(cut, idx + len(marker))
            if cut > 0:
                text = _lstrip_junk(text[cut:])
            result = text

    return _finalize_question_text(result)


def _build_history_context(messages: list[dict[str, Any]]) -> str:
    recent = messages[-(settings.max_history_rounds * 2):]
    lines: list[str] = []
    for m in recent:
        if m["role"] not in ("user", "assistant"):
            # 系统内部评估（含自我介绍点评）不是面试官/候选人的话，不进上下文，避免污染提问
            continue
        role_label = "候选人" if m["role"] == "user" else "面试官"
        lines.append(f"[{role_label}]: {m['content'][:200]}")
    return "\n".join(lines) if lines else "（无历史对话）"


def _load_session(session_id: str) -> dict[str, Any]:
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM interview_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if row is None:
        raise ValueError("会话不存在")
    return row_to_dict(row)


def _load_resume(resume_id: str | None) -> dict[str, Any] | None:
    if not resume_id:
        return None
    with get_db() as db:
        row = db.execute(
            "SELECT parsed_data, skills, years_exp FROM resumes WHERE id = ?", (resume_id,)
        ).fetchone()
    if row is None:
        return None
    d = row_to_dict(row)
    try:
        d["parsed_data"] = json.loads(d["parsed_data"] or "{}")
    except Exception:
        d["parsed_data"] = {}
    try:
        d["skills"] = json.loads(d["skills"] or "[]")
    except Exception:
        d["skills"] = []
    return d


def _build_resume_context(resume: dict[str, Any] | None) -> str:
    """把简历里能用于出题的素材（年限、项目经历）整理成提示词片段。"""
    if not resume:
        return "（未上传简历）"
    parsed = resume.get("parsed_data") or {}
    lines: list[str] = []
    years = parsed.get("years_of_experience")
    if not years:
        years = resume.get("years_exp")
    if years:
        lines.append(f"工作年限：{years} 年")
    projects = parsed.get("projects") or []
    for p in projects[:8]:
        name = (p.get("name") or "").strip()
        desc = (p.get("description") or "").strip()
        if name:
            lines.append(f"- {name}" + (f"：{desc[:150]}" if desc else ""))
    if not lines:
        return "（简历未提取到工作年限/项目经历）"
    return "\n".join(lines)


def _completed_projects() -> list[dict[str, Any]]:
    """知识库中所有已完成索引的代码库。"""
    with get_db() as db:
        rows = db.execute(
            """SELECT id, name FROM projects
               WHERE index_status = 'completed' AND chunk_count > 0
               ORDER BY last_indexed_at DESC"""
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def _completed_materials() -> list[dict[str, Any]]:
    """全局资料库中已完成向量化的资料（含文件夹单元）。"""
    with get_db() as db:
        rows = db.execute(
            """SELECT id, name FROM materials
               WHERE index_status = 'completed' AND chunk_count > 0
               ORDER BY created_at DESC LIMIT 20"""
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def _selected_project_ids(session: dict[str, Any]) -> list[str]:
    """本场会话勾选的代码库项目 id（无则退回单一主项目）。"""
    ids: list[str] = []
    try:
        ids = [p for p in json.loads(session.get("project_ids") or "[]") if p]
    except Exception:
        ids = []
    if not ids and session.get("project_id"):
        ids = [session["project_id"]]
    return ids


def _session_knowledge_sources(session: dict[str, Any]) -> list[dict[str, Any]]:
    """面试出题/知识库查询命中的来源 = 本场范围：

    会话勾选的代码库（若勾选项都失效则回退为全部已完成代码库）
    + 该简历 + 全部已完成资料。
    """
    sources: list[dict[str, Any]] = []
    picked: list[dict[str, Any]] = []
    pids = _selected_project_ids(session)
    if pids:
        marks = ",".join("?" for _ in pids)
        with get_db() as db:
            picked = [
                row_to_dict(r)
                for r in db.execute(
                    f"""SELECT id, name FROM projects
                        WHERE id IN ({marks}) AND index_status = 'completed' AND chunk_count > 0""",
                    tuple(pids),
                ).fetchall()
            ]
    if not picked:
        picked = _completed_projects()
    for p in picked:
        sources.append({"id": p["id"], "prefix": "project_", "label": f"项目·{p['name']}"})
    if session.get("resume_id"):
        sources.append({
            "id": session["resume_id"],
            "prefix": "resume_",
            "label": "简历",
        })
    for m in _completed_materials():
        sources.append({"id": m["id"], "prefix": "material_", "label": f"资料·{m['name']}"})
    return sources


def _code_entries_for_session(session: dict[str, Any], code_names: list[str]) -> list[dict[str, Any]]:
    """从本场勾选的已完成代码库中，挑出属于某简历项目映射的那些代码库条目。"""
    wanted = {c.lower() for c in (code_names or []) if c}
    pids = _selected_project_ids(session)
    if not pids or not wanted:
        return []
    marks = ",".join("?" for _ in pids)
    with get_db() as db:
        rows = [
            row_to_dict(r)
            for r in db.execute(
                f"""SELECT id, name FROM projects
                    WHERE id IN ({marks}) AND index_status = 'completed' AND chunk_count > 0""",
                tuple(pids),
            ).fetchall()
        ]
    return [{"id": r["id"], "name": r["name"]} for r in rows if r["name"].lower() in wanted]


def _selected_code_projects(session: dict[str, Any]) -> list[dict[str, Any]]:
    """本场勾选的、已完成索引的代码库项目（含 id/name/language）。"""
    pids = _selected_project_ids(session)
    if not pids:
        return []
    marks = ",".join("?" for _ in pids)
    with get_db() as db:
        rows = [
            row_to_dict(r)
            for r in db.execute(
                f"""SELECT id, name, language FROM projects
                    WHERE id IN ({marks}) AND index_status = 'completed'""",
                tuple(pids),
            ).fetchall()
        ]
    return rows


def _selected_code_names(session: dict[str, Any]) -> list[str]:
    """本场勾选代码库的名字（用于提示词里划“可深挖范围”）。"""
    return [r["name"] for r in _selected_code_projects(session)]


def _intro_anchors(session: dict[str, Any]) -> list[dict[str, Any]]:
    """开场首题的候选锚点：简历项目经历 + 本场选择的代码库项目。

    供开场随机抽一个，避免首题永远落在同一个项目（如只落在简历首条经历上）。

    简历项目经历**只有映射到本场勾选的代码库**时才进候选池：否则会出现
    “勾了 A 项目（如 secops-platform），开场却问 B 项目（如仅存在于简历的 Aeye）”的错位。
    """
    cands: list[dict[str, Any]] = []
    resume = _load_resume(session.get("resume_id"))
    parsed = (resume or {}).get("parsed_data") or {}
    sel_ids = _selected_project_ids(session)
    sel_lower: set[str] = set()
    if sel_ids:
        marks = ",".join("?" for _ in sel_ids)
        with get_db() as db:
            sel_lower = {
                (r["name"] or "").lower()
                for r in db.execute(
                    f"""SELECT name FROM projects
                        WHERE id IN ({marks}) AND index_status = 'completed'""",
                    tuple(sel_ids),
                ).fetchall()
            }
    has_selection = bool(sel_lower)
    for p in (parsed.get("projects") or [])[:8]:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        if has_selection:
            # 只保留“简历项目 → 勾选代码库”能对上号的经历
            mapped = {m.lower() for m in map_for_name(name)}
            if not mapped or not (mapped & sel_lower):
                continue
        cands.append({
            "kind": "resume", "name": name[:24],
            "id": session.get("resume_id") or "",
        })

    for r in _selected_code_projects(session):
        cands.append({
            "kind": "project", "id": r["id"],
            "name": r["name"], "language": r.get("language") or "",
        })
    return cands


def _format_knowledge(results: list[dict[str, Any]], snippet: int = 260) -> str:
    lines: list[str] = []
    for r in results:
        sub = str(r.get("file_path") or r.get("function_name") or "")[:60]
        head = r["source"] + (f" · {sub}" if sub else "")
        lines.append(f"[{head}]\n{str(r['text'])[:snippet]}")
    return "\n\n".join(lines)


def _source_key(
    src: dict[str, Any], file_path: str, function_name: str, text: str
) -> str:
    """知识片段指纹：来源集合 + 文件/函数 + 片段摘要，用于去重/追溯。"""
    sig = hashlib.md5(str(text)[:120].encode("utf-8", "ignore")).hexdigest()[:8]
    return f"{src.get('prefix', '')}{src.get('id', '')}::{file_path}::{function_name}::{sig}"


def _pick_source_meta(results: list[dict[str, Any]], cap: int = 3) -> list[dict[str, str]]:
    """从实际用到的片段里挑前几处作为“引用自哪里”展示。"""
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for r in results:
        fp = r.get("file_path") or r.get("function_name") or ""
        mark = (str(r.get("source", "")), str(fp))
        if mark in seen:
            continue
        seen.add(mark)
        out.append({
            "source": str(r.get("source", "")),
            "file_path": str(r.get("file_path", "")),
            "function_name": str(r.get("function_name", "")),
        })
        if len(out) >= cap:
            break
    return out


def _asked_context_text(messages: list[dict[str, Any]], cap: int = 5) -> str:
    """取本场最近几道面试官问句作为“已考话题”，防止重复同角度。"""
    qs = [
        str(m.get("content", "")).strip()
        for m in messages
        if m["role"] == "assistant" and (m.get("round_num") or 0) > 0 and m.get("content")
    ]
    qs = qs[-cap:]
    if not qs:
        return ""
    return "\n".join(f"{i + 1}. {q[:90]}" for i, q in enumerate(qs))


def _question_and_reference(
    messages: list[dict[str, Any]], round_num: int
) -> tuple[str, str]:
    """取某一轮题目的原文，以及（若已预生成）其参考答案——评分对照用。

    返回 (question, reference)。题目存在该轮 assistant 消息的 content 里，
    参考答案随题缓存在该消息的 score_json.reference。
    """
    for m in messages:
        if m.get("role") == "assistant" and (m.get("round_num") or 0) == round_num:
            q = str(m.get("content") or "").strip()
            ref = ""
            try:
                ref = str((json.loads(m.get("score_json") or "{}") or {}).get("reference") or "").strip()
            except Exception:
                ref = ""
            return q, ref
    return "", ""


def _question_skill_from_messages(
    messages: list[dict[str, Any]], round_num: int
) -> str:
    """取某轮题目当时记录的考察技能（随题落库在 assistant 的 score_json 里）。

    评分必须针对“这道题当初考的技能”，而不是下一题的技能。
    """
    for m in messages:
        if m["role"] == "assistant" and (m.get("round_num") or 0) == round_num:
            try:
                data = json.loads(m.get("score_json") or "{}")
                skill = data.get("skill") or ""
                if skill:
                    return str(skill)
            except Exception:
                pass
    return ""


def _question_cat_from_messages(
    messages: list[dict[str, Any]], round_num: int
) -> str:
    """取某轮题目当时记录的考察类别（随题落库在 assistant 的 score_json 里）。

    与技能一样，评分必须对齐“这道题当初的类别”，而非下一题的类别。
    """
    for m in messages:
        if m["role"] == "assistant" and (m.get("round_num") or 0) == round_num:
            try:
                data = json.loads(m.get("score_json") or "{}")
                cat = data.get("cat") or ""
                if cat in CATEGORIES:
                    return str(cat)
            except Exception:
                pass
    return ""


def _pick_skill_for_category(cat: str, skills: list[str], session_id: str) -> str:
    """按下一题类别挑选技能标签：basics 用固定标签且不推进技能轮转，
    其余类别沿用简历技能轮转，保证回到技能题时仍连贯。"""
    if cat == "basics":
        return _GENERIC_CS_SKILL
    return _next_skill(skills, session_id)


def _build_tech_stack_block(session: dict[str, Any], resume: dict[str, Any] | None) -> str:
    """候选人的技术栈背景（知识类题目的取材池），非 project 轮次用它替代代码 RAG。

    内容标注为“仅背景”，防止面试官据此要求候选人复述其具体代码实现。
    """
    parts: list[str] = []
    skills = (resume or {}).get("skills") or []
    parts.append("技能栈：" + ("、".join(skills[:20]) if skills else "（简历未提取到具体技能）"))

    project_ids: list[str] = []
    try:
        project_ids = [p for p in json.loads(session.get("project_ids") or "[]") if p]
    except Exception:
        project_ids = []
    if not project_ids and session.get("project_id"):
        project_ids = [session["project_id"]]
    if project_ids:
        marks = ",".join("?" for _ in project_ids)
        with get_db() as db:
            rows = db.execute(
                f"""SELECT name, language FROM projects
                    WHERE id IN ({marks}) AND index_status = 'completed'""",
                tuple(project_ids),
            ).fetchall()
        proj_lines = [
            f"{r['name']}" + (f"（{r['language'] or '语言未识别'}）" if r.get("language") else "")
            for r in [row_to_dict(x) for x in rows]
        ]
        parts.append("已选项目：" + ("；".join(proj_lines) if proj_lines else "（无已完成索引项目）"))

    parsed = (resume or {}).get("parsed_data") or {}
    desc_lines: list[str] = []
    for p in (parsed.get("projects") or [])[:6]:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        desc = (p.get("description") or "").strip()
        desc_lines.append(f"- {name}" + (f"：{desc[:80]}" if desc else ""))
    if desc_lines:
        parts.append("简历项目经历：\n" + "\n".join(desc_lines))

    parts.append("目标岗位：" + (session.get("target_position") or "未指定"))
    return "\n".join(parts)


async def retrieve_knowledge(
    sources: list[dict[str, Any]],
    query: str,
    per_source: int = 2,
    max_total: int = 8,
    exclude: set[str] | None = None,
) -> list[dict[str, Any]]:
    """用同一个 query 向量跨多个知识集合检索，按距离合并排序返回。

    各集合都用同一套 BGE-M3 余弦向量，距离可直接横向比较。
    exclude：本场已引用过的片段指纹，命中则跳过，让下一题换新素材、扩大覆盖面。
    """
    exclude = set(exclude or [])
    try:
        embeddings = await embed_client.embed([query])
    except Exception:
        logger.warning("embed failed for knowledge retrieval")
        return []
    if not embeddings:
        return []
    embedding = embeddings[0]

    found: list[dict[str, Any]] = []
    for src in sources:
        try:
            # 多取一些再按 exclude 过滤，保证过滤后仍有足够候选
            data = vector_store.query(
                src["id"],
                embedding,
                n_results=max(per_source * 3, 6),
                collection_prefix=src["prefix"],
            )
        except Exception:
            logger.debug("retrieve failed for %s %s", src.get("prefix"), src.get("id"))
            continue
        docs = (data.get("documents") or [[]])[0] or []
        metas = (data.get("metadatas") or [[]])[0] or []
        dists = (data.get("distances") or [[]])[0] or []
        picked = 0
        for i, text in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            dist = dists[i] if i < len(dists) else 1.0
            fp = str(meta.get("file_path", ""))
            fn = str(meta.get("function_name", ""))
            key = _source_key(src, fp, fn, str(text))
            if key in exclude:
                continue
            found.append({
                "key": key,
                "source": src["label"],
                "kind": src["prefix"].rstrip("_"),
                "text": str(text),
                "file_path": fp,
                "function_name": fn,
                "distance": round(float(dist), 4) if dist is not None else None,
                "_d": float(dist) if dist is not None else 1.0,
            })
            picked += 1
            if picked >= per_source:
                break
    found.sort(key=lambda r: r["_d"])
    return found[:max_total]


def _answer_for_eval(text: str | None) -> str:
    """评分必须基于完整回答：超长时保留头尾、只省略中段，
    避免候选人在末尾提到的关键点（安全、易用等）被截掉而误判“没答到”。"""
    s = (text or "").strip()
    if not s:
        return "（无）"
    if len(s) <= 2600:
        return s
    return s[:1600] + "\n……（中段省略，详见完整回答）……\n" + s[-1000:]


def _build_turn_prompt(
    session: dict[str, Any],
    skills: list[str],
    answered_round: int,
    is_intro: bool,
    is_last: bool,
    skill: str,
    answered_skill: str,
    answered_cat: str,
    next_cat: str,
    question_type: str,
    resume_skills: list[str],
    resume_ctx: str,
    stack_context: str,
    rag_context: str,
    history_ctx: str,
    asked_context: str,
    user_answer: str,
    intro_anchor: str = "",
    scope_note: str = "",
    answered_question: str = "",
    answer_reference: str = "",
) -> str:
    difficulty = session.get("difficulty", "mid")
    diff_label = _DIFFICULTY_LABELS.get(difficulty, "中级")
    diff_question = _DIFFICULTY_QUESTION.get(difficulty, _DIFFICULTY_QUESTION["mid"])
    target_position = session.get("target_position") or "未指定"
    max_rounds = session.get("max_rounds", settings.default_max_rounds)
    focus_tone = _FOCUS_VOICE.get(session.get("focus") or "balanced", _FOCUS_VOICE["balanced"])
    diff_scale = _DIFFICULTY_SCALE.get(difficulty, _DIFFICULTY_SCALE["mid"])

    if is_intro:
        progress = "开场白后的自我介绍环节（尚未出技术题，本轮将给出自我介绍点评并出第一道技术题）"
    else:
        progress = f"第 {answered_round}/{max_rounds} 轮技术问答（先给本条回答打分，再出下一题）"

    parts: list[str] = [
        f"面试进度：{progress}",
        f"难度：{diff_label}",
        f"目标岗位：{target_position}",
    ]

    # 评分对齐 + 同类别追问许可（仅技术轮）
    if not is_intro:
        answered_label = CAT_LABELS.get(answered_cat, "") or "未标注"
        parts.append(
            f"评分对齐：本条回答对应上一道题 —— 类别：{answered_label}"
            f" · 考察技能：{answered_skill or '（未记录）'}"
        )
        if answered_cat and next_cat and answered_cat != next_cat:
            parts.append(
                f"（若上一题回答不完整，可先在「{answered_label}」内追问一次再换方向；"
                f"回答完整则按下方本轮类别出新题）"
            )

        # 追问纪律：全场合计 ≤ ⌊总轮数/3⌋；候选人表明无法回答时禁止再追问该题
        if not is_last:
            sid = session.get("id") or ""
            used = _followup_used.get(sid, 0)
            budget = _followup_budget(session)
            discipline = (
                f"追问纪律：本场累计已追问 {used}/{budget} 次，全场合计不得超过 ⌊总轮数/3⌋；"
                "同一道题最多追问 1 次。"
            )
            if _looks_unable(user_answer):
                discipline += "候选人上一题已表明无法回答——立即停止追问该主题，转向其它方向出新题。"
            elif used >= budget:
                discipline += "追问名额已用尽——不要同主题追问，一律按本轮类别出新题。"
            else:
                discipline += "只有上一题“确实作答但明显不完整/浅”才可用一次追问名额；回答已较完整就换新方向。"
            parts.append(discipline)

        # 本条回答对应的题目原文 + 参考答案（供评分做“切题/正确性”对照）
        if answered_question:
            parts.append(f"上一条问题（本条回答须回答的）：\n{answered_question}")
        if answer_reference:
            parts.append(
                "本题参考要点（仅供判分对照，严禁把其中内容当成候选人已说过的）：\n"
                + answer_reference[:1400]
            )

    parts.append(f"候选人技能栈：{', '.join((resume_skills or skills)[:15])}")

    if is_last:
        parts.append("注意：本轮是面试最后一轮，只需要评分与点评，不要生成下一题（省略 next_question 字段）。")
    elif next_cat:
        parts.append(f"本轮类别：{CAT_LABELS.get(next_cat, next_cat)}（下一题按此类别出题）")
        parts.append(f"类别出题要求：\n{_CAT_INSTRUCTIONS.get(next_cat, '')}")
        parts.append(f"提问口吻（按本场发问侧重）：{focus_tone}")
        parts.append(_QUESTION_STYLE)
        parts.append(f"难度尺度（本档为「{diff_label}」，照此拉开深度与给分）：{diff_scale}")
        if next_cat == "project":
            # 项目深挖：注入难度考法与代码 RAG，允许锚定候选人代码库
            parts.append(f"难度考察方式：{diff_question}")
            parts.append(f"出题类型（本轮题型）：{question_type}")
            if intro_anchor:
                parts.append(f"首题对象（第一道题请紧扣它发问，勿旁逸到其它项目）：{intro_anchor}")
            if scope_note:
                parts.append(scope_note)
            parts.append(f"候选人简历项目经历：\n{resume_ctx}")
            parts.append(
                "知识库参考（代码库/简历/资料，已按来源标注，本轮取材请避开与本场已引用重复的片段）：\n"
                + (rag_context if rag_context else "（暂无相关代码）")
            )
        else:
            # 知识类题目：不给代码片段，只给技术栈背景，彻底脱离私有代码
            parts.append(f"难度把控：{_DIFFICULTY_GUIDES.get(difficulty, _DIFFICULTY_GUIDES['mid'])}")
            parts.append(
                "候选人技术栈与方向（仅作取材背景，严禁据此要求候选人复述其具体代码文件/函数实现）：\n"
                + stack_context
            )
        parts.append(f"下一题建议考察技能/主题：{skill}")

    if asked_context:
        parts.append(f"本场已考话题（禁止与其中任何一条重复或相近）：\n{asked_context}")
    parts.append(f"对话历史：\n{history_ctx}")
    parts.append(f"最近一条候选人回答：\n{_answer_for_eval(user_answer)}")

    return "\n\n".join(parts)


async def generate_turn(
    session_id: str,
    user_answer: str,
    skills: list[str],
) -> dict[str, Any]:
    """单轮推进：一次模型调用同时产出“上条回答的评分”和“下一道问题”。

    相比旧的“评分一次 + 出题一次”两次生成，延迟接近减半。
    内部完成：
    1) 落库候选人回答；2) 推进轮次（最后一轮则终止会话）；
    3) 一次生成评分/点评 + 下一题并清洗；4) 落库 system_eval。
    """
    session = _load_session(session_id)
    answered_round = session["current_round"]
    is_intro = answered_round == 0
    new_round = answered_round + 1
    max_rounds = session.get("max_rounds", settings.default_max_rounds)
    # 自我介绍(第 0 轮)不占“轮数”，max_rounds 即技术问答总轮数(round 1..max_rounds)
    is_last = new_round > max_rounds
    focus = session.get("focus") or "balanced"

    # 类别计划：技术问答共 max_rounds 道（round 1..max_rounds）
    plan = build_round_plan(max_rounds, focus)

    history_messages = get_session_messages(session_id)
    history_ctx = _build_history_context(history_messages)

    # 本条回答对应的“上一条题目原文 + 参考答案”，注入评分上下文做切题/正确性对照
    answered_question = ""
    answer_reference = ""
    if not is_intro:
        answered_question, answer_reference = _question_and_reference(
            history_messages, answered_round
        )

    # 评分必须对齐“本题实际对应题目”的技能与类别（该题生成时已随题落库），
    # 而不是拿“下一题要轮到的技能/类别”去评，避免答A题却点评B技能的错位。
    answered_skill = ""
    answered_cat = ""
    if not is_intro:
        answered_skill = _question_skill_from_messages(history_messages, answered_round)
        answered_cat = _question_cat_from_messages(history_messages, answered_round)
    if not answered_cat:
        # 旧数据 / 旧版会话可能没有类别：按计划里“该题当时的位置”兜底
        idx = answered_round - 1
        if 0 <= idx < len(plan):
            answered_cat = plan[idx]

    # 下一题建议类别 = 计划中 new_round-1 的位置；末轮不出题
    next_cat = ""
    next_idx = new_round - 1
    if not is_last and 0 <= next_idx < len(plan):
        next_cat = plan[next_idx]

    # 技能/题型随下一题类别走：basics 用固定标签；非 project 不轮题型
    if is_last:
        skill = ""
        question_type = ""
    else:
        skill = _pick_skill_for_category(next_cat, skills, session_id)
        question_type = _next_question_type(
            session.get("difficulty", "mid"), session_id
        ) if next_cat == "project" else ""

    resume = _load_resume(session.get("resume_id"))
    resume_ctx = _build_resume_context(resume)
    resume_skills = (resume or {}).get("skills") or []
    # 知识类题目的取材背景（技术栈池），非 project 轮次用它替代代码 RAG
    stack_context = _build_tech_stack_block(session, resume)

    # 简历项目 ↔ 代码库 对应关系说明 + “可深挖范围”硬约束（project 轮注入，防止张冠李戴 / 勾了 A 却问 B）
    scope_note = ""
    if next_cat == "project":
        _rp = (resume or {}).get("parsed_data") or {}
        scope_note = build_mapping_note(_rp.get("projects") or [])
        allowed = _selected_code_names(session)
        if allowed:
            rule = (
                "可深挖范围：仅限本场勾选的代码库（" + "、".join(allowed)
                + "）及其对应（映射到上述代码库）的简历项目。\n"
                "严禁就“未勾选 / 未映射的简历项目”（例如仅在简历里出现、但本场未勾选其代码库的经历）"
                "出项目深挖题；也不得把 A 代码库的内容说成 B 项目的实现。"
            )
            scope_note = (scope_note + "\n" + rule).strip() if scope_note else rule

    # 开场首题：从“简历项目 + 本场代码库项目”中随机抽一个作锚点，
    # 让多轮测试的首题不再永远落在同一个项目上
    intro_anchor = ""
    intro_sources: list[dict[str, Any]] | None = None
    if is_intro and not is_last:
        cands = _intro_anchors(session)
        if cands:
            pick = random.choice(cands)
            if pick["kind"] == "project":
                intro_anchor = pick["name"] + (
                    f"（{pick['language']}）" if pick.get("language") else ""
                )
                intro_sources = [{
                    "id": pick["id"], "prefix": "project_",
                    "label": f"项目·{pick['name']}",
                }]
                # 首题聚焦代码库项目时，不再把简历项目清单顶在前面（避免又被拉回简历首条经历）
                resume_ctx = ""
            else:
                intro_anchor = pick["name"]
                srcs: list[dict[str, Any]] = [{
                    "id": pick["id"] or session.get("resume_id") or "",
                    "prefix": "resume_", "label": f"简历·{pick['name']}",
                }]
                # 若该简历项目已映射到本场某代码库，首题可在简历 + 其代码库里取材
                for e in _code_entries_for_session(session, map_for_name(pick["name"])):
                    srcs.append({"id": e["id"], "prefix": "project_", "label": f"项目·{e['name']}"})
                intro_sources = srcs

    # 本场已考话题：从历史面试官问句取最近几轮，避免同角度重复
    asked_context = _asked_context_text(history_messages)

    # 仅“项目深挖”类别跨知识库检索（去掉知识题的项目锚定）；并跳过本场已引用片段
    rag_context = ""
    sources_meta: list[dict[str, str]] = []
    if next_cat == "project":
        kb_sources = intro_sources if intro_sources else _session_knowledge_sources(session)
        kb_results = await retrieve_knowledge(
            kb_sources,
            skill,
            per_source=2,
            max_total=4,
            exclude=set(_used_sources.get(session_id, [])),
        )
        rag_context = _format_knowledge(kb_results, snippet=200)
        sources_meta = _pick_source_meta(kb_results) if kb_results else []
        _remember_sources(session_id, [r["key"] for r in kb_results])

    prompt = _build_turn_prompt(
        session=session,
        skills=skills,
        answered_round=answered_round,
        is_intro=is_intro,
        is_last=is_last,
        skill=skill,
        answered_skill=answered_skill,
        answered_cat=answered_cat,
        next_cat=next_cat,
        question_type=question_type,
        resume_skills=resume_skills,
        resume_ctx=resume_ctx,
        stack_context=stack_context,
        rag_context=rag_context,
        history_ctx=history_ctx,
        asked_context=asked_context,
        user_answer=user_answer,
        intro_anchor=intro_anchor,
        scope_note=scope_note,
        answered_question=answered_question,
        answer_reference=answer_reference,
    )
    system = _INTRO_TURN_SYSTEM if is_intro else _TURN_SYSTEM

    raw = await llm_generate(prompt=prompt, system=system, temperature=0.6)
    obj = parse_json_object(raw)

    # 模型自报类别/主题修正（覆盖“同类别追问”等脱离计划的情况）；
    # 类别非法一律回退计划值，杜绝脏值入库。
    if obj is not None:
        if not is_last:
            mc = obj.get("category")
            if isinstance(mc, str) and mc in CATEGORIES:
                next_cat = mc
            topic = obj.get("topic")
            if isinstance(topic, str) and topic.strip():
                skill = topic.strip()
            # 记录“同主题追问”次数，用于全场追问总数控制（≤⌊总轮数/3⌋）
            if not is_intro and obj.get("is_followup") in (True, "true", "True", 1, "1"):
                _followup_used[session_id] = _followup_used.get(session_id, 0) + 1
            # 若自报落回 project 且之前没取代码素材（计划原本非 project），补一次检索
            if next_cat == "project" and not rag_context:
                kb_results = await retrieve_knowledge(
                    _session_knowledge_sources(session),
                    skill,
                    per_source=2,
                    max_total=4,
                    exclude=set(_used_sources.get(session_id, [])),
                )
                rag_context = _format_knowledge(kb_results, snippet=200)
                sources_meta = _pick_source_meta(kb_results) if kb_results else []
                _remember_sources(session_id, [r["key"] for r in kb_results])

    if is_intro:
        if obj is None:
            eval_result = {
                "type": "self_intro",
                "clarity": None,
                "substance": None,
                "fit": None,
                "avg": None,
                "comment": "（自我介绍点评生成失败）",
            }
        else:
            eval_result = finalize_intro_eval(obj, answer=user_answer)
    else:
        if obj is None:
            eval_result = {
                "depth": 5.0, "logic": 5.0, "integrity": 5.0, "avg": 5.0,
                "comment": "评估解析失败，请人工复查",
            }
        else:
            eval_result = finalize_answer_eval(obj, answer=user_answer)

    question_text = ""
    used_sources: list[dict[str, str]] = []
    if not is_last:
        if obj is not None:
            q = obj.get("next_question") or obj.get("question") or obj.get("问题")
            if isinstance(q, str) and q.strip():
                question_text = _clean_question_text(q)
        if not question_text:
            # 偶发 JSON/字段缺失时的保底：给一个不会卡的通用题
            question_text = _DEFAULT_NEXT_QUESTION
        used_sources = sources_meta

        # 防重复：
        #  ① 文本判重：对比“已问题目原文”，去标点/空白后相同或相似即命中 ——
        #     基于持久化历史，恒生效且不依赖内存（后端 reload 也不会丢）；零模型调用。
        #  ② 语义判重：历史≥3 题后才开启（嵌入一次，向量同时用于比对与缓存，省调用）。
        semantic_on = len(_QUESTION_VECS.get(session_id, {})) >= _DUP_MIN_CACHE
        _qvec: list[float] | None = None
        if semantic_on:
            _qvec = await _embed_question(question_text)

        dup = _text_dup_round(history_messages, question_text)
        if dup is None and semantic_on:
            dup = await _dup_round(history_messages, question_text, session_id, _qvec)
        orig_text = question_text
        if dup is not None:
            retry = await llm_generate(
                prompt=prompt
                + f"\n（重试要求：你上一稿的下一题与第 {dup} 题重复（或近似重复），请立刻换一个考察角度或技能点重新出题，严禁照抄或近似重复本场已考题。）",
                system=system,
                temperature=0.7,
            )
            obj2 = parse_json_object(retry)
            if obj2 is not None:
                q2 = obj2.get("next_question") or obj2.get("question") or obj2.get("问题")
                if isinstance(q2, str) and q2.strip():
                    q2 = _clean_question_text(q2)
                    q2_dup = _text_dup_round(history_messages, q2)
                    if q2_dup is None and semantic_on:
                        q2_dup = await _dup_round(history_messages, q2, session_id)
                    if q2 and q2_dup is None:
                        question_text = q2

        # 缓存本题向量供后续语义去重（复用上一步向量；重出后才补一次嵌入）
        if question_text:
            final_vec = _qvec if (_qvec is not None and question_text == orig_text) else None
            if final_vec is None:
                final_vec = await _embed_question(question_text)
            if final_vec:
                _QUESTION_VECS.setdefault(session_id, {})[new_round] = final_vec

    # 评分随行落类别/技能（intro 是 self_intro，报告端已排除，保持原样）
    stored_eval = eval_result
    if not is_intro:
        stored_eval = dict(eval_result)
        stored_eval["cat"] = answered_cat
        stored_eval["skill"] = answered_skill

    with get_db() as db:
        db.execute(
            """INSERT INTO messages (session_id, round_num, role, content, score_json)
               VALUES (?, ?, 'user', ?, NULL)""",
            (session_id, answered_round, user_answer),
        )
        db.execute(
            """INSERT INTO messages (session_id, round_num, role, content, score_json)
               VALUES (?, ?, 'system_eval', ?, ?)""",
            (
                session_id,
                answered_round,
                eval_result["comment"],
                json.dumps(stored_eval, ensure_ascii=False),
            ),
        )
        if is_last:
            db.execute(
                "UPDATE interview_sessions SET status = 'terminated', current_round = ?, ended_at = ? WHERE id = ?",
                (new_round, now_iso(), session_id),
            )
            _forget_session(session_id)
        else:
            db.execute(
                "UPDATE interview_sessions SET current_round = ?, status = 'questioning' WHERE id = ?",
                (new_round, session_id),
            )

    return {
        "answered_round": answered_round,
        "is_intro": is_intro,
        "is_last": is_last,
        "next_round": new_round,
        "evaluation": eval_result,
        "question_text": question_text if not is_last else "",
        "skill": skill,
        "cat": next_cat,
        "sources": used_sources,
    }


async def generate_greeting(
    session_id: str,
    skills: list[str],
    history_messages: list[dict[str, Any]],
):
    session = _load_session(session_id)
    diff_label = _DIFFICULTY_LABELS.get(session.get("difficulty", "mid"), "中级")
    focus = session.get("focus") or "balanced"
    identity = _FOCUS_IDENTITY.get(focus, _FOCUS_IDENTITY["balanced"])

    prompt = f"""你是一位资深技术面试官，即将在「论道」主持一场{diff_label}面试。
{identity}
候选人简历技能：{', '.join(skills[:10])}

请作 1-2 句简短自我介绍——自然说出你的人设与本场侧重，再请候选人介绍自己。
注意：不要用“我是XX，今天负责你的技术面试”这类干巴巴、模板化的白话开场。
{_SPEAK_STYLE}
只输出你的话，不要任何解释、分析或JSON。"""

    async for token in llm_generate_stream(
        prompt=prompt, system=_INTERVIEW_SYSTEM, temperature=0.7
    ):
        yield token


async def start_interview(resume_id: str, project_id: str, **kwargs: Any) -> str:
    difficulty = kwargs.get("difficulty", "mid")
    max_rounds = kwargs.get("max_rounds", settings.default_max_rounds)
    target_position = kwargs.get("target_position", "")
    focus = kwargs.get("focus", "balanced")
    project_ids = [p for p in (kwargs.get("project_ids") or []) if p]
    if not project_ids:
        project_ids = [project_id]
    if project_id not in project_ids:
        project_ids.insert(0, project_id)

    with get_db() as db:
        resume_row = db.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if not resume_row:
            raise ValueError("简历不存在")

        marks = ",".join("?" for _ in project_ids)
        rows = db.execute(
            f"SELECT id, index_status FROM projects WHERE id IN ({marks})",
            tuple(project_ids),
        ).fetchall()
        indexed = {r["id"]: r["index_status"] for r in rows}
        for pid in project_ids:
            if indexed.get(pid) is None:
                raise ValueError("所选项目不存在或未导入")
            if indexed[pid] != "completed":
                raise ValueError("所选项目尚未完成索引")

        session_id = generate_id()
        db.execute(
            """INSERT INTO interview_sessions
               (id, resume_id, project_id, project_ids, target_position, difficulty, max_rounds, focus, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'questioning')""",
            (
                session_id,
                resume_id,
                project_id,
                json.dumps(project_ids, ensure_ascii=False),
                target_position,
                difficulty,
                max_rounds,
                focus,
            ),
        )

    return session_id


def get_session(session_id: str) -> dict[str, Any] | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
        return row_to_dict(row)


def get_session_messages(session_id: str) -> list[dict[str, Any]]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY round_num, created_at",
            (session_id,),
        ).fetchall()
        return [row_to_dict(r) for r in rows]


async def search_session_kb(
    session_id: str, query: str, n_results: int = 8
) -> list[dict[str, Any]]:
    """论道“知识库查询”面板用：跨本场面试的所有知识来源综合检索。"""
    session = _load_session(session_id)
    results = await retrieve_knowledge(
        _session_knowledge_sources(session), query, per_source=3, max_total=n_results
    )
    return [
        {
            "source": r["source"],
            "text": r["text"],
            "file_path": r.get("file_path", ""),
            "function_name": r.get("function_name", ""),
            "distance": r.get("distance"),
        }
        for r in results
    ]


async def summarize_knowledge(query: str, results: list[dict[str, Any]]) -> str:
    """把检索命中的原始片段归一化、转成一段自然语言说明。

    results 为空时直接返回提示；模型把压缩/混淆片段当噪音忽略。
    """
    if not results:
        return "未找到明显相关内容，请换个关键词试试。"
    lines: list[str] = []
    for r in results[:8]:
        loc = r.get("file_path") or r.get("function_name") or ""
        head = f"- 来源：{r.get('source', '')}" + (f" · {loc}" if loc else "")
        lines.append(f"{head}\n{str(r.get('text', ''))[:300]}")
    prompt = f"检索关键词：{query}\n\n检索到的片段：\n\n" + "\n\n".join(lines) + "\n\n请给出自然语言说明。"
    raw = await llm_generate(
        prompt=prompt, system=_KB_SUMMARY_SYSTEM, temperature=0.3
    )
    return (raw or "").strip() or "未找到明显相关内容，请换个关键词试试。"


def prewarm_reference(session_id: str, round_num: int) -> None:
    """出题完成即让参考答案在后台生成（写库缓存），点击查看时一般已就绪。

    异常静默，不干扰面试主流程。
    """
    async def _run() -> None:
        try:
            await generate_reference(session_id, round_num)
        except Exception:
            logger.warning("prewarm reference failed for session=%s round=%s", session_id, round_num)

    asyncio.create_task(_run())


async def generate_reference(session_id: str, round_num: int) -> str:
    """读取（已缓存）或生成某一轮的“标准参考答案”。

    出题完成时后台已开始生成并回写 messages.score_json.reference；
    这里先读缓存，命中即秒回；未命中才现场生成并回写（并发用 per-round 锁去重）。
    """
    session = _load_session(session_id)
    with get_db() as db:
        row = db.execute(
            """SELECT id, content, score_json FROM messages
               WHERE session_id = ? AND round_num = ? AND role = 'assistant'
               ORDER BY id LIMIT 1""",
            (session_id, round_num),
        ).fetchone()
    if row is None or not (row["content"] or "").strip():
        raise ValueError("未找到该题，无法生成参考答案")

    msg_id = row["id"]
    question_text = row["content"].strip()
    saved_meta: dict[str, Any] = {}
    stored_sources: list[dict[str, str]] = []
    if row["score_json"]:
        try:
            saved_meta = json.loads(row["score_json"]) or {}
            stored_sources = saved_meta.get("sources") or []
            if saved_meta.get("rv") == _REF_VERSION:
                cached = (saved_meta.get("reference") or "").strip()
                if cached:
                    return cached
        except Exception:
            saved_meta = {}
            stored_sources = []

    key = f"{session_id}:{round_num}"
    lock = _ref_locks.setdefault(key, asyncio.Lock())
    async with lock:
        # 等锁期间后台任务可能已生成好，先复查一次
        with get_db() as db:
            r2 = db.execute(
                "SELECT score_json FROM messages WHERE id = ?", (msg_id,)
            ).fetchone()
        if r2 and r2["score_json"]:
            try:
                data2 = json.loads(r2["score_json"]) or {}
                if data2.get("rv") == _REF_VERSION:
                    cached = (data2.get("reference") or "").strip()
                    if cached:
                        return cached
            except Exception:
                pass

        # 本题类别：只有项目深挖才整库检索代码；知识类题目用通用原理作答
        cat = saved_meta.get("cat") or ""
        if cat not in CATEGORIES:
            plan = build_round_plan(
                session.get("max_rounds", settings.default_max_rounds),
                session.get("focus") or "balanced",
            )
            idx = round_num - 1
            cat = plan[idx] if 0 <= idx < len(plan) else "project"

        kb_ctx = ""
        source_meta = stored_sources
        if cat == "project":
            kb_results = await retrieve_knowledge(
                _session_knowledge_sources(session), question_text, per_source=2, max_total=6
            )
            kb_ctx = _format_knowledge(kb_results, snippet=300)
            if not source_meta:
                source_meta = _pick_source_meta(kb_results, cap=3) if kb_results else []

        source_lines = []
        for s in source_meta:
            loc = s.get("file_path") or s.get("function_name") or ""
            source_lines.append(f"- {s.get('source', '')}" + (f" · {loc}" if loc else ""))
        resume = _load_resume(session.get("resume_id"))
        resume_ctx = _build_resume_context(resume)
        diff_label = _DIFFICULTY_LABELS.get(session.get("difficulty", "mid"), "中级")
        guide = _DIFFICULTY_GUIDES.get(session.get("difficulty", "mid"), _DIFFICULTY_GUIDES["mid"])
        cat_label = CAT_LABELS.get(cat, cat)

        prompt = f"""题目（第 {round_num} 题 · {cat_label} · 难度 {diff_label}，{guide}）：
{question_text}

本题引用来源：
{chr(10).join(source_lines) if source_lines else '（无）'}

知识库相关片段：
{kb_ctx if kb_ctx else '（无）'}

候选人简历背景：
{resume_ctx}

请给出这份题目的标准参考答案。"""
        if cat != "project":
            prompt += "\n（本题属于脱离候选人代码库的通用题：答案覆盖通用机制与要点即可，不得编造或引用候选人的私有代码细节。）"

        raw = await llm_generate(
            prompt=prompt, system=_REFERENCE_SYSTEM, temperature=0.4
        )
        ref = (raw or "").strip()

        # 合并写回，保留题目自带的 cat/skill/sources，避免 prewarm 把元数据冲掉
        merged = dict(saved_meta)
        merged.update({"sources": source_meta, "reference": ref, "rv": _REF_VERSION})
        with get_db() as db:
            db.execute(
                """UPDATE messages SET score_json = ? WHERE id = ?""",
                (json.dumps(merged, ensure_ascii=False), msg_id),
            )
        _ref_locks.pop(key, None)
        return ref


def _is_self_intro_eval(m: dict[str, Any]) -> bool:
    """自我介绍点评只做现场反馈，不计入最终报告与技能覆盖。"""
    if not m.get("score_json"):
        return False
    try:
        return json.loads(m["score_json"]).get("type") == "self_intro"
    except Exception:
        return False


async def get_report(session_id: str) -> dict[str, Any]:
    session = get_session(session_id)
    if not session:
        raise ValueError("会话不存在")

    messages = get_session_messages(session_id)
    eval_msgs = [
        m
        for m in messages
        if m["role"] == "system_eval" and not _is_self_intro_eval(m)
    ]

    with get_db() as db:
        resume_row = db.execute(
            "SELECT skills FROM resumes WHERE id = ?", (session["resume_id"],)
        ).fetchone()
    skills = json.loads(resume_row["skills"]) if resume_row else []

    focus = session.get("focus") or "balanced"
    plan = build_round_plan(
        (session.get("max_rounds") or settings.default_max_rounds), focus
    )

    report = await generate_report(eval_msgs, skills)

    with get_db() as db:
        db.execute(
            "UPDATE interview_sessions SET status = 'reported' WHERE id = ?",
            (session_id,),
        )

    round_details: list[dict[str, Any]] = []
    for m in eval_msgs:
        data: dict[str, Any] = {}
        if m.get("score_json"):
            try:
                data = json.loads(m["score_json"]) or {}
            except Exception:
                data = {}
        rnum = m.get("round_num") or 1
        cat = data.get("cat") or ""
        if cat not in CATEGORIES:
            idx = rnum - 1
            cat = plan[idx] if 0 <= idx < len(plan) else "project"
        round_details.append({
            "round": rnum,
            "score": data.get("avg"),
            "comment": m["content"] if m["role"] == "system_eval" else None,
            "cat": cat,
            "cat_label": CAT_LABELS.get(cat, cat),
            "skill": data.get("skill") or "",
        })

    return {
        "session_id": session_id,
        "focus": focus,
        "summary": report,
        "radar_data": report["radar_data"],
        "category_stats": report.get("category_stats") or [],
        "round_details": round_details,
        "improvement_suggestion": report["improvement_suggestion"],
    }
