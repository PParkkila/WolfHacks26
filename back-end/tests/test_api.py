import json
from dataclasses import replace

from fastapi.testclient import TestClient
from support import OTHER, PID

from agent.api.app import create_app
from agent.domain.events import SseEvent
from agent.domain.metrics import GLUCO_SCORE

ALLOWED = "http://localhost:5173"


def frames(text: str) -> list[tuple[str, dict]]:
    blocks = [f for f in text.replace("\r\n", "\n").split("\n\n") if f.strip()]
    return [
        (lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: ")))
        for f in blocks
        if (lines := [ln for ln in f.split("\n") if not ln.startswith(":")])
    ]


# --- auth -----------------------------------------------------------------------


def test_health_needs_no_token(client):
    body = client.get("/health").json()
    assert body["db"] is True
    assert (body["windows"], body["participants"]) == (2907, 17)
    assert body["clock"]["now"] == "2026-10-04T07:00:00Z"


def test_personas_and_login(client):
    personas = client.get("/personas").json()
    assert len(personas) == 18
    assert personas[0]["role"] == "clinician"
    login = client.post("/auth/login", json={"persona_id": f"patient:{PID}"}).json()
    assert login["principal"]["participant_id"] == PID
    headers = {"Authorization": f"Bearer {login['token']}"}
    assert client.get("/me", headers=headers).json()["display_name"] == "Patient 013"
    missing = client.post("/auth/login", json={"persona_id": "patient:nobody"})
    assert missing.status_code == 404


def test_data_routes_need_a_valid_token(client):
    for path in ("/catalog", "/participants", "/cohort", "/clock", "/chat/sessions"):
        assert client.get(path).status_code == 401
        bad = client.get(path, headers={"Authorization": "Bearer junk"})
        assert bad.status_code == 401


# --- scope ------------------------------------------------------------------------


def test_patient_sees_only_themselves(client, as_patient, as_clinician):
    assert len(client.get("/participants", headers=as_clinician).json()) == 17
    rows = client.get("/participants", headers=as_patient).json()
    assert [r["person_id"] for r in rows] == [PID]
    assert client.get("/participants/13", headers=as_patient).status_code == 200
    for path in (f"/participants/{OTHER}", "/participants/2/explain", "/cohort"):
        response = client.get(path, headers=as_patient)
        assert response.status_code == 403
        assert response.json()["code"] == "not_permitted"
    other = client.post(
        "/query", headers=as_patient, json={"participants": ["2"]}
    ).json()
    assert other["code"] == "not_permitted"
    pooled = client.post("/query", headers=as_patient, json={"group_by": "cohort"})
    assert pooled.status_code == 403


def test_catalog_is_scoped(client, as_patient, as_clinician):
    mine = client.get("/catalog", headers=as_patient).json()
    assert [p["person_id"] for p in mine["participants"]] == [PID]
    assert mine["group_bys"] == ["participant"]
    assert GLUCO_SCORE in {m["name"] for m in mine["metrics"]}
    everyone = client.get("/catalog", headers=as_clinician).json()
    assert len(everyone["participants"]) == 17


# --- data -----------------------------------------------------------------------


def test_generic_query(client, as_clinician):
    body = {
        "metrics": [GLUCO_SCORE, "hr_mean_bpm_24h"],
        "bucket": "day",
        "group_by": "cohort",
    }
    result = client.post("/query", headers=as_clinician, json=body).json()
    [series] = result["series"]
    assert series["participant_id"] is None
    assert set(series["points"][0]) >= {"t", "n", GLUCO_SCORE, "hr_mean_bpm_24h"}
    bad = client.post("/query", headers=as_clinician, json={"metrics": ["glucose"]})
    assert bad.status_code == 400
    assert bad.json()["suggestions"]
    extra = client.post("/query", headers=as_clinician, json={"sql": "drop"})
    assert extra.status_code == 422


def test_unknown_and_ambiguous_participants(client, as_clinician):
    missing = client.get("/participants/99", headers=as_clinician)
    assert (missing.status_code, missing.json()["code"]) == (404, "not_found")


def test_explain_includes_cohort_position_for_clinicians_only(
    client, as_clinician, as_patient
):
    clinical = client.get("/participants/13/explain", headers=as_clinician).json()
    assert clinical["cohort_position"]
    own = client.get("/participants/13/explain?hours=12", headers=as_patient).json()
    assert own["cohort_position"] is None
    assert own["change"]["hours"] == 12


def test_cohort_and_compare(client, as_clinician):
    overview = client.get("/cohort", headers=as_clinician).json()
    assert overview["participants"] == 17
    compare = client.get(
        "/participants/13/compare?metric=gluco_score", headers=as_clinician
    ).json()
    assert compare["cohort_size"] == 17


def test_clock_control(client, as_clinician):
    state = client.get("/clock", headers=as_clinician).json()
    assert state["enabled"] is False  # tests run with the replay disabled
    seek = client.post("/clock", headers=as_clinician, json={"action": "speed"})
    assert seek.status_code == 422
    paused = client.post("/clock", headers=as_clinician, json={"action": "pause"})
    assert paused.json()["playing"] is False


# --- chat -------------------------------------------------------------------------


class FakeChat:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def stream(self, principal, session_id: str, message: str):
        self.calls.append((principal.user_id, session_id, message))
        yield SseEvent("tool_start", {"tool": "get_my_status", "args": {}})
        yield SseEvent("data", {"chart": {"series": []}})
        yield SseEvent("token", {"text": f"echo:{message}"})
        yield SseEvent("done", {"session_id": session_id})


def test_chat_streams_as_the_signed_in_user(runtime, as_patient):
    fake = FakeChat()
    client = TestClient(create_app(replace(runtime, chat=fake)))  # type: ignore[arg-type]
    with client.stream(
        "POST",
        "/chat",
        json={"session_id": "abc-123", "message": "hi"},
        headers=as_patient,
    ) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["x-accel-buffering"] == "no"
        text = "".join(r.iter_text())
    parsed = frames(text)
    assert [name for name, _ in parsed] == ["tool_start", "data", "token", "done"]
    assert fake.calls == [(f"patient:{PID}", "abc-123", "hi")]


def test_chat_validates_and_needs_a_token(client, as_patient):
    assert (
        client.post("/chat", json={"session_id": "ok", "message": "x"}).status_code
        == 401
    )
    bad_id = {"session_id": "bad id!", "message": "x"}
    assert client.post("/chat", json=bad_id, headers=as_patient).status_code == 422
    empty = {"session_id": "ok", "message": ""}
    assert client.post("/chat", json=empty, headers=as_patient).status_code == 422


def test_chat_threads_belong_to_their_user(runtime, client, as_patient, as_clinician):
    runtime.sessions.touch(f"patient:{PID}", "t1", "Why did my score drop?")
    mine = client.get("/chat/sessions", headers=as_patient).json()
    assert [(t["session_id"], t["title"]) for t in mine] == [
        ("t1", "Why did my score drop?")
    ]
    assert client.get("/chat/sessions", headers=as_clinician).json() == []
    assert client.get("/chat/sessions/t1", headers=as_patient).json() == []
    assert client.get("/chat/sessions/t1", headers=as_clinician).status_code == 404


def test_tools_listing_depends_on_role(client, as_patient, as_clinician):
    patient_tools = {t["name"] for t in client.get("/tools", headers=as_patient).json()}
    clinician_tools = {
        t["name"] for t in client.get("/tools", headers=as_clinician).json()
    }
    assert "get_my_status" in patient_tools
    assert "query_data" in clinician_tools
    assert not patient_tools & clinician_tools


def test_patient_tool_schemas_take_no_participant(client, as_patient):
    for tool in client.get("/tools", headers=as_patient).json():
        params = set(tool["parameters"].get("properties", {}))
        assert not params & {"person_id", "participants", "group_by"}, tool["name"]


def test_cors_allows_only_the_configured_origins(client):
    ok = client.get("/health", headers={"Origin": ALLOWED})
    assert ok.headers["access-control-allow-origin"] == ALLOWED
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers
    preflight = client.options(
        "/chat",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "POST"},
    )
    assert preflight.headers["access-control-allow-origin"] == ALLOWED
