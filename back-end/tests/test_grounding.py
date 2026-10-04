import pytest

from agent.analysis.grounding import ungrounded_numbers

OUTPUT = {
    "summary": "P012: at_risk (score 0.87, confidence 0.91)",
    "rows": 1,
    "model_version": "mock-v0.1",
    "window": {
        "start": "2026-10-01T00:00:00+00:00",
        "end": "2026-10-02T00:00:00+00:00",
    },
    "person_id": "P012",
    "score": 0.87,
    "confidence": 0.91,
    "wear_time_hours": 22.5,
    "top_features": [{"percentile": 94.3, "value": 80.2}, {"percentile": 12.0}],
}


@pytest.mark.parametrize(
    "answer",
    [
        "P012 scores 0.87 with confidence 0.91.",
        "P012 is flagged at 87%, confidence 91%.",  # probabilities as percentages
        "Resting HR sits at the 94th percentile (value 80.2).",
        "Wear time was 22.5 hours for the window ending 2026-10-02 (model v0.1).",
        "It sits near the 94th percentile.",  # truncated rather than rounded
        "It sits near the 94.3th percentile.",
        "The top 2 features are listed.",  # a list length
        "1. First finding\n2. Second finding",  # list markers say nothing
    ],
)
def test_supported_numbers_pass(answer):
    assert ungrounded_numbers(answer, OUTPUT) == []


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("P012 scores 0.93.", ["0.93"]),
        ("Their HbA1c is 6.8.", ["6.8"]),
        ("About 42% of the cohort is flagged.", ["42"]),
        ("That is 3 times the usual rate, or 3 times again.", ["3"]),  # deduplicated
    ],
)
def test_unsupported_numbers_are_reported_once_in_order(answer, expected):
    assert ungrounded_numbers(answer, OUTPUT) == expected


def test_the_users_own_numbers_count():
    assert ungrounded_numbers("Here are the top 5.", "Give me the top 5") == []


def test_nothing_is_grounded_without_sources():
    assert ungrounded_numbers("The score is 0.87.") == ["0.87"]
