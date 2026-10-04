from agent.data.cache import StatsCache


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make(ttl_s):
    loads: list[str] = []

    def load(group):
        loads.append(group)
        return {}

    clock = FakeClock()
    return StatsCache(load, ttl_s, clock), loads, clock


def test_loads_once_per_group_without_a_ttl():
    cache, loads, clock = make(None)
    cache.get("all")
    clock.now += 10_000
    cache.get("all")
    cache.get("at_risk")
    assert loads == ["all", "at_risk"]


def test_reloads_only_the_expired_group():
    cache, loads, clock = make(60.0)
    cache.get("all")
    clock.now += 30
    cache.get("at_risk")
    clock.now += 40  # "all" is 70s old, "at_risk" 40s
    cache.get("all")
    cache.get("at_risk")
    assert loads == ["all", "at_risk", "all"]
