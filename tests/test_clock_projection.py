"""Independent civil-time anchors, not KASI-fitted offsets.

TAI-UTC anchors: ERFA/SOFA dat.c, USNO tai-utc.dat.  TT = TAI+32.184s.
The leap-second example is the SOFA time-scale cookbook's supported UTC form.
"""
import importlib.util
from datetime import UTC, datetime
import math

import pytest

from sazu.errors import SazuError


def module():
    assert importlib.util.find_spec('sazu.clock_projection') is not None, 'clock projection missing'
    from sazu import clock_projection
    return clock_projection


@pytest.mark.parametrize('day,seconds,expected,status', [
    (2437300.5, 33.606818, datetime(1961,1,1,tzinfo=UTC), 'historical_utc_drift'),
    (2438761.5, 35.724130, datetime(1965,1,1,tzinfo=UTC), 'historical_utc_drift'),
    (2441317.5, 42.184, datetime(1972,1,1,tzinfo=UTC), 'utc_leap_table'),
    (2457754.5, 69.184, datetime(2017,1,1,tzinfo=UTC), 'utc_leap_table'),
    (2461406.5, 69.184, datetime(2027,1,1,tzinfo=UTC), 'utc_future_assumption'),
])
def test_independent_utc_anchors(day, seconds, expected, status):
    result = module().project_tt(day, seconds/86400)
    assert result.instant_utc == expected
    assert result.status == status
    assert result.policy_id == 'sofa-utc-v2'
    assert result.production_authorized is False


def test_utc_drift_depends_on_fraction_of_day():
    # 1965-Jan-01 noon: drift increases 0.001296 / 2 seconds after midnight.
    result = module().project_tt(2438761.5, (43200+35.724130+0.000648)/86400)
    assert result.instant_utc == datetime(1965,1,1,12,tzinfo=UTC)


def test_pre_1960_is_not_synthetic_utc():
    result = module().project_tt(2433282.5, 0.)
    assert result.status == 'utc_undefined_before_1960'
    assert result.instant_utc is None and result.utc_text is None
    assert result.tt_day == 2433282.5 and result.tt_fraction == 0.


def test_leap_second_never_squashed_into_previous_second():
    # TT at 2016-Dec-31 23:59:60.5 UTC = 2017-Jan-01 00:01:08.684 TT.
    result = module().project_tt(2457754.5, 68.684/86400)
    assert result.instant_utc is None
    assert result.utc_text == '2016-12-31T23:59:60.500000Z'
    assert result.status == 'utc_leap_second'


def test_modern_fraction_precision_preserved():
    result = module().project_tt(2457754.5, 69.307456/86400)
    assert result.instant_utc == datetime(2017,1,1,0,0,0,123456,tzinfo=UTC)


@pytest.mark.parametrize('day,fraction', [(True,0.),(2457754.5,True),('2457754.5',0.),
    (math.nan,0.),(math.inf,0.),(2457754.5,math.inf),(2457754.5,1.),
    (2457754.5,-1.),(0.,0.)])
def test_invalid_two_part_jd_rejected(day,fraction):
    with pytest.raises(SazuError) as error:
        module().project_tt(day,fraction)
    assert error.value.code in ('INVALID_INPUT','UNSUPPORTED_RANGE')


def test_version_manifest_is_explicit_and_stable():
    m = module()
    first=m.projection_identity(); second=m.projection_identity()
    assert first == second
    assert first['policy_id']=='sofa-utc-v2'
    assert first['pyerfa']=='2.0.1.5'
    assert len(first['leap_table_sha256'])==64
    assert first['confirmed_before_utc']=='2027-01-01T00:00:00Z'
    assert 'bulletinc-072' in first['confirmation_source']
    first['policy_id']='tampered'
    assert m.projection_identity()['policy_id']=='sofa-utc-v2'


def test_future_erfa_warning_is_visible_not_an_exception():
    result=module().project_tt(2469807.5,69.184/86400) # 2050-Jan-01
    assert result.status=='utc_future_assumption'
    assert result.instant_utc==datetime(2050,1,1,tzinfo=UTC)
    assert 'future_leap_seconds_not_predicted' in result.assumptions


def test_projection_does_not_depend_on_os_timezone(monkeypatch):
    m=module()
    baseline=m.project_tt(2438761.5,35.724130/86400)
    monkeypatch.setenv('TZ','America/New_York')
    assert m.project_tt(2438761.5,35.724130/86400)==baseline


