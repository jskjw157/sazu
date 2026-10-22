"""Independent standard offsets, boundary checks and finite Bulletin C evidence.

ERFA 2.0.1 dat.c: https://raw.githubusercontent.com/liberfa/erfa/v2.0.1/src/dat.c
IERS C72: https://hpiers.obspm.fr/iers/bul/bulc/bulletinc.72
No astronomical or KASI expected value is replaced by these tests.
"""
from datetime import UTC, date, datetime

import pytest

from sazu.errors import SazuError
from sazu.serde import digest
from sazu.term_clock import project_tt_to_utc, clock_identity
from tests.test_term_clock_repair import tt_from_utc_with_known_offset


def offset_1960(instant):
    midnight = datetime(instant.year, instant.month, instant.day, tzinfo=UTC)
    mjd = midnight.toordinal() + 1721424.5 - 2400000.5
    fraction = (instant-midnight).total_seconds()/86400
    return 1.417818 + (mjd + fraction - 37300) * .001296


@pytest.mark.parametrize('instant', [
    datetime(1960,1,1,tzinfo=UTC),
    datetime(1960,1,1,0,0,0,1000,tzinfo=UTC),
    datetime(1960,2,29,12,34,56,123456,tzinfo=UTC),
    datetime(1960,7,1,6,30,tzinfo=UTC),
    datetime(1960,12,30,12,0,tzinfo=UTC),
])
def test_1960_standard_affine_offsets_are_supported(instant):
    parts = tt_from_utc_with_known_offset(instant, offset_1960(instant))
    result = project_tt_to_utc(*parts)
    assert result.status == 'historical_utc'
    assert result.comparable_as_utc is True
    assert abs((result.instant_utc-instant).total_seconds()) < .00001
    assert result.production_authorized is False


def test_exact_first_supported_tt_instant_is_not_one_day_early():
    assert offset_1960(datetime(1960,1,1,tzinfo=UTC)) == pytest.approx(.943482)
    parts = (2436934.5, (32.184 + .943482)/86400)
    before = project_tt_to_utc(parts[0], parts[1]-.001/86400)
    at = project_tt_to_utc(*parts)
    assert before.instant_utc is None
    assert before.status == 'historical_clock_unresolved'
    assert at.instant_utc == datetime(1960,1,1,tzinfo=UTC)
    assert at.comparable_as_utc


def test_1961_transition_contains_5ms_step_not_a_constant_offset():
    # Standard coefficients approached from the old segment, then the new one.
    end_of_old_rule = 1.417818 + (37300-37300)*.001296
    new_rule = 1.422818
    assert new_rule-end_of_old_rule == pytest.approx(.005)
    instant = datetime(1961,1,1,tzinfo=UTC)
    result = project_tt_to_utc(*tt_from_utc_with_known_offset(instant, new_rule))
    assert result.instant_utc == instant
    earlier = datetime(1960,12,31,23,59,59,tzinfo=UTC)
    result_before = project_tt_to_utc(*tt_from_utc_with_known_offset(earlier,offset_1960(earlier)))
    # ERFA utctai.c distributes a mini-leap into quasi-JD; d2dtf.c only
    # rescales >0.5s leaps. Keep its display but do not assert exact civil UTC
    # on a step day. This is not an empirically fitted KASI correction.
    assert result_before.status == 'historical_utc_step_day'
    assert not result_before.comparable_as_utc
    assert result_before.instant_utc is not None
    assert result_before.production_authorized is False


@pytest.mark.parametrize('instant', [
    datetime(2026,10,23,tzinfo=UTC),
    datetime(2026,11,22,0,0,tzinfo=UTC),
    datetime(2026,12,31,23,59,59,999000,tzinfo=UTC),
])
def test_c72_supports_late_2026_without_claiming_geometry_accuracy(instant):
    projection = project_tt_to_utc(*tt_from_utc_with_known_offset(instant,37))
    assert projection.status == 'modern_utc'
    assert projection.comparable_as_utc is True
    assert projection.reviewed_at == date(2026,10,22)
    assert projection.utc_offset_confirmed_through == date(2026,12,31)
    assert projection.bulletin_id == 'IERS-Bulletin-C-72'
    assert projection.production_authorized is False


