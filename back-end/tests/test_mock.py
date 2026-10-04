from agent.data.mock import FEATURES, MockBackend


def test_same_seed_same_numbers():
    a, b = MockBackend(seed=7), MockBackend(seed=7)
    assert a.latest_scores() == b.latest_scores()
    assert a.get_features("P012") == b.get_features("P012")
    assert MockBackend(seed=8).get_features("P012") != a.get_features("P012")


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
