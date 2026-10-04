"""Run evals/cases.yaml through the real agent stack and report pass/fail.

Uses the real model (needs LLM_API_KEY and AGENT_MODEL) and whichever data
backend is configured, as of the newest data (the replay clock is off).

    uv run python evals/run.py [--tier 2] [--only 9 10 11] [--include-planned]
"""

import argparse
import asyncio
import re
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agent.analysis.ids import resolve_participant
from agent.auth import CLINICIAN, Principal, patient
from agent.bootstrap import Runtime, build_runtime
from agent.config import Settings
from agent.domain.events import EventHandler

CASES_PATH = Path(__file__).parent / "cases.yaml"
PERSON_ID = re.compile(r"\bPatient (?:IMU-)?\d{2,3}\b")


@dataclass
class CaseOutcome:
    case_id: int
    who: str
    question: str
    tools: list[str]
    answer: str
    seconds: float
    failures: list[str]
    ungrounded: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def check(case: dict, tools: list[str], answer: str) -> list[str]:
    failures: list[str] = []
    for tool in case.get("expect_tools", []):
        if tool not in tools:
            failures.append(f"expected tool {tool}, called {tools or 'none'}")
    if (any_tools := case.get("expect_any_tools")) and not set(any_tools) & set(tools):
        failures.append(f"expected one of {any_tools}, called {tools or 'none'}")
    for tool in case.get("forbid_tools", []):
        if tool in tools:
            failures.append(f"must not call {tool}")
    if case.get("no_tools") and tools:
        failures.append(f"expected no tool calls, got {tools}")
    for pattern in case.get("answer_all", []):
        if not re.search(pattern, answer, re.IGNORECASE):
            failures.append(f"answer lacks /{pattern}/")
    if (any_patterns := case.get("answer_any")) and not any(
        re.search(p, answer, re.IGNORECASE) for p in any_patterns
    ):
        failures.append(f"answer matches none of {any_patterns}")
    for pattern in case.get("answer_none", []):
        if re.search(pattern, answer, re.IGNORECASE):
            failures.append(f"answer must not match /{pattern}/")
    if (minimum := case.get("min_person_ids")) and len(
        set(PERSON_ID.findall(answer))
    ) < minimum:
        failures.append(f"answer names fewer than {minimum} person ids")
    return failures


class _Collector(EventHandler):
    """What an eval asserts on: tools called, the answer text, ungrounded numbers."""

    def __init__(self) -> None:
        self.tools: list[str] = []
        self.tokens: list[str] = []
        self.ungrounded: list[str] = []

    def on_tool_start(self, data: dict[str, Any]) -> None:
        self.tools.append(data["tool"])

    def on_token(self, data: dict[str, Any]) -> None:
        self.tokens.append(data["text"])

    def on_error(self, data: dict[str, Any]) -> None:
        self.tokens.append(f"[error: {data['message']}]")

    def on_done(self, data: dict[str, Any]) -> None:
        self.ungrounded = data.get("ungrounded_numbers", [])


def principal_for(runtime: Runtime, case: dict) -> Principal:
    who = str(case.get("as", "clinician"))
    if who == "clinician":
        return CLINICIAN
    return patient(resolve_participant(who, runtime.store.participants()))


async def run_case(runtime: Runtime, case: dict) -> CaseOutcome:
    started = time.perf_counter()
    collector = _Collector()
    async for event in runtime.chat.stream(
        principal_for(runtime, case), f"eval-{uuid.uuid4().hex}", case["question"]
    ):
        collector.handle(event)
    answer = "".join(collector.tokens)
    failures = check(case, collector.tools, answer)
    if collector.ungrounded:
        failures.append(f"numbers not found in any tool result: {collector.ungrounded}")
    return CaseOutcome(
        case["id"],
        str(case.get("as", "clinician")),
        case["question"],
        collector.tools,
        answer,
        time.perf_counter() - started,
        failures,
        collector.ungrounded,
    )


async def main(args: argparse.Namespace) -> int:
    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    cases = [c for c in cases if c["tier"] <= args.tier]
    if not args.include_planned:
        cases = [c for c in cases if not c.get("planned")]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    # As of the newest data, and with throwaway chat memory so eval threads never
    # show up in a persona's conversation list.
    scratch = Path(tempfile.mkdtemp(prefix="pulsecast-evals-"))
    settings = Settings(  # pyright: ignore[reportCallIssue]
        replay_enabled=False, session_db_path=scratch / "sessions.sqlite"
    )
    runtime = build_runtime(settings)

    outcomes = [await run_case(runtime, case) for case in cases]
    for o in outcomes:
        status = "PASS" if o.passed else "FAIL"
        print(f"[{status}] #{o.case_id:<2} {o.seconds:5.1f}s  {o.who:<11} {o.question}")
        print(f"        tools: {o.tools or 'none'}")
        for failure in o.failures:
            print(f"        - {failure}")
        if args.verbose or not o.passed:
            print(f"        answer: {o.answer.strip()[:400]}")
    passed = sum(o.passed for o in outcomes)
    print(f"\n{passed}/{len(outcomes)} passed")
    return 0 if passed == len(outcomes) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", type=int, default=1, help="run cases up to this tier")
    parser.add_argument("--only", type=int, nargs="*", help="case ids to run")
    parser.add_argument(
        "--include-planned",
        action="store_true",
        help="also run cases that need tools that do not exist yet",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sys.exit(asyncio.run(main(parser.parse_args())))
