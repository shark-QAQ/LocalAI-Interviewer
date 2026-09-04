"""MBTI 职业性格测试接口。

可信度门禁：仅当文本生成提供方为 DeepSeek(API) 时开放；本地 Ollama 时返回 403 并引导切换。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..llm_config import get_llm_settings
from ..services import mbti_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mbti", tags=["mbti"])

_GATE_MSG = (
    "MBTI 职业测试为保证可信度，仅在使用 DeepSeek API（设置页把提供方切到 API）时开放。"
    "当前仍是本地模型，请先到「设置」切换后再试。"
)


class MbtiAnswer(BaseModel):
    dim: str
    pole: str


class MbtiResultBody(BaseModel):
    answers: list[MbtiAnswer]


def _require_api() -> None:
    if get_llm_settings().provider != "deepseek":
        raise HTTPException(status_code=403, detail=_GATE_MSG)


@router.get("/questions")
async def get_questions() -> dict[str, Any]:
    _require_api()
    questions = await mbti_service.generate_questions()
    return {
        "dimensions": mbti_service.DIMENSIONS,
        "questions": questions,
    }


@router.post("/result")
async def post_result(body: MbtiResultBody) -> dict[str, Any]:
    _require_api()

    answers = body.answers or []
    if len(answers) != mbti_service.TOTAL:
        raise HTTPException(status_code=400, detail=f"需提交 {mbti_service.TOTAL} 道题的作答结果（当前 {len(answers)}）")

    per_dim: dict[str, int] = {}
    for a in answers:
        dim = a.dim
        if dim not in mbti_service.DIM_POLES:
            raise HTTPException(status_code=400, detail=f"非法维度：{dim}")
        if a.pole not in mbti_service.DIM_POLES[dim]:
            raise HTTPException(status_code=400, detail=f"维度 {dim} 的选项字母非法：{a.pole}")
        per_dim[dim] = per_dim.get(dim, 0) + 1
    if any(per_dim.get(d, 0) != mbti_service.PER_DIM for d in mbti_service.DIM_POLES):
        raise HTTPException(status_code=400, detail="每个维度必须恰好作答 5 题")

    typed: list[dict[str, str]] = [{"dim": a.dim, "pole": a.pole} for a in answers]
    type_info = mbti_service.compute_type(typed)
    conclusion = await mbti_service.summarize(type_info["type"], type_info["dimensions"])
    return {
        "type": type_info["type"],
        "type_full": type_info["type_full"],
        "dimensions": type_info["dimensions"],
        "borderline": type_info["borderline"],
        "summary": conclusion["summary"],
        "industries": conclusion["industries"],
    }
