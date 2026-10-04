"""CLI: `agent serve` runs the API; `agent ask "..."` answers one question."""

import argparse
import asyncio
import sys
import uuid

import uvicorn


async def _ask(question: str, session_id: str) -> None:
    from agent.bootstrap import build_runtime

    runtime = build_runtime()
    async for event in runtime.chat.stream(session_id, question):
        if event.name == "token":
            print(event.data["text"], end="", flush=True)
        elif event.name == "tool_start":
            print(f"\n  [{event.data['tool']} {event.data['args']}]", file=sys.stderr)
        elif event.name == "tool_end":
            print(f"  [-> {event.data['summary']}]", file=sys.stderr)
        elif event.name == "error":
            print(f"\n[error] {event.data['message']}", file=sys.stderr)
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
        asyncio.run(_ask(args.question, args.session or uuid.uuid4().hex))


if __name__ == "__main__":
    main()
