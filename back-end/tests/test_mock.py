from datetime import timedelta

from agent.data.mock import FEATURES, MockBackend
from agent.domain.models import WindowKey


def test_same_seed_same_numbers():
    a, b = MockBackend(seed=7), MockBackend(seed=7)
    assert a.latest_scores() == b.latest_scores()
    key = a.get_score("P012").key
    assert a.get_features(key) == b.get_features(key)
    assert MockBackend(seed=8).get_features(key) != a.get_features(key)


def test_forty_people_two_windows(backend):
    assert len(backend.latest_scores()) == 40
    latest = backend.get_score("P007")
    previous = backend.get_score("P007", window_end=latest.window_end.replace(day=1))
    assert latest
    assert previous
    assert latest.label != previous.label


def test_seeded_edge_cases(backend):
    assert backend.get_score("P999") is None
    assert backend.get_score("P035").score is None
    assert backend.get_score("P031").wear_time_hours < 10
    assert backend.get_score("P038").wear_time_hours < 10
    assert 0.5 <= backend.get_score("P019").confidence <= 0.55
    assert 0.45 <= backend.get_score("P027").confidence <= 0.55


def test_at_risk_group_leans_in_the_risk_direction(backend):
    everyone, at_risk = backend.feature_stats("all"), backend.feature_stats("at_risk")
    for name, spec in FEATURES.items():
        assert (at_risk[name].p50 - everyone[name].p50) * spec.risk_sign >= 0, name


def test_features_match_a_scoring_window_within_a_minute(backend):
    end = backend.get_score("P012").window_end

    def features_at(offset):
        return backend.get_features(
            WindowKey(person_id="P012", window_end=end + offset)
        )

    exact = features_at(timedelta(0))
    assert exact is not None
    assert features_at(timedelta(seconds=1)) == exact
    assert features_at(-timedelta(seconds=59)) == exact
    assert features_at(timedelta(hours=1)) is None


def test_scores_still_need_an_exact_window(backend):
    end = backend.get_score("P012").window_end
    assert backend.get_score("P012", end + timedelta(seconds=1)) is None


def test_history_is_newest_first(backend):
    history = backend.get_history("P007")
    assert [s.window_end for s in history] == sorted(
        (s.window_end for s in history), reverse=True
    )
    assert len(history) == 2
    assert backend.get_history("P007", limit=1) == history[:1]
    assert backend.get_history("P999") == []