@pytest.mark.parametrize('instant', [datetime(2027,1,1,tzinfo=UTC),
                                     datetime(2050,1,1,tzinfo=UTC)])
def test_no_automatic_extension_beyond_adopted_bulletin_window(instant):
    result = project_tt_to_utc(*tt_from_utc_with_known_offset(instant,37))
    assert result.status == 'future_utc_assumption'
    assert not result.comparable_as_utc
    assert result.instant_utc is not None
    assert result.utc_offset_confirmed_through == date(2026,12,31)
    assert result.future_assumption_policy == 'hold-last-tai-minus-utc-not-confirmed'


def test_identity_contains_reviewed_bulletin_claims_not_just_a_review_date():
    identity = clock_identity()
    assert identity['policy'] == 'erfa-historical-utc-v2-c72'
    assert identity['reviewed_at'] == date(2026,10,22)
    assert identity['utc_offset_confirmed_through'] == date(2026,12,31)
    assert identity['historical_utc_start'] == date(1960,1,1)
    claims = identity['bulletin']
    assert claims['id'] == 'IERS-Bulletin-C-72'
    assert claims['issued_on'] == date(2026,7,6)
    assert claims['source_url'] == 'https://hpiers.obspm.fr/iers/bul/bulc/bulletinc.72'
    assert claims['no_leap_at'] == date(2026,12,31)
    assert claims['tai_minus_utc_seconds'] == 37
    assert identity['bulletin_claims_sha256'] == digest(claims)
    assert identity['bulletin_hash_kind'] == 'normalized-reviewed-claims-not-source-bytes'


def test_explicit_old_cap_is_conservative_and_in_model_identity():
    parts = tt_from_utc_with_known_offset(datetime(2026,11,1,tzinfo=UTC),37)
    current = project_tt_to_utc(*parts)
    restricted = project_tt_to_utc(*parts, reviewed_through=date(2026,10,22))
    assert current.comparable_as_utc
    assert not restricted.comparable_as_utc
    assert restricted.utc_offset_confirmed_through == date(2026,12,31)
    assert restricted.reviewed_through == date(2026,10,22)
    assert current.clock_model_id != restricted.clock_model_id
    assert current.clock_model_id == digest(clock_identity())


@pytest.mark.parametrize('cap',[date(2100,1,1),date(2027,1,1),True,
                                datetime(2026,12,31,tzinfo=UTC),'2026-12-31'])
def test_caller_cannot_extend_the_reviewed_evidence(cap):
    with pytest.raises(SazuError):
        project_tt_to_utc(2451545., reviewed_through=cap)


def test_clock_registry_payload_is_fresh_not_shared_mutable_state():
    first = clock_identity()
    first['bulletin']['no_leap_at'] = date(2050,12,31)
    assert clock_identity()['bulletin']['no_leap_at'] == date(2026,12,31)


@pytest.mark.parametrize('hour',[0,12,23])
def test_subsecond_historical_step_day_is_explicit_not_a_silent_precision_claim(hour):
    instant = datetime(1960,12,31,hour,0,tzinfo=UTC)
    p = project_tt_to_utc(*tt_from_utc_with_known_offset(instant,offset_1960(instant)))
    assert p.status == 'historical_utc_step_day'
    assert not p.comparable_as_utc
    assert p.instant_utc is not None


def test_clock_evidence_status_does_not_change_for_machine_calendar(monkeypatch):
    # The model is frozen; environment variables cannot advance bulletin validity.
    monkeypatch.setenv('SAZU_UTC_CONFIRMED_THROUGH','2099-12-31')
    p = project_tt_to_utc(*tt_from_utc_with_known_offset(datetime(2040,1,1,tzinfo=UTC),37))
    assert p.status == 'future_utc_assumption'
    assert p.utc_offset_confirmed_through == date(2026,12,31)
