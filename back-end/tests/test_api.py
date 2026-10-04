import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from agent.api.app import create_app
from agent.domain.events import SseEvent


class FakeChat:
    async def stream(self, session_id: str, message: str):
        yield SseEvent(
            "tool_start", {"tool": "get_risk_label", "args": {"person_id": "P012"}}
        )
        yield SseEvent("token", {"text": f"echo:{message}"})
        yield SseEvent("done", {"session_id": session_id})


def make_client(repos, tools) -> TestClient:
    runtime = SimpleNamespace(
        settings=SimpleNamespace(gemini_api_key="k"),
        repos=repos,
        tools=list(tools.values()),
        chat=FakeChat(),
    )
    return TestClient(create_app(runtime))  # type: ignore[arg-type]


def test_health(repos, tools):
    body = make_client(repos, tools).get("/health").json()
    assert body == {"db": True, "llm": True, "model_version": "mock-v0.1"}


def test_tools_listing_comes_from_registered_tools(repos, tools):
    listed = make_client(repos, tools).get("/tools").json()
    assert {t["name"] for t in listed} == set(tools)
    assert all(t["parameters"]["type"] == "object" for t in listed)


def test_chat_streams_named_sse_events(repos, tools):
    client = make_client(repos, tools)
    with client.stream(
        "POST", "/chat", json={"session_id": "abc-123", "message": "hi"}
    ) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["x-accel-buffering"] == "no"
        text = "".join(r.iter_text())
    frames = [f for f in text.replace("\r\n", "\n").split("\n\n") if f.strip()]
    parsed = [
        (lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: ")))
        for f in frames
        if (lines := [ln for ln in f.split("\n") if not ln.startswith(":")])
    ]
    assert [name for name, _ in parsed] == ["tool_start", "token", "done"]
    assert parsed[1][1] == {"type": "token", "text": "echo:hi"}


def test_chat_validates_request(repos, tools):
    client = make_client(repos, tools)
    assert (
        client.post("/chat", json={"session_id": "bad id!", "message": "x"}).status_code
        == 422
    )
    assert (
        client.post("/chat", json={"session_id": "ok", "message": ""}).status_code
        == 422
    )


def test_cors_is_open(repos, tools):
    r = make_client(repos, tools).options(
        "/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers["access-control-allow-origin"] == "*"
