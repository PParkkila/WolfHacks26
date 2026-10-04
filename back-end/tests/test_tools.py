import pytest

from agent.tools.base import error, safe_tool


async def test_registered_tools_have_schemas(tools):
    assert set(tools) == {
        "get_risk_label",
        "explain_risk",
        "rank_candidates",
        "compare_to_cohort",
        "data_quality_check",
    }
    assert tools["rank_candidates"].params_json_schema["properties"].keys() == {
        "top_k",
        "min_confidence",
    }
    assert all(tool.description for tool in tools.values())


async def test_get_risk_label_reliable(invoke):
    out = await invoke("get_risk_label", person_id="P012")
    assert out["label"] == "at_risk"
    assert out["reliable"] is True
    assert out["abstain_reason"] is None
    assert out["model_version"] == "mock-v0.1"
    assert out["window"]["end"].startswith("2026-10-02")


@pytest.mark.parametrize(
    ("person", "reason"),
    [
        ("P031", "insufficient_data_quality"),
        ("P019", "low_confidence"),
        ("P035", "not_scored"),
    ],
)
async def test_get_risk_label_flags_abstention(invoke, person, reason):
    out = await invoke("get_risk_label", person_id=person)
    assert out["reliable"] is False
    assert out["abstain_reason"] == reason


async def test_get_risk_label_unknown_person_is_structured_error(invoke):
    out = await invoke("get_risk_label", person_id="P999")
    assert out["code"] == "not_found"
    assert "error" in out
    assert out["rows"] == 0


async def test_get_risk_label_window_argument(invoke):
    previous = await invoke(
        "get_risk_label", person_id="P007", window="2026-10-01T00:00:00Z"
    )
    latest = await invoke("get_risk_label", person_id="P007")
    assert previous["label"] == "not_at_risk"
    assert latest["label"] == "at_risk"
    assert (await invoke("get_risk_label", person_id="P007", window="garbage"))[
        "code"
    ] == "bad_argument"


async def test_explain_risk_describes_deviation_not_attribution(invoke):
    out = await invoke("explain_risk", person_id="P012")
    assert out["method"] == "cohort_deviation"
    assert len(out["top_features"]) == out["rows"] == 5
    zs = [abs(f["z_score"]) for f in out["top_features"]]
    assert zs == sorted(zs, reverse=True)
    assert {"value", "cohort_median", "percentile", "direction"} <= out["top_features"][
        0
    ].keys()
    assert out["tension"] is False
    assert "associations" in out["caveat"]


async def test_explain_risk_notices_tension(invoke):
    out = await invoke("explain_risk", person_id="P024")
    assert out["label"] == "at_risk"
    assert out["tension"] is True


@pytest.mark.parametrize("person", ["P031", "P019", "P035"])
async def test_explain_risk_withheld_when_unreliable(invoke, person):
    out = await invoke("explain_risk", person_id=person)
    assert out["abstain"] is True
    assert "top_features" not in out


async def test_rank_candidates_sorted_and_capped(invoke):
    out = await invoke("rank_candidates", top_k=5)
    scores = [c["score"] for c in out["candidates"]]
    assert len(scores) == out["rows"] == 5
    assert scores == sorted(scores, reverse=True)
    assert all(c["reliable"] in (True, False) for c in out["candidates"])
    assert (await invoke("rank_candidates", top_k=0))["code"] == "bad_argument"
    assert (await invoke("rank_candidates", top_k=201))["code"] == "bad_argument"


async def test_rank_candidates_excludes_unscored_and_applies_confidence(invoke):
    everyone = await invoke("rank_candidates", top_k=200)
    ids = {c["person_id"] for c in everyone["candidates"]}
    assert "P035" not in ids
    assert everyone["scored_people"] == 39
    confident = await invoke("rank_candidates", top_k=200, min_confidence=0.8)
    assert all(c["confidence"] >= 0.8 for c in confident["candidates"])
    assert "P019" not in {c["person_id"] for c in confident["candidates"]}


async def test_compare_to_cohort(invoke):
    out = await invoke("compare_to_cohort", person_id="P012", feature="resting_hr_bpm")
    assert out["direction"] == "above"
    assert out["percentile"] > 90
    assert {"value", "cohort_median", "percentile"} <= out.keys()


async def test_compare_to_cohort_unknown_feature_suggests(invoke):
    out = await invoke("compare_to_cohort", person_id="P012", feature="resting_hr")
    assert out["code"] == "unknown_feature"
    assert "resting_hr_bpm" in out["suggestions"]
    assert out["available_features"]
    assert (await invoke("compare_to_cohort", person_id="P999", feature="x"))[
        "code"
    ] == "not_found"


async def test_data_quality_check(invoke):
    assert (await invoke("data_quality_check", person_id="P003"))["verdict"] == "good"
    assert (await invoke("data_quality_check", person_id="P014"))[
        "verdict"
    ] == "marginal"
    bad = await invoke("data_quality_check", person_id="P031")
    assert bad["verdict"] == "insufficient"
    assert bad["reasons"]


def test_safe_tool_never_raises():
    @safe_tool
    def boom() -> dict:
        raise RuntimeError("secret connection string")

    out = boom()
    assert out["code"] == "internal_error"
    assert "secret" not in str(out)
    assert error("x", "y")["rows"] == 0


async def test_compare_to_cohort_carries_trust_fields(invoke):
    out = await invoke("compare_to_cohort", person_id="P031", feature="resting_hr_bpm")
    assert out["reliable"] is False
    assert out["abstain_reason"] == "insufficient_data_quality"
    assert out["data_quality"] == "insufficient"
