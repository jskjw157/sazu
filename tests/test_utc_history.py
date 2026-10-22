"""Historical UTC regressions; expectations use ERFA/SOFA published drift constants."""
from datetime import UTC, datetime
import pytest
from sazu.errors import SazuError


def convert(jd1, jd2):
    # A missing module is made an assertion failure, not a collection error.
    import importlib.util
    assert importlib.util.find_spec('sazu.utc_history') is not None, 'historical UTC converter missing'
    from sazu.utc_history import historical_utc_from_tt
    return historical_utc_from_tt(jd1, jd2)


@pytest.mark.parametrize('year,month,day,mjd,offset', [
    (1960,1,1,36934,0.943482),
    (1961,1,1,37300,1.422818),
    (1961,8,1,37512,1.647570),
    (1965,1,1,38761,3.540130),
    (1968,2,1,39887,6.185682),
])
def test_published_piecewise_drift_midnights(year,month,day,mjd,offset):
    value=convert(2400000.5+mjd,(32.184+offset)/86400)
    assert abs((value-datetime(year,month,day,tzinfo=UTC)).total_seconds()) <= 0.000002


def test_fractional_day_drift_not_rounded_to_integer_leap_seconds():
    offset=1.422818+0.5*0.001296
    value=convert(2437300.5,0.5+(32.184+offset)/86400)
    assert abs((value-datetime(1961,1,1,12,tzinfo=UTC)).total_seconds()) <= 0.000002


@pytest.mark.parametrize('a,b',[(True,0.0),(None,0.0),(float('nan'),0.0),(2437300.5,float('inf'))])
def test_invalid_split_jd(a,b):
    with pytest.raises(SazuError):convert(a,b)


@pytest.mark.parametrize('a,b',[(2433282.5,0.0),(2441317.5,42.184/86400),(2451545.0,0.0)])
def test_not_a_proleptic_or_modern_converter(a,b):
    with pytest.raises(SazuError) as exc:convert(a,b)
    assert exc.value.code=='UNSUPPORTED_RANGE'


def test_split_precision_preserved():
    fraction=(32.184+1.422818)/86400 + 0.123456/86400
    value=convert(2437300.5,fraction)
    assert abs((value-datetime(1961,1,1,0,0,0,123456,tzinfo=UTC)).total_seconds()) <= 0.000002


def test_missing_erfa_does_not_silently_fall_back(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules,'erfa',None)
    with pytest.raises(SazuError) as exc:convert(2437300.5,33.606818/86400)
    assert exc.value.code=='SOURCE_NOT_AVAILABLE'


def project(jd1, jd2, old):
    from types import SimpleNamespace
    import sazu.utc_history as module
    assert hasattr(module, 'project_solar_time'), 'solar event clock policy missing'
    return module.project_solar_time(SimpleNamespace(whole=jd1,tt_fraction=jd2,
                                                      utc_datetime=lambda: old))


def test_historical_projection_uses_correct_utc_not_legacy():
    old=datetime(1960,12,31,23,59,51,422818,tzinfo=UTC)
    instant,basis=project(2437300.5,33.606818/86400,old)
    assert instant==datetime(1961,1,1,tzinfo=UTC)
    assert basis=='erfa_historical_utc'


def test_preutc_projection_is_preserved_but_not_disguised_as_historical_utc():
    old=datetime(1950,1,1,tzinfo=UTC)
    instant,basis=project(2433282.5,42.184/86400,old)
    assert instant==old and basis=='legacy_pre1960_projection'


def test_modern_utc_is_not_replaced_with_ut1():
    old=datetime(2026,2,3,20,2,7,930494,tzinfo=UTC)
    instant,basis=project(2461075.5,0.1,old)
    assert instant is old and basis=='skyfield_utc_leap_table'


def test_exact_utc_era_boundary_classified_using_tt_not_legacy_wall_date():
    old=datetime(1959,12,31,23,59,50,tzinfo=UTC)
    instant,basis=project(2436934.5,33.127482/86400,old)
    assert instant==datetime(1960,1,1,tzinfo=UTC)
    assert basis=='erfa_historical_utc'


def test_identity_records_compiled_library_and_actual_time_table():
    from sazu.utc_history import erfa_identity
    data=erfa_identity()
    assert data['pyerfa']=='2.0.1.5'
    assert len(data['compiled_sha256'])==len(data['utc_table_sha256'])==64
    assert data['policy']=='utc-history-erfa-1960-1971-v1'


def test_event_requires_honest_clock_label_for_historical_projection():
    from dataclasses import replace
    from tests.test_term_audit import comparison_inputs
    doc,events=comparison_inputs(1950,1950)
    assert hasattr(events[0],'clock_basis'), 'event clock provenance missing'
    legacy=replace(events[0],clock_basis='legacy_pre1960_projection')
    from sazu.term_audit import compare_term_range
    report=compare_term_range([legacy]+events[1:],doc,1950,1950)
    assert report['clock_basis_counts']['legacy_pre1960_projection']==1
    assert report['clock_review_required'] is True
    assert report['production_authorized'] is False


def test_invalid_clock_label_rejected():
    from dataclasses import replace
    from tests.test_term_audit import comparison_inputs
    _,events=comparison_inputs()
    assert hasattr(events[0],'clock_basis'), 'event clock provenance missing'
    with pytest.raises(SazuError):replace(events[0],clock_basis='officially_certified_UTC')


def test_clock_diagnostic_uses_same_tt_event_not_old_dut1_added_to_corrected_utc():
    from types import SimpleNamespace
    import tools.diagnose_term_clocks as module
    assert hasattr(module,'ut1_display_shift'), 'corrected UTC diagnosis missing'
    corrected=datetime(1961,1,1,tzinfo=UTC)
    legacy=datetime(1960,12,31,23,59,51,tzinfo=UTC)
    event=SimpleNamespace(instant_utc=corrected,tt_jd=2437300.5)
    ts=SimpleNamespace(tt_jd=lambda value:SimpleNamespace(utc_datetime=lambda:legacy,dut1=9.2))
    assert abs(module.ut1_display_shift(event,ts)-0.2)<1e-6
