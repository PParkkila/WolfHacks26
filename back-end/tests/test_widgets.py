from support import PID

from agent.analysis.compliance import sanitize
from agent.auth import CLINICIAN, patient
from agent.domain.metrics import GLUCO_SCORE
from agent.query import QuerySpec

STAGES = ["design", "fetch", "compliance", "bind"]
RANKING = {
    "title": "Lowest Gluco Scores",
    "kind": "ranking",
    "query": {
        "metrics": [GLUCO_SCORE],
        "hours": 168,
        "bucket": "all",
        "agg": "last",
        "sort_by": GLUCO_SCORE,
        "order": "asc",
        "limit": 5,
    },
}


async def test_build_widget_runs_the_whole_pipeline(invoke_clinician):
    out = await invoke_clinician(
        "build_widget",
        title="Lowest",
        kind="ranking",
        metrics=[GLUCO_SCORE],
        participants=[],  # what models send for "everyone"
    )
    widget = out["widget"]
    assert [step["stage"] for step in widget["steps"]] == STAGES
    assert widget["query"]["bucket"] == "all"
    assert "start" not in widget["query"]  # relative, so a pin follows the clock
    series = out["chart"]["series"]
    assert len(series) == 5
    assert not any(s["participant_id"].startswith("demo:") for s in series)
    scores = [s["points"][-1][GLUCO_SCORE] for s in series]
    assert scores == sorted(scores)


async def test_build_widget_failures_are_payloads(invoke_clinician):
    bad = await invoke_clinician(
        "build_widget", title="x", kind="trend", metrics=["glucose"]
    )
    assert bad["code"] == "bad_argument"


def test_sanitize_hides_small_cohort_cells(clinician):
    raw = clinician.query(
        QuerySpec(metrics=[GLUCO_SCORE], hours=48, bucket="hour", group_by="cohort")
    )
    raw.series[0].points[0]["participants"] = 2
    clean, audit = sanitize(raw, CLINICIAN)
    assert clean.series[0].points[0][GLUCO_SCORE] is None
    assert clean.series[0].points[1][GLUCO_SCORE] is not None
    assert any("hidden" in line for line in audit)


def test_sanitize_keeps_a_patient_to_their_own_series(clinician):
    raw = clinician.query(QuerySpec(metrics=[GLUCO_SCORE], hours=24))
    clean, audit = sanitize(raw, patient(PID))
    assert [s.participant_id for s in clean.series] == ["Patient 013"]
    assert "other series removed" in audit[0]


def test_pin_list_refresh_and_unpin(client, as_clinician, as_patient):
    pinned = client.post("/widgets", json=RANKING, headers=as_clinician)
    assert pinned.status_code == 201
    wid = pinned.json()["id"]
    assert [w["id"] for w in client.get("/widgets", headers=as_clinician).json()] == [
        wid
    ]
    assert client.get("/widgets", headers=as_patient).json() == []  # per user

    data = client.get(f"/widgets/{wid}/data", headers=as_clinician).json()
    assert [step["stage"] for step in data["steps"]] == STAGES
    assert len(data["result"]["series"]) == 5
    assert client.get(f"/widgets/{wid}/data", headers=as_patient).status_code == 404

    assert client.delete(f"/widgets/{wid}", headers=as_clinician).status_code == 204
    assert client.get("/widgets", headers=as_clinician).json() == []


def test_patients_cannot_pin_cohort_views(client, as_patient):
    spec = {
        "title": "Panel",
        "kind": "cohort_trend",
        "query": {"metrics": [GLUCO_SCORE], "group_by": "cohort"},
    }
    assert client.post("/widgets", json=spec, headers=as_patient).status_code == 403
