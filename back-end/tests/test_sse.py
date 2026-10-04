import json
from types import SimpleNamespace

import pytest
from agents import (
    GuardrailFunctionOutput,
    InputGuardrailResult,
    InputGuardrailTripwireTriggered,
    MaxTurnsExceeded,
    RawResponsesStreamEvent,
    RunItemStreamEvent,
)

from agent.api.chat_service import MAX_TURNS_REPLY, ChatService
from agent.api.sse import StreamTranslator
from agent.guardrails import DECLINE_MESSAGES, GuardrailVerdict, build_input_guardrails
from agent.observability.trace import JsonlTracer, NullTracer


def delta(text: str) -> RawResponsesStreamEvent:
    return RawResponsesStreamEvent(
        data=SimpleNamespace(type="response.output_text.delta", delta=text)
    )


def called(name: str, args: dict, call_id: str = "c1") -> RunItemStreamEvent:
    raw = {"name": name, "arguments": json.dumps(args), "call_id": call_id}
    return RunItemStreamEvent(name="tool_called", item=SimpleNamespace(raw_item=raw))


def returned(output, call_id: str = "c1") -> RunItemStreamEvent:
    item = SimpleNamespace(raw_item={"call_id": call_id}, output=output)
    return RunItemStreamEvent(name="tool_output", item=item)


def test_translator_maps_the_five_event_kinds():
    t = StreamTranslator()
    assert t.translate(delta("hi"))[0].data == {"text": "hi"}
    start = t.translate(called("get_risk_label", {"person_id": "P012"}))[0]
    assert (start.name, start.data) == (
        "tool_start",
        {"tool": "get_risk_label", "args": {"person_id": "P012"}},
    )
    end = t.translate(returned({"summary": "P012: at_risk", "rows": 1}))[0]
    assert (end.name, end.data) == (
        "tool_end",
        {"tool": "get_risk_label", "summary": "P012: at_risk", "rows": 1},
    )


def test_translator_handles_error_payloads_and_noise():
    t = StreamTranslator()
    t.translate(called("explain_risk", {}))
    end = t.translate(returned({"error": "not found", "rows": 0}))[0]
    assert end.data["summary"] == "not found"
    assert end.data["rows"] == 0
    assert t.translate(returned("raw text", call_id="zzz"))[0].data["tool"] == "unknown"
    other = RawResponsesStreamEvent(data=SimpleNamespace(type="response.created"))
    assert t.translate(other) == []


class FakeResult:
    def __init__(self, events=(), raises: Exception | None = None):
        self._events, self._raises = list(events), raises

    async def stream_events(self):
        for event in self._events:
            yield event
        if self._raises:
            raise self._raises


def service(result: FakeResult, tracer=None) -> ChatService:
    return ChatService(
        agent=None,  # type: ignore[arg-type]
        sessions=lambda sid: None,  # type: ignore[arg-type,return-value]
        tracer=tracer or NullTracer(),
        max_turns=6,
        run_streamed=lambda *a, **k: result,
    )


async def collect(svc: ChatService):
    return [e async for e in svc.stream("s1", "hello")]


async def test_stream_happy_path_ends_with_done():
    events = await collect(
        service(
            FakeResult(
                [called("t", {}), returned({"summary": "s", "rows": 2}), delta("ok")]
            )
        )
    )
    assert [e.name for e in events] == ["tool_start", "tool_end", "token", "done"]
    assert events[-1].data == {"session_id": "s1"}


async def test_guardrail_trip_is_a_normal_reply_not_an_error():
    guardrail = build_input_guardrails("m")[0]
    out = GuardrailFunctionOutput(
        output_info=GuardrailVerdict(category="treatment"), tripwire_triggered=True
    )
    trip = InputGuardrailTripwireTriggered(
        InputGuardrailResult(guardrail=guardrail, output=out)
    )
    events = await collect(service(FakeResult(raises=trip)))
    assert [e.name for e in events] == ["token", "done"]
    assert events[0].data["text"] == DECLINE_MESSAGES["treatment"]


async def test_max_turns_gives_plain_apology():
    events = await collect(
        service(FakeResult([delta("partial")], raises=MaxTurnsExceeded("too many")))
    )
    assert [e.name for e in events] == ["token", "token", "done"]
    assert events[1].data["text"] == MAX_TURNS_REPLY


async def test_unexpected_exception_becomes_error_event_and_stream_closes():
    events = await collect(service(FakeResult(raises=RuntimeError("db down"))))
    assert [e.name for e in events] == ["error", "done"]
    assert events[0].data == {
        "message": "Something went wrong answering that.",
        "recoverable": True,
    }
    assert "db down" not in json.dumps(events[0].data)


async def test_jsonl_trace_records_the_turn(tmp_path):
    path = tmp_path / "t.jsonl"
    fake = FakeResult(
        [
            called("get_risk_label", {"person_id": "P1"}),
            returned({"summary": "s", "rows": 1}),
            delta("answer"),
        ]
    )
    await collect(service(fake, JsonlTracer(path)))
    line = json.loads(path.read_text().splitlines()[0])
    assert line["message"] == "hello"
    assert line["answer"] == "answer"
    assert line["outcome"] == "ok"
    assert line["tool_calls"][0]["tool"] == "get_risk_label"
    assert line["tool_calls"][0]["rows"] == 1
    assert isinstance(line["latency_ms"], int)


@pytest.mark.parametrize("category", ["diagnosis", "treatment", "identification"])
def test_every_blocking_category_has_a_decline(category):
    assert DECLINE_MESSAGES[category]


def test_translator_accepts_genuine_sdk_items():
    from agents import Agent
    from agents.items import ToolCallItem, ToolCallOutputItem
    from openai.types.responses import ResponseFunctionToolCall, ResponseTextDeltaEvent

    sdk_agent = Agent(name="x")
    call = ResponseFunctionToolCall(
        type="function_call",
        name="get_risk_label",
        call_id="call_1",
        arguments='{"person_id": "P012"}',
    )
    output = ToolCallOutputItem(
        agent=sdk_agent,
        raw_item={"type": "function_call_output", "call_id": "call_1", "output": "{}"},
        output={"summary": "s", "rows": 3},
    )
    text = ResponseTextDeltaEvent(
        type="response.output_text.delta",
        delta="hi",
        item_id="i",
        output_index=0,
        content_index=0,
        sequence_number=1,
        logprobs=[],
    )
    t = StreamTranslator()
    assert t.translate(RawResponsesStreamEvent(data=text))[0].data == {"text": "hi"}
    start = t.translate(
        RunItemStreamEvent(
            name="tool_called", item=ToolCallItem(agent=sdk_agent, raw_item=call)
        )
    )[0]
    assert start.data == {"tool": "get_risk_label", "args": {"person_id": "P012"}}
    end = t.translate(RunItemStreamEvent(name="tool_output", item=output))[0]
    assert end.data == {"tool": "get_risk_label", "summary": "s", "rows": 3}
