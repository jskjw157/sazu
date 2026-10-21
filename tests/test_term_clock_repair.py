"""IERS reference offsets are independent of the algorithm being tested.

These tests verify clock conversion, not solar geometry or KASI agreement.
"""
from datetime import UTC, date, datetime, timedelta
import importlib

import pytest

from sazu.errors import SazuError


def repair():
    spec = importlib.util.find_spec('sazu.term_clock')
    assert spec is not None, 'Missing reviewed clock projection; legacy pre-1972 UTC is unsafe'
    return importlib.import_module('sazu.term_clock')


def tt_from_utc_with_known_offset(utc, offset):
    # TT = UTC + (TAI-UTC from IERS) + 32.184 s. Split the JD to retain precision.
    midnight = datetime(utc.year, utc.month, utc.day, tzinfo=UTC)
    jd_midnight = float(midnight.toordinal()) + 1721424.5
    fraction = ((utc-midnight).total_seconds()+offset+32.184)/86400
    return jd_midnight, fraction


@pytest.mark.parametrize('instant,offset', [
    (datetime(1961,1,1,tzinfo=UTC), 1.422818),
    (datetime(1962,1,1,tzinfo=UTC), 1.845858),
    (datetime(1965,1,1,tzinfo=UTC), 3.540130),
    (datetime(1965,7,1,tzinfo=UTC), 3.974706),
    (datetime(1968,2,1,tzinfo=UTC), 6.185682),
    (datetime(1972,1,1,tzinfo=UTC), 10.0),
    (datetime(2017,1,1,tzinfo=UTC), 37.0),
])
def test_known_iers_utc_offsets(instant, offset):
    projection = repair().project_tt_to_utc(*tt_from_utc_with_known_offset(instant, offset))
    assert projection.instant_utc is not None
    assert abs((projection.instant_utc-instant).total_seconds()) < .001
    assert projection.status in {'historical_utc', 'modern_utc'}
    assert projection.production_authorized is False
    assert len(projection.clock_model_id) == 64


def test_pre_1961_is_not_fabricated_utc_or_relabelled_ut1():
    p = repair().project_tt_to_utc(2433282.5, .5)  # 1950-Jan-01 noon TT
    assert p.instant_utc is None
    assert p.status == 'historical_clock_unresolved'
    assert p.comparable_as_utc is False
    assert p.production_authorized is False


def test_future_model_is_not_treated_as_confirmed_civil_utc():
    parts = tt_from_utc_with_known_offset(datetime(2049,1,1,tzinfo=UTC), 37)
    p = repair().project_tt_to_utc(*parts)
    assert p.status == 'future_utc_assumption'
    assert p.comparable_as_utc is False
    assert p.instant_utc is not None
    assert p.production_authorized is False


def test_review_horizon_is_explicit_and_does_not_use_machine_date():
    parts = tt_from_utc_with_known_offset(datetime(2026,10,22,tzinfo=UTC), 37)
    old = repair().project_tt_to_utc(*parts, reviewed_through=date(2026,9,1))
    recent = repair().project_tt_to_utc(*parts, reviewed_through=date(2026,10,22))
    assert old.status == 'future_utc_assumption'
    assert recent.status == 'modern_utc'
    assert old.clock_model_id != recent.clock_model_id


@pytest.mark.parametrize('a,b',[(True,0.),(float('nan'),0.),(2451545.,float('inf')),
                               ('2451545',0.),(2451545.,True),(1.,0.)])
def test_invalid_julian_time_does_not_coerce(a,b):
    with pytest.raises(SazuError):
        repair().project_tt_to_utc(a,b)


def test_native_leap_second_is_not_coerced_to_235959():
    # 2017-Jan-01 00:00:36 TAI = 2016-Dec-31 23:59:60 UTC.
    p = repair().project_tt_to_utc(2457754.5, (36+32.184)/86400)
    assert p.status == 'leap_second_unrepresentable'
    assert p.instant_utc is None
    assert p.comparable_as_utc is False


def test_repeated_projection_identical():
    a = repair().project_tt_to_utc(2438761.5, 35.724130/86400)
    b = repair().project_tt_to_utc(2438761.5, 35.724130/86400)
    assert a == b


