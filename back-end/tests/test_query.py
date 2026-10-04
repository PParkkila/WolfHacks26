from datetime import timedelta

import pytest
from support import OTHER, PID, FakeTime

from agent.auth import CLINICIAN, patient
from agent.clock import ReplayClock
from agent.domain.errors import ForbiddenError, QueryError
from agent.domain.metrics import GLUCO_CHANGE, GLUCO_SCORE, METRICS
from agent.query import QueryService, QuerySpec


def test_clinician_sees_everyone_patient_only_themselves(clinician, me):
    assert len(clinician.visible()) == 17
    assert me.visible() == [PID]
    assert [r.person_id for r in me.participants()] == [PID]


def test_patient_cannot_name_anyone_else_even_by_short_ref(me):
    assert me.resolve("13") == PID
    for ref in ("2", OTHER, "nobody"):
        with pytest.raises(ForbiddenError):
            me.resolve(ref)
    with pytest.raises(ForbiddenError):
        me.query(QuerySpec(participants=["2"]))


def test_patient_gets_no_cohort_data(me):
    with pytest.raises(ForbiddenError):
        me.query(QuerySpec(group_by="cohort"))
    with pytest.raises(ForbiddenError):
        me.cohort_overview()
    with pytest.raises(ForbiddenError):
        me.cohort_position(PID)
    assert me.catalog().group_bys == ["participant"]


def test_query_defaults_to_the_last_week_hourly(clinician):
    result = clinician.query(QuerySpec(participants=["13"]))
    assert result.end == clinician.as_of()
    assert result.start == result.end - timedelta(hours=168)
    [series] = result.series
    assert len(series.points) == 168
    assert series.participant_id == PID
    assert result.units == {GLUCO_SCORE: METRICS[GLUCO_SCORE].unit}


def test_query_rejects_bad_specs_with_help(clinician):
    with pytest.raises(QueryError) as exc:
        clinician.query(QuerySpec(metrics=["glucose"]))
    assert "gluco_score" in exc.value.details["suggestions"]
    with pytest.raises(QueryError):
        clinician.query(QuerySpec(sort_by="hr_mean_bpm_24h"))
    with pytest.raises(QueryError):
        clinician.query(QuerySpec(start=clinician.as_of(), end=clinician.as_of()))


def test_ranking_with_one_value_per_participant(clinician):
    result = clinician.query(
        QuerySpec(bucket="all", agg="last", sort_by=GLUCO_SCORE, order="asc", limit=3)
    )
    values = [s.points[0][GLUCO_SCORE] for s in result.series]
    assert values == sorted(values)
    assert (result.total_series, len(result.series), result.truncated) == (17, 3, True)
    lowest = clinician.participants(GLUCO_SCORE, "asc")[0]
    assert result.series[0].participant_id == lowest.person_id


def test_cohort_series_pools_everyone_by_day(clinician):
    result = clinician.query(
        QuerySpec(metrics=["hr_mean_bpm_24h"], bucket="day", group_by="cohort")
    )
    [series] = result.series
    assert series.participant_id is None
    assert all(p["participants"] >= 16 for p in series.points)


def test_explain_change_compares_with_then_and_with_own_week(clinician):
    report = clinician.explain_change(PID, hours=24)
    gluco = next(c for c in report.changes if c.metric == GLUCO_SCORE)
    assert report.then_window_end == report.now_window_end - timedelta(hours=24)
    assert gluco.delta is not None
    assert gluco.delta < -40  # the pinned sharp drop
    assert gluco.z_vs_baseline is not None
    assert gluco.z_vs_baseline < -2
    assert GLUCO_CHANGE not in {c.metric for c in report.changes}
    assert 0 < len(report.largest_shifts) <= 3


def test_imu_participant_has_no_heart_rate_and_that_is_not_an_error(clinician):
    row = clinician.participant(clinician.resolve("IMU-00"))
    assert row.values["hr_mean_bpm_24h"] is None
    report = clinician.explain_change(row.person_id)
    hr = next(c for c in report.changes if c.metric == "hr_mean_bpm_24h")
    assert (hr.now, hr.delta) == (None, None)
    with pytest.raises(QueryError):
        clinician.compare_to_cohort(row.person_id, "hr_mean_bpm_24h")


def test_cohort_overview(clinician):
    overview = clinician.cohort_overview()
    assert overview.participants == 17
    assert overview.lowest_gluco[0].person_id == clinician.participants()[0].person_id
    assert all((r.values[GLUCO_CHANGE] or 0) < 0 for r in overview.biggest_drops)
    assert PID in {r.person_id for r in overview.biggest_drops}
    assert overview.gluco_score is not None
    assert overview.gluco_score.n == 17


def test_compare_to_cohort(clinician):
    comparison = clinician.compare_to_cohort(PID, GLUCO_SCORE)
    assert comparison.cohort_size == 17
    assert comparison.direction == "below"


def test_everything_stops_at_the_replay_clock(store):
    time = FakeTime()
    clock = ReplayClock(store.data_range, seconds_per_hour=10, time_source=time)
    svc = QueryService(store, clock, CLINICIAN)
    start = clock.now()
    assert start is not None
    assert svc.latest(PID).window_end == start
    result = svc.query(QuerySpec(participants=[PID], hours=1000, bucket="raw"))
    assert result.series[0].points[-1]["t"] == start

    time.now += 30  # three simulated hours
    fresh = svc.windows_between(start, clock.now())
    assert len(fresh) == 3 * 17
    patient_view = QueryService(store, clock, patient(PID))
    assert len(patient_view.windows_between(start, clock.now())) == 3
