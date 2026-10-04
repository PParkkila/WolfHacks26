from typing import Any

from agent.domain.events import EventHandler, SseEvent
from agent.main import _Printer


class Recording(EventHandler):
    def __init__(self) -> None:
        self.seen: list[tuple[str, dict[str, Any]]] = []

    def on_token(self, data):
        self.seen.append(("token", data))

    def on_tool_start(self, data):
        self.seen.append(("tool_start", data))

    def on_tool_end(self, data):
        self.seen.append(("tool_end", data))

    def on_error(self, data):
        self.seen.append(("error", data))

    def on_done(self, data):
        self.seen.append(("done", data))


def test_each_event_kind_reaches_its_hook_with_its_data():
    handler = Recording()
    kinds = ["token", "tool_start", "tool_end", "error", "done"]
    for kind in kinds:
        handler.handle(SseEvent(kind, {"k": kind}))  # type: ignore[arg-type]
    assert handler.seen == [(kind, {"k": kind}) for kind in kinds]


def test_unoverridden_hooks_ignore_events():
    EventHandler().handle(SseEvent("token", {"text": "hi"}))


def test_cli_printer_splits_answer_and_diagnostics(capsys):
    printer = _Printer()
    printer.handle(SseEvent("tool_start", {"tool": "t", "args": {"a": 1}}))
    printer.handle(SseEvent("tool_end", {"summary": "s"}))
    printer.handle(SseEvent("token", {"text": "answer"}))
    printer.handle(SseEvent("error", {"message": "boom"}))
    out, err = capsys.readouterr()
    assert out == "answer"
    assert "[t {'a': 1}]" in err
    assert "[-> s]" in err
    assert "[error] boom" in err
