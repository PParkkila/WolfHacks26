from support import PID

from agent.domain.metrics import GLUCO_SCORE


async def test_list_participants_sorts_and_caps(invoke_clinician, clinician):
    out = await invoke_clinician("list_participants", top_k=3)
    scores = [p["values"][GLUCO_SCORE] for p in out["participants"]]
    assert scores == sorted(scores)
    assert (out["rows"], out["total_participants"]) == (3, 17)
    assert out["as_of"] == clinician.as_of().isoformat()
    bad = await invoke_clinician("list_participants", top_k=0)
    assert bad["code"] == "bad_argument"


async def test_get_participant_resolves_short_refs_and_charts_the_week(
    invoke_clinician,
):
    out = await invoke_clinician("get_participant", person_id="P013")
    assert out["participant"]["person_id"] == PID
    assert out["gluco_week"]["points"] == 168
    [series] = out["chart"]["series"]
    assert len(series["points"]) <= 48
    assert out["chart"]["downsampled"] is True


async def test_unknown_person_is_a_payload_not_an_exception(invoke_clinician):
    out = await invoke_clinician("get_participant", person_id="99")
    assert out["code"] == "not_found"
    assert out["rows"] == 0


async def test_explain_change_combines_history_and_cohort(invoke_clinician):
    out = await invoke_clinician("explain_change", person_id="13")
    assert out["change"]["person_id"] == PID
    assert out["cohort_position"]
    assert GLUCO_SCORE in out["chart"]["metrics"]
    assert "->" in out["summary"]


async def test_query_data_keeps_llm_payloads_bounded(invoke_clinician):
    out = await invoke_clinician(
        "query_data", metrics=[GLUCO_SCORE, "hr_mean_bpm_24h"], bucket="hour"
    )
    points = sum(len(s["points"]) for s in out["chart"]["series"])
    assert len(out["chart"]["series"]) == 17
    assert points <= 240
    bad = await invoke_clinician("query_data", metrics=["glucose"])
    assert bad["code"] == "bad_argument"
    assert "gluco_score" in bad["suggestions"]


async def test_cohort_tools(invoke_clinician):
    overview = await invoke_clinician("cohort_overview")
    assert overview["overview"]["participants"] == 17
    compare = await invoke_clinician(
        "compare_to_cohort", person_id="13", metric="hr_mean_bpm_24h"
    )
    assert compare["comparison"]["percentile_method"] == "normal_approximation"


async def test_patient_tools_are_bound_to_the_patient(invoke_patient):
    status = await invoke_patient("get_my_status")
    assert status["latest"]["person_id"] == PID
    change = await invoke_patient("explain_my_change", hours=12)
    assert change["change"]["hours"] == 12
    assert "cohort_position" not in change
    trend = await invoke_patient("get_my_trend", metric="motion_mean_g", bucket="day")
    assert trend["trend"]["metric"] == "motion_mean_g"
    data = await invoke_patient("query_my_data", metrics=[GLUCO_SCORE], agg="min")
    assert [s["participant_id"] for s in data["chart"]["series"]] == [PID]
