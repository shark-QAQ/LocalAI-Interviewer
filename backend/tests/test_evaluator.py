from app.services.evaluator import finalize_answer_eval, finalize_intro_eval, parse_json_object


def test_parse_json_object_edge():
    assert parse_json_object("") is None
    assert parse_json_object("```json\n{\"a\":1}\n```") == {"a": 1}
    assert parse_json_object("no braces") is None
    assert parse_json_object("text {\"a\":1} tail") == {"a": 1}
    # 连续多个对象：整段不是合法 JSON → None
    assert parse_json_object("{\"a\":1} {\"b\":2}") is None
    assert parse_json_object("123") is None


def test_finalize_answer_normal():
    r = finalize_answer_eval({"correctness": 8, "off_topic": False, "critical_error": False,
                              "depth": 7, "logic": 7, "integrity": 6, "comment": "清楚"},
                             answer="足够长的一段正常回答内容")
    assert r["correctness"] == 8
    assert 6 < r["avg"] < 8
    assert "off_topic" not in r


def test_finalize_answer_off_topic_gate():
    r = finalize_answer_eval({"correctness": 9, "off_topic": True, "critical_error": False,
                              "depth": 8, "logic": 8, "integrity": 8, "comment": "流畅"},
                             answer="很长但答非所问的内容，确实很长啊")
    assert r["depth"] <= 3 and r["avg"] <= 3.5
    assert "答非所问" in r["comment"]
    assert r["off_topic"] is True


def test_finalize_answer_critical_error_gate():
    r = finalize_answer_eval({"correctness": 7, "off_topic": False, "critical_error": True,
                              "depth": 7, "logic": 7, "integrity": 7, "comment": "ok"}, answer="答案")
    assert r["critical_error"] is True and r["avg"] <= 3.5


def test_finalize_answer_empty_short():
    r = finalize_answer_eval({"correctness": 7, "depth": 7, "logic": 7, "integrity": 7, "comment": "x"}, answer="不知道")
    assert r["avg"] <= 3.5
    assert "过短" in r["comment"]


def test_finalize_answer_legacy_no_correctness():
    r = finalize_answer_eval({"depth": 7, "logic": 6, "integrity": 5, "comment": "legacy"},
                             answer="这是一段足够长的正常回答内容用于测试用")
    assert "correctness" not in r
    assert abs(r["avg"] - (7 * 0.4 + 6 * 0.3 + 5 * 0.3)) < 0.01


def test_finalize_intro_gate_and_normal():
    short = finalize_intro_eval({"clarity": 8, "substance": 7, "fit": 7, "comment": "c"}, answer="嗯")
    assert short["avg"] == 3.0
    off = finalize_intro_eval({"clarity": 8, "substance": 7, "fit": 6, "off_topic": True, "comment": "x"},
                              answer="昨天吃了火锅，今天打算爬山，生活很惬意的一天。")
    assert off["avg"] == 3.0 and "答非所问" in off["comment"]
    ok = finalize_intro_eval({"clarity": 7, "substance": 8, "fit": 6, "comment": "好"},
                             answer="我叫张三，五年后端，做过安全平台和政务系统。")
    assert ok["avg"] > 6
