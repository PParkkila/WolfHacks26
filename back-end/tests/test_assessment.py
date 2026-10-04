from datetime import UTC, datetime

import pytest

from agent.analysis.quality import ReliabilityPolicy
from agent.assessment import Assessor


@pytest.fixture
def assessor(backend) -> Assessor:
    return Assessor(backend, ReliabilityPolicy())


def test_unknown_person_is_none(assessor):
    assert assessor.assess("P999") is None


def test_reliable_person(assessor):
    a = assessor.assess("P012")
    assert a is not None
    assert a.reliable
    assert a.quality.verdict == "good"
    assert a.reliability.abstain_reason is None


@pytest.mark.parametrize(
    ("person", "reason"),
    [
        ("P031", "insufficient_data_quality"),
        ("P019", "low_confidence"),
        ("P035", "not_scored"),
    ],
)
def test_unreliable_people_carry_the_reason(assessor, person, reason):
    a = assessor.assess(person)
    assert a is not None
    assert not a.reliable
    assert a.reliability.abstain_reason == reason


def test_window_selects_an_earlier_scoring_window(assessor):
    latest = assessor.assess("P007")
    previous = assessor.assess("P007", datetime(2026, 10, 1, tzinfo=UTC))
    assert latest is not None
    assert previous is not None
    assert latest.score.label == "at_risk"
    assert previous.score.label == "not_at_risk"
    assert assessor.assess("P007", datetime(2020, 1, 1, tzinfo=UTC)) is None


def test_assess_all_includes_unscored_people(assessor):
    everyone = assessor.assess_all()
    assert len(everyone) == 40
    assert sum(not a.reliable for a in everyone) >= 5  # seeded edge cases
