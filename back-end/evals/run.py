"""Run evals/cases.yaml through the real agent stack and report pass/fail.

Uses the real model (needs GEMINI_API_KEY and AGENT_MODEL) and whichever
DATA_BACKEND is configured; the seeded cases assume the mock backend.

    uv run python evals/run.py [--tier 2] [--only 9 10 11]
"""

import argparse
import asyncio
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml

from agent.bootstrap import Runtime, build_runtime

CASES_PATH = Path(__file__).parent / "cases.yaml"
PERSON_ID = re.compile(r"\bP\d{3}\b")


@dataclass
class Outcome:
    case_id: int
    question: str
    tools: list[str]
    answer: str
    seconds: float
    failures: list[str]

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


async def run_case(runtime: Runtime, case: dict) -> Outcome:
    started = time.perf_counter()
    tools: list[str] = []
    tokens: list[str] = []
    async for event in runtime.chat.stream(
        f"eval-{uuid.uuid4().hex}", case["question"]
    ):
        if event.name == "tool_start":
            tools.append(event.data["tool"])
        elif event.name == "token":
            tokens.append(event.data["text"])
        elif event.name == "error":
            tokens.append(f"[error: {event.data['message']}]")
    answer = "".join(tokens)
    return Outcome(
        case["id"],
        case["question"],
        tools,
        answer,
        time.perf_counter() - started,
        check(case, tools, answer),
    )


async def main(args: argparse.Namespace) -> int:
    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    cases = [c for c in cases if c["tier"] <= args.tier]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    runtime = build_runtime()

    outcomes = [await run_case(runtime, case) for case in cases]
    for o in outcomes:
        status = "PASS" if o.passed else "FAIL"
        print(f"[{status}] #{o.case_id:<2} {o.seconds:5.1f}s  {o.question}")
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
    parser.add_argument("-v", "--verbose", action="store_true")
    sys.exit(asyncio.run(main(parser.parse_args())))
