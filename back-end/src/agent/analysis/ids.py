"""Participant ids: display names and resolving what people type.

Keys look like "demo:big_ideas:013" or "demo:imu50:00". People type "13",
"P013", "participant 13", "imu50" or the full key; `resolve_participant` maps
all of them to the one key they mean.
"""

import difflib
import re
from collections.abc import Iterable

from agent.domain.errors import AmbiguousPersonError, PersonNotFoundError

DATASET_HINTS = {"imu": "imu50", "big": "big_ideas"}


def _parts(person_id: str) -> tuple[str, str]:
    """(dataset, number) of a key; tolerant of keys without a dataset part."""
    segments = person_id.split(":")
    number = segments[-1]
    dataset = segments[-2] if len(segments) >= 2 else ""
    return dataset, number


def display_name(person_id: str) -> str:
    dataset, number = _parts(person_id)
    if dataset.startswith("imu"):
        return f"Patient IMU-{number}"
    return f"Patient {number}"


def _hint(text: str) -> str | None:
    return next((ds for key, ds in DATASET_HINTS.items() if key in text), None)


def resolve_participant(ref: str, known: Iterable[str]) -> str:
    """The one known key `ref` names.

    Raises PersonNotFoundError (with close matches) or AmbiguousPersonError.
    """
    known = list(known)
    text = ref.strip()
    if text in known:
        return text
    lowered = text.lower()
    exact_suffix = [k for k in known if k.lower().endswith(lowered) and ":" in lowered]
    if len(exact_suffix) == 1:
        return exact_suffix[0]

    hint = _hint(lowered)
    # Drop dataset names so their digits ("imu50") are not read as a number.
    stripped = re.sub(r"imu[-_ ]?50|imu|big[-_ ]?ideas", " ", lowered)
    numbers = re.findall(r"\d+", stripped)
    candidates = [
        k
        for k in known
        if (hint is None or _parts(k)[0] == hint)
        and (
            not numbers
            or (_parts(k)[1].isdigit() and int(_parts(k)[1]) == int(numbers[-1]))
        )
    ]
    if (numbers or hint) and len(candidates) == 1:
        return candidates[0]
    if (numbers or hint) and len(candidates) > 1:
        raise AmbiguousPersonError(ref, candidates)
    raise PersonNotFoundError(
        ref, difflib.get_close_matches(text, known, n=3, cutoff=0.4)
    )
