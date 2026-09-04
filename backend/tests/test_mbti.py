import json

import pytest
from app.services import mbti_service as m


# ---------- service ----------

def test_dimension_table_consistent():
    assert m.TOTAL == 20 and m.PER_DIM == 5
    assert list(m.DIM_POLES) == ["EI", "SN", "TF", "JP"]
    assert m.DIM_POLES["EI"] == ("E", "I")


def test_fallback_bank_valid():
    assert len(m._FALLBACK_QUESTIONS) == 20
    assert m._validate_questions(m._FALLBACK_QUESTIONS) is True


def test_validate_bad():
    qs = list(m._FALLBACK_QUESTIONS)
    assert m._validate_questions(qs[:5]) is False
    bad = dict(qs[0]); bad["poleA"] = "X";
    assert m._validate_questions([bad] + qs[1:]) is False


def test_extract_json_array():
    assert m._extract_json_array("no array") == []
    assert m._extract_json_array('pre [1,2] post') == [1, 2]


@pytest.mark.asyncio
async def test_generate_questions_llm_fail_falls_back(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(m, "llm_generate", boom)
    qs = await m.generate_questions()
    assert len(qs) == 20


@pytest.mark.asyncio
async def test_generate_questions_llm_invalid_then_fallback(monkeypatch):
    async def bad(*a, **k):
        return "not-json"
    monkeypatch.setattr(m, "llm_generate", bad)
    qs = await m.generate_questions()
    assert len(qs) == 20


def _fake_dim_batch(dim):
    left, right = m.DIM_POLES[dim]
    out = []
    for i in range(m.PER_DIM):
        out.append({"dim": dim, "text": f"{dim} 场景{i}", "opA": f"偏向{left}", "opB": f"偏向{right}",
                    "poleA": left, "poleB": right})
    return out


@pytest.mark.asyncio
async def test_generate_questions_parallel_dim_success(monkeypatch):
    async def fake(prompt, system="", temperature=0.8):
        # 从提示里按 dim= 提取目标维度，返回该维 5 题
        for d in m.DIM_POLES:
            if f'"{d}"' in prompt or d in prompt:
                return json.dumps(_fake_dim_batch(d), ensure_ascii=False)
        return "not-json"
    monkeypatch.setattr(m, "llm_generate", fake)
    qs = await m.generate_questions()
    from collections import Counter
    cnt = Counter(q["dim"] for q in qs)
    assert len(qs) == 20 and all(cnt[d] == 5 for d in m.DIM_POLES)


@pytest.mark.asyncio
async def test_generate_questions_one_dim_fallback_mix(monkeypatch):
    import json as _json
    async def fake(prompt, system="", temperature=0.8):
        # 只对 TF 维度成功，其它维失败 -> 失败维回退内置
        if "TF" in prompt:
            return _json.dumps(_fake_dim_batch("TF"), ensure_ascii=False)
        raise RuntimeError("boom")
    monkeypatch.setattr(m, "llm_generate", fake)
    qs = await m.generate_questions()
    from collections import Counter
    cnt = Counter(q["dim"] for q in qs)
    assert len(qs) == 20 and cnt["TF"] == 5 and cnt["EI"] == 5


def test_valid_one_and_fallback_for():
    ok = {"dim": "EI", "text": "x", "opA": "a", "opB": "b", "poleA": "E", "poleB": "I"}
    assert m._valid_one(ok)
    bad = dict(ok); bad["poleA"] = "S"
    assert not m._valid_one(bad)
    assert m._valid_one("not-dict") is False
    assert len(m._fallback_for("EI")) == 5
    assert all(x["dim"] == "EI" for x in m._fallback_for("EI"))


def test_compute_type_left_extreme():
    ans = []
    for dim, pole in [("EI", "E"), ("SN", "S"), ("TF", "T"), ("JP", "J")]:
        ans += [{"dim": dim, "pole": pole}] * 5
    r = m.compute_type(ans)
    assert r["type"] == "ESTJ"
    assert r["borderline"] is False
    d = {x["dim"]: x for x in r["dimensions"]}
    assert d["EI"]["left_pct"] == 100 and d["EI"]["pick"] == "E"


def test_compute_type_tie_borderline():
    ans = []
    for dim, (l, rr) in m.DIM_POLES.items():
        ans += [{"dim": dim, "pole": l}] * 3 + [{"dim": dim, "pole": rr}] * 2
    # EI 4:1? 上面 3+2 -> pick left; 想测平票单独构造
    ans2 = []
    for dim, (l, rr) in m.DIM_POLES.items():
        ans2 += [{"dim": dim, "pole": l}] * 5
    # 制造每维 2:2 会 break 每维恰5前提，但 compute_type 容忍任意数量
    mixed = []
    for dim, (l, rr) in m.DIM_POLES.items():
        mixed += [{"dim": dim, "pole": l}, {"dim": dim, "pole": rr}, {"dim": dim, "pole": l}, {"dim": dim, "pole": rr}]
    r = m.compute_type(mixed)
    assert r["borderline"] is True
    assert r["type"] == "ESTJ"  # 平票取 E/S/T/J


def test_compute_type_missing_answers_is_safe():
    r = m.compute_type([])
    assert len(r["dimensions"]) == 4


@pytest.mark.asyncio
async def test_summarize_llm_success(monkeypatch):
    dims = m.compute_type([{"dim": d, "pole": "E"} for d in ("EI", "SN", "TF", "JP")])["dimensions"]
    async def fake(prompt, system="", temperature=0.7):
        return '{"summary":"测试描述","industries":[{"name":"软件研发","pct":90,"why":"适合"},{"name":"产品","pct":80,"why":"也行"}]}'
    monkeypatch.setattr(m, "llm_generate", fake)
    out = await m.summarize("ESTJ", dims)
    assert out["summary"] == "测试描述"
    assert out["industries"][0]["pct"] == 90


@pytest.mark.asyncio
async def test_summarize_llm_fail_fallback(monkeypatch):
    dims = m.compute_type([{"dim": d, "pole": "E"} for d in ("EI", "SN", "TF", "JP")])["dimensions"]
    async def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(m, "llm_generate", boom)
    out = await m.summarize("ESTJ", dims)
    assert out["industries"] and out["summary"]


# ---------- router ----------

def test_mbti_questions_gated(client):
    r = client.get("/api/v1/mbti/questions")
    assert r.status_code == 403


def test_mbti_result_gated(client):
    r = client.post("/api/v1/mbti/result", json={"answers": []})
    assert r.status_code == 403


def test_mbti_questions_api_fallback(client, enable_api, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("no-llm")
    monkeypatch.setattr(m, "llm_generate", boom)
    r = client.get("/api/v1/mbti/questions")
    assert r.status_code == 200
    data = r.json()
    assert len(data["questions"]) == 20
    assert len(data["dimensions"]) == 4


def test_mbti_result_api(client, enable_api, monkeypatch):
    async def fake(prompt, system="", temperature=0.7):
        return '{"summary":"你很有条理","industries":[{"name":"项目管理","pct":91,"why":"组织力强"},{"name":"财务","pct":80,"why":"细致"},{"name":"工程","pct":75,"why":"严谨"}]}'
    monkeypatch.setattr(m, "llm_generate", fake)
    answers = []
    for dim, pole in [("EI", "E"), ("SN", "S"), ("TF", "T"), ("JP", "J")]:
        answers += [{"dim": dim, "pole": pole}] * 5
    r = client.post("/api/v1/mbti/result", json={"answers": answers})
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "ESTJ"
    assert len(data["industries"]) == 3
    assert all("left_pct" in d for d in data["dimensions"])


def test_mbti_result_validation(client, enable_api):
    r = client.post("/api/v1/mbti/result", json={"answers": []})
    assert r.status_code == 400
    bad = [{"dim": "EI", "pole": "X"}] * 20
    assert client.post("/api/v1/mbti/result", json={"answers": bad}).status_code == 400
