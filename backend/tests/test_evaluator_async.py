import pytest
from app.services import evaluator as ev


@pytest.mark.asyncio
async def test_evaluate_answer_success_and_fallback(monkeypatch):
    async def good(prompt, system="", temperature=0.7):
        return '{"depth":7,"logic":6,"integrity":5,"comment":"可以"}'
    monkeypatch.setattr(ev, "llm_generate", good)
    r = await ev.evaluate_answer(1, "C", "详细回答内容", "ctx")
    assert r["depth"] == 7.0 and r["avg"]

    async def junk(*a, **k):
        return "not-json"
    monkeypatch.setattr(ev, "llm_generate", junk)
    r = await ev.evaluate_answer(1, "C", "答", "ctx")
    assert r["avg"] == 5.0


@pytest.mark.asyncio
async def test_evaluate_introduction(monkeypatch):
    async def good(prompt, system="", temperature=0.7):
        return '{"clarity":7,"substance":8,"fit":6,"comment":"ok"}'
    monkeypatch.setattr(ev, "llm_generate", good)
    r = await ev.evaluate_introduction("我叫张三，做后端", "后端工程师", ["Python"])
    assert r["type"] == "self_intro" and r["avg"] == 7.0

    async def junk(*a, **k):
        return "xxx"
    monkeypatch.setattr(ev, "llm_generate", junk)
    r = await ev.evaluate_introduction("hi")
    assert r["avg"] is None


@pytest.mark.asyncio
async def test_generate_report_aggregation(monkeypatch):
    async def suggestion(prompt, system="", temperature=0.7):
        return "多练分布式与高并发设计。"
    monkeypatch.setattr(ev, "llm_generate", suggestion)

    rows = [
        {"score_json": '{"depth":8,"logic":7,"integrity":7,"avg":7.4,"cat":"project"}'},
        {"score_json": '{"depth":3,"logic":5,"integrity":4,"avg":4.0,"cat":"stack"}'},
    ]
    report = await ev.generate_report(rows, ["Python", "FastAPI"])
    assert report["avg_score"] == 5.7  # (7.4+4.0)/2
    assert report["radar_data"]["labels"]
    assert report["improvement_suggestion"].startswith("多练")
    cats = {c["cat"]: c["count"] for c in report["category_stats"]}
    assert cats["project"] == 1 and cats["stack"] == 1


def test_generate_report_empty():
    import asyncio
    r = asyncio.run(ev.generate_report([], []))
    assert r["avg_score"] == 0
    assert r["improvement_suggestion"] == "暂无评估数据"