def generated_year(year, tmp_path, monkeypatch):
    """Inject independently anchored TT events, not a mock conversion result."""
    from datetime import date
    from dataclasses import replace
    from types import SimpleNamespace
    import skyfield.api
    from skyfield import almanac, almanac_east_asia
    import sazu.solar_terms as terms
    from tests.test_core import manifest
    import erfa
    times=[]
    indices=[]
    for term in (terms.TERMS[22], terms.TERMS[23], *terms.TERMS[:22]):
        month=1 if term.kasi_id>22 else (term.kasi_id+3)//2
        day=5 if term.kasi_id%2 else 20
        a,b=erfa.cal2jd(year,month,day)
        # TT roots supplied independently; conversion itself must not be mocked.
        t=SimpleNamespace(whole=float(a+b),tt_fraction=0.25,tt=float(a+b+0.25),
                          utc_datetime=lambda y=year,m=month,d=day:datetime(y,m,d,6,tzinfo=UTC))
        times.append(t);indices.append(term.longitude//15)
    scale=SimpleNamespace(from_datetime=lambda dt:SimpleNamespace(tdb=2460000.0))
    kernel=SimpleNamespace(spk=SimpleNamespace(segments=[SimpleNamespace(target=x,start_jd=0.,end_jd=1e10) for x in (3,10,399)]),close=lambda:None)
    monkeypatch.setattr(skyfield.api,'Loader',lambda directory:SimpleNamespace(timescale=lambda builtin:scale))
    monkeypatch.setattr(skyfield.api,'load_file',lambda path:kernel)
    monkeypatch.setattr(almanac,'find_discrete',lambda *a,**k:(times,indices))
    monkeypatch.setattr(almanac_east_asia,'solar_terms',lambda eph:None)
    monkeypatch.setattr(terms,'verify_file',lambda *a:None)
    m=replace(manifest(),clock='TDB',precision='computed',coverage_start=date(1900,1,1),coverage_end=date(2100,1,1))
    return terms.generate_terms(year,tmp_path/'kernel',m)


def test_generator_uses_real_utc_drift_projection(tmp_path,monkeypatch):
    values=generated_year(1965,tmp_path,monkeypatch)
    assert len(values)==24
    for event in values:
        assert hasattr(event,'utc_projection'), 'event must carry the actual clock policy'
        assert event.utc_projection.status=='historical_utc_drift'
        assert event.instant_utc==event.utc_projection.instant_utc
        assert event.utc_projection.tt_day+event.utc_projection.tt_fraction==event.tt_jd


def test_generator_retains_tt_but_no_fake_pre_1960_utc(tmp_path,monkeypatch):
    values=generated_year(1950,tmp_path,monkeypatch)
    assert len(values)==24
    assert all(e.instant_utc is None and e.utc_projection.status=='utc_undefined_before_1960' for e in values)
    assert all(a.tt_jd<b.tt_jd for a,b in zip(values,values[1:]))


def test_audit_blocks_undefined_clock_without_counting_it_as_a_match(tmp_path,monkeypatch):
    from tests.test_kasi_reference import document_bytes,parse
    from sazu.term_audit import compare_term_range
    doc=parse(document_bytes(1950,1950),1950,1950)
    values=generated_year(1950,tmp_path,monkeypatch)
    result=compare_term_range(values,doc,1950,1950)
    assert result['status']=='blocked' and result['matched']==0
    assert result['expected']==24 and result['candidate_count']==24
    assert len(result['unresolved_clock_keys'])==24
    assert result['missing_candidate_keys']==[]
    assert result['invalid_annual_structure']==[]
    assert result['production_authorized'] is False


@pytest.mark.parametrize('change', [
    {'production_authorized':True}, {'policy_id':'invented'},
    {'instant_utc':None}, {'status':'historical_utc_drift'},
    {'utc_text':'wrong'}, {'tt_fraction':float('nan')}
])
def test_projection_cannot_be_forged_by_dataclass_replacement(change):
    from dataclasses import replace
    result=module().project_tt(2457754.5,69.184/86400)
    with pytest.raises(SazuError): replace(result,**change)


def test_source_event_rejects_inconsistent_clock_projection(tmp_path,monkeypatch):
    from dataclasses import replace
    event=generated_year(1965,tmp_path,monkeypatch)[0]
    with pytest.raises(SazuError): replace(event,instant_utc=datetime(1965,1,1,tzinfo=UTC))


def test_reference_check_keeps_mismatch_after_clock_fix():
    from datetime import timedelta
    from dataclasses import replace
    from tests.test_term_audit import comparison_inputs, audit
    doc,values=comparison_inputs()
    values[0]=replace(values[0],instant_utc=values[0].instant_utc-timedelta(seconds=30.5))
    result=audit(values,doc)
    assert result['status']=='failed' and len(result['mismatches'])==1
    assert result['comparison_policy']=='nearest-minute-half-up-v1'
