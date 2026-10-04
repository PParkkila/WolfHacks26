"""CLI: `agent serve` runs the API; `agent ask "..."` answers one question."""

import argparse
import asyncio
import sys
import uuid
from typing import Any

import uvicorn

from agent.domain.events import EventHandler


class _Printer(EventHandler):
    """The answer goes to stdout; tool calls and errors go to stderr."""

    def on_token(self, data: dict[str, Any]) -> None:
        print(data["text"], end="", flush=True)

    def on_tool_start(self, data: dict[str, Any]) -> None:
        print(f"\n  [{data['tool']} {data['args']}]", file=sys.stderr)

    def on_tool_end(self, data: dict[str, Any]) -> None:
        print(f"  [-> {data['summary']}]", file=sys.stderr)

    def on_data(self, data: dict[str, Any]) -> None:
        series = data["chart"].get("series", [])
        print(f"  [chart: {len(series)} series]", file=sys.stderr)

    def on_error(self, data: dict[str, Any]) -> None:
        print(f"\n[error] {data['message']}", file=sys.stderr)


async def _ask(question: str, session_id: str, who: str) -> None:
    from agent.analysis.ids import resolve_participant
    from agent.auth import CLINICIAN, patient
    from agent.bootstrap import build_runtime
    from agent.config import Settings

    # A one-off question has no shared replay clock: answer as of the newest data.
    runtime = build_runtime(Settings(replay_enabled=False))  # pyright: ignore[reportCallIssue]
    principal = (
        CLINICIAN
        if who == "clinician"
        else patient(resolve_participant(who, runtime.store.participants()))
    )
    print(f"[as {principal.display_name}, now {runtime.clock.now()}]", file=sys.stderr)
    printer = _Printer()
    async for event in runtime.chat.stream(principal, session_id, question):
        printer.handle(event)
    print()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="agent")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    ask = commands.add_parser("ask", help="ask one question without a server")
    ask.add_argument("question")
    ask.add_argument("--session", default=None, help="session id (default: new)")
    ask.add_argument(
        "--as",
        dest="who",
        default="clinician",
        help='"clinician" (default) or a participant, e.g. "13" for Patient 013',
    )

    args = parser.parse_args(argv)
    if args.command == "serve":
        uvicorn.run(
            "agent.api.app:create_default_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    else:
        asyncio.run(_ask(args.question, args.session or uuid.uuid4().hex, args.who))


if __name__ == "__main__":
    main()