@pytest.mark.parametrize('year,month,base,mjd_ref,rate', [
    (1961,1,1.422818,37300,.001296), (1961,8,1.372818,37300,.001296),
    (1962,1,1.845858,37665,.0011232), (1963,11,1.945858,37665,.0011232),
    (1964,1,3.240130,38761,.001296), (1964,4,3.340130,38761,.001296),
    (1964,9,3.440130,38761,.001296), (1965,1,3.540130,38761,.001296),
    (1965,3,3.640130,38761,.001296), (1965,7,3.740130,38761,.001296),
    (1965,9,3.840130,38761,.001296), (1966,1,4.313170,39126,.002592),
    (1968,2,4.213170,39126,.002592),
])
def test_iers_rate_is_applied_within_each_historical_segment(year,month,base,mjd_ref,rate):
    instant = datetime(year,month,15,12,34,56,123456,tzinfo=UTC)
    midnight = datetime(year,month,15,tzinfo=UTC)
    mjd = midnight.toordinal()+1721424.5-2400000.5
    fraction = (instant-midnight).total_seconds()/86400
    offset = base + (mjd+fraction-mjd_ref)*rate
    p = repair().project_tt_to_utc(*tt_from_utc_with_known_offset(instant,offset))
    assert abs((p.instant_utc-instant).total_seconds()) < .001


def test_mutated_erfa_table_cannot_inherit_reviewed_clock_status(monkeypatch):
    import erfa
    original = erfa.leap_seconds.get()
    altered = original.copy()
    altered[-1]['tai_utc'] = 38
    monkeypatch.setattr(erfa.leap_seconds, 'get', lambda: altered)
    with pytest.raises(SazuError) as error:
        repair().project_tt_to_utc(*tt_from_utc_with_known_offset(datetime(2020,1,1,tzinfo=UTC),37))
    assert error.value.code == 'SOURCE_CONFLICT'


def test_unreviewed_future_horizon_cannot_be_selected_by_request():
    with pytest.raises(SazuError):
        repair().project_tt_to_utc(2451545., reviewed_through=date(2100,1,1))


def test_large_integer_is_a_domain_error_not_python_overflow():
    with pytest.raises(SazuError):
        repair().project_tt_to_utc(10**1000)


def test_cli_new_generation_routes_to_reviewed_projection(monkeypatch, tmp_path):
    from sazu import cli
    from sazu.serde import canonical_json
    from tests.test_core import manifest
    import json
    # The CLI may not re-expose an unreviewed UTC datetime from the legacy path.
    def forbidden(*args):
        pytest.fail('CLI still calls the legacy UTC generator')
    monkeypatch.setattr(cli, 'generate_terms', forbidden, raising=False)
    sentinel = ({'clock': {'status':'historical_clock_unresolved','instant_utc':None}},)
    monkeypatch.setattr(cli, 'generate_reviewed_terms', lambda *args: sentinel, raising=False)
    payload = {'path':str(tmp_path/'unused.bsp'), 'year':1950,
               'manifest':json.loads(canonical_json(manifest(clock='TDB',precision='computed')))}
    assert cli.dispatch('generate-terms', payload) == sentinel


def test_ephemeris_metadata_survives_projection_without_legacy_utc():
    from sazu.solar_terms import SolarTermEvent
    instant = datetime(1965,2,4,tzinfo=UTC)
    # Arbitrary test event: verifies transport of TT and metadata, not solar astronomy.
    first, second = tt_from_utc_with_known_offset(instant,3.584194)
    event = SolarTermEvent(1965,1,'입춘',315,instant-timedelta(seconds=6),None,
                           'computed',None,None,'synthetic','a'*64,
                           first+second,'b'*64,1e-8)
    projected = repair().project_computed_term(event)
    assert abs((projected.clock.instant_utc-instant).total_seconds()) < .001
    assert projected.tt_jd == event.tt_jd
    assert projected.ephemeris_model_id == event.model_id
    assert projected.model_id != event.model_id
    assert projected.source_sha256 == event.source_sha256
    assert projected.clock.status == 'historical_utc'
    assert projected.production_authorized is False
