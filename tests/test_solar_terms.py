from datetime import UTC,date,datetime,timedelta
from dataclasses import replace
import pytest
from tests.test_core import manifest
from tests.test_sources import fixture
from sazu.errors import SazuError


def test_mapping():
    from sazu.solar_terms import TERMS
    assert len(TERMS)==24
    assert TERMS[0].name=='입춘' and TERMS[0].longitude==315
    assert TERMS[22].name=='소한' and TERMS[22].longitude==285
    assert len({x.longitude for x in TERMS})==24
    assert sum(x.is_month_boundary for x in TERMS)==12

def test_fixed_clock_and_rollover():
    from sazu.solar_terms import normalize_reference_record
    r=normalize_reference_record((24,1950,1,20,24,0),manifest())
    assert r.instant_utc==datetime(1950,1,20,15,tzinfo=UTC)
    assert r.original_time=='1950-01-20T24:00'
    assert r.lower_utc==r.instant_utc-timedelta(seconds=30)
    assert r.upper_utc==r.instant_utc+timedelta(seconds=30)

def test_rounding_boundary():
    from sazu.solar_terms import normalize_reference_record,compare_reference
    r=normalize_reference_record((1,2026,2,4,5,2),manifest())
    assert compare_reference(r,r.lower_utc)=='match'
    assert compare_reference(r,r.upper_utc)=='mismatch'
    assert compare_reference(r,r.instant_utc)=='match'

def test_unknown_precision_is_not_exact():
    from sazu.solar_terms import normalize_reference_record,compare_reference
    r=normalize_reference_record((1,2026,2,4,5,2),manifest(precision='unknown'))
    assert r.lower_utc is None and r.upper_utc is None
    assert compare_reference(r,r.instant_utc)=='unknown'

@pytest.mark.parametrize('row',[(0,2026,1,1,0,0),(25,2026,1,1,0,0),(True,2026,1,1,0,0),
 (1,2026,2,30,0,0),(1,2026,2,4,24,1),(1,2026,2,4,25,0),(1,2026,2,4,1,60),(1,2026,2,4,1)])
def test_bad_records(row):
    from sazu.solar_terms import normalize_reference_record
    with pytest.raises(SazuError): normalize_reference_record(row,manifest())

def test_wrong_clock_and_precision():
    from sazu.solar_terms import normalize_reference_record
    for m in [manifest(clock='Asia/Seoul'),manifest(precision='computed')]:
        with pytest.raises(SazuError): normalize_reference_record((1,2026,2,4,5,2),m)

def test_annual_missing_or_duplicate():
    from sazu.solar_terms import normalize_reference_record,validate_annual_terms
    event=normalize_reference_record((1,2026,2,4,5,2),manifest())
    for events in [[],[event],[event]*24]:
        with pytest.raises(SazuError): validate_annual_terms(events,2026)

def test_generation_requires_local_source(tmp_path):
    from sazu.solar_terms import generate_terms
    with pytest.raises(SazuError) as e: generate_terms(2026,tmp_path/'absent',fixture())
    assert e.value.code in ('SOURCE_NOT_AVAILABLE','INVALID_INPUT')

def synthetic_year(year=2026):
    from sazu.solar_terms import normalize_reference_record
    records=[(23,year,1,5,0,0),(24,year,1,20,0,0)]
    records += [(identifier,year,(identifier+3)//2,5 if identifier%2 else 20,0,0) for identifier in range(1,23)]
    return [normalize_reference_record(r,manifest()) for r in records]


def test_complete_synthetic_year_validation():
    from sazu.solar_terms import validate_annual_terms
    values=synthetic_year()
    assert validate_annual_terms(list(reversed(values)),2026)==tuple(values)


def test_annual_mixed_source_rejected():
    from sazu.solar_terms import validate_annual_terms
    values=synthetic_year();values[0]=replace(values[0],source_sha256='b'*64)
    with pytest.raises(SazuError) as e: validate_annual_terms(values,2026)
    assert e.value.code=='SOURCE_CONFLICT'


def test_generation_missing_checked_before_import(tmp_path):
    from sazu.solar_terms import generate_terms
    m=manifest(clock='TDB',precision='computed')
    with pytest.raises(SazuError) as e: generate_terms(2026,tmp_path/'absent',m)
    assert e.value.code=='SOURCE_NOT_AVAILABLE'


def test_computed_event_requires_model_identity():
    from sazu.solar_terms import SolarTermEvent
    with pytest.raises(SazuError):
        SolarTermEvent(2026,1,'입춘',315,datetime(2026,2,3,20,2,tzinfo=UTC),None,
                       'computed',None,None,'synthetic','a'*64)

def test_outside_source_coverage_keeps_error_code():
    from sazu.solar_terms import normalize_reference_record
    with pytest.raises(SazuError) as e:
        normalize_reference_record((1,2026,2,4,5,2),manifest(coverage_end=date(2025,12,31)))
    assert e.value.code=='UNSUPPORTED_RANGE'


def test_event_source_identity_is_strict():
    from sazu.solar_terms import normalize_reference_record
    event=normalize_reference_record((1,2026,2,4,5,2),manifest())
    with pytest.raises(SazuError): replace(event,source_id='../forged')


def test_kernel_is_closed_when_validation_fails_without_context_protocol(tmp_path, monkeypatch):
    import sys
    from types import ModuleType, SimpleNamespace
    import sazu.solar_terms as module

    class Kernel:
        closed = False
        spk = SimpleNamespace(segments=[])

        def close(self):
            self.closed = True

    kernel = Kernel()
    fake = ModuleType('skyfield')
    api = ModuleType('skyfield.api')
    scale = SimpleNamespace(from_datetime=lambda value: SimpleNamespace(tdb=2460000.0))
    api.Loader = lambda directory: SimpleNamespace(timescale=lambda builtin: scale)
    api.load_file = lambda path: kernel
    fake.api = api
    fake.almanac = SimpleNamespace()
    fake.almanac_east_asia = SimpleNamespace()
    monkeypatch.setitem(sys.modules, 'skyfield', fake)
    monkeypatch.setitem(sys.modules, 'skyfield.api', api)
    (tmp_path/'fixture.npz').write_bytes(b'time-model')
    monkeypatch.setattr(module.resources, 'files', lambda package: tmp_path)
    monkeypatch.setattr(module, 'version', lambda package: 'fixture-version')
    path = tmp_path/'kernel.bsp'
    path.write_bytes(b'abc')
    m = replace(fixture(), clock='TDB', precision='computed')
    with pytest.raises(SazuError) as error:
        module.generate_terms(2026, path, m)
    assert error.value.code == 'DATA_INTEGRITY_FAILED'
    assert kernel.closed
