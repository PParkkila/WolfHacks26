"""Does every number in an answer come from a tool result?

The prompt demands it ("every number must come from a tool result"); this checks
it. It is detection, not prevention: the answer has already streamed by the time
it can be checked, so callers log and flag the turn rather than block it.
"""

import re
from collections.abc import Iterable
from typing import Any

NUMBER = re.compile(r"(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?")
# "1." / "2)" / "- 3." at the start of a line numbers a list; it says nothing.
LIST_MARKER = re.compile(r"(?m)^\s*(?:[-*]\s*)?\d+[.)]\s+")


def _numbers_in(text: str) -> list[str]:
    return [m.replace(",", "") for m in NUMBER.findall(text)]


def _decimals(number: str) -> int:
    return len(number.partition(".")[2])


def _facts(source: Any) -> Iterable[float]:
    """Every value a source can vouch for.

    Numbers count as themselves and, for probabilities, as a percentage. Numbers
    inside strings (timestamps, summaries) count the same way. So does the length
    of a list, because "5 features" is a fair reading of a five-item list.
    """
    if isinstance(source, bool) or source is None:
        return
    if isinstance(source, int | float):
        yield float(source)
        yield float(source) * 100
    elif isinstance(source, str):
        for n in _numbers_in(source):
            yield from (float(n), float(n) * 100)
    elif isinstance(source, dict):
        for value in source.values():
            yield from _facts(value)
    elif isinstance(source, list | tuple):
        yield float(len(source))
        for value in source:
            yield from _facts(value)


def ungrounded_numbers(answer: str, *sources: Any) -> list[str]:
    """Numbers in `answer` that no source supports, in order of appearance.

    A number matches a source value when they agree to the precision written, so
    "94" matches 94.3 (rounded or truncated) and "87" matches a score of 0.87.
    Pass the tool outputs and the user's message as sources.
    """
    facts = {f for source in sources for f in _facts(source)}
    found: list[str] = []
    for number in _numbers_in(LIST_MARKER.sub("", answer)):
        tolerance = 10.0 ** -_decimals(number)
        if number not in found and not any(
            abs(float(number) - fact) < tolerance for fact in facts
        ):
            found.append(number)
    return found
