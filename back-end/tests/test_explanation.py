import pytest

from agent.analysis.quality import ReliabilityPolicy
from agent.assessment import Assessor
from agent.explanation import Explainer, Explanation, NoFeatures, Withheld


@pytest.fixture
def assess(backend):
    return Assessor(backend, ReliabilityPolicy()).assess


@pytest.fixture
def explainer(backend) -> Explainer:
    return Explainer(backend, backend)


def explain(explainer, assess, person):
    assessment = assess(person)
    assert assessment is not None
    return explainer.explain(assessment)


def test_reliable_person_gets_top_five_by_abs_z(explainer, assess):
    out = explain(explainer, assess, "P012")
    assert isinstance(out, Explanation)
    zs = [abs(d.z_score) for d in out.deviations]
    assert len(zs) == 5
    assert zs == sorted(zs, reverse=True)
    assert out.tension.present is False


def test_label_contradicted_by_features_is_flagged(explainer, assess):
    out = explain(explainer, assess, "P024")
    assert isinstance(out, Explanation)
    assert out.tension.present is True
    assert out.tension.opposed > out.tension.aligned


@pytest.mark.parametrize(
    ("person", "reason"),
    [
        ("P031", "insufficient_data_quality"),
        ("P019", "low_confidence"),
        ("P035", "not_scored"),
    ],
)
def test_unreliable_assessment_is_withheld_without_reading_features(
    backend, assess, person, reason
):
    class ExplodingFeatures:
        def get_features(self, *_args):
            raise AssertionError("features must not be read for a withheld case")

    out = explain(Explainer(ExplodingFeatures(), backend), assess, person)
    assert out == Withheld(reason)


def test_missing_feature_vector(backend, assess):
    class NoVectors:
        def get_features(self, *_args):
            return None

    assert explain(Explainer(NoVectors(), backend), assess, "P012") == NoFeatures()
