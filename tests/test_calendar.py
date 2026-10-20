from concurrent.futures import ThreadPoolExecutor
from datetime import date
import pytest
from sazu.calendar import CalendarInput, CalendarDate, convert_calendar, library_identity
from sazu.errors import SazuError

@pytest.mark.parametrize('args', [
 ('gregorian',2026,2,30), ('gregorian',True,1,1), ('gregorian',2026.0,1,1),
 ('gregorian',2026,'1',1), ('gregorian',2026,1,1,'regular'),
 ('korean_lunar',2026,1,1), ('korean_lunar',2026,1,31,'regular'),
 ('korean_lunar',2026,1,1,False), ([],2026,1,1), ('chinese_lunar',2026,1,1),
 ('gregorian',2026,13,1), ('gregorian',2026,1,0),
])
def test_invalid_inputs(args):
    with pytest.raises(SazuError): CalendarInput(*args)

@pytest.mark.parametrize('ymd,lunar', [
 ((2017,6,24),(2017,5,1,True)), ((2017,7,23),(2017,6,1,False)),
 ((2023,3,22),(2023,2,1,True)), ((2026,2,17),(2026,1,1,False))])
def test_known_library_regressions(ymd,lunar):
    r=convert_calendar(CalendarInput('gregorian',*ymd)); c=r.candidates[0]
    assert (c.lunar_year,c.lunar_month,c.lunar_day,c.is_leap)==lunar
    back=convert_calendar(CalendarInput('korean_lunar',*lunar[:3], 'leap' if lunar[3] else 'regular'))
    assert back.candidates[0].solar==date(*ymd)
    assert r.library_version and len(r.library_sha256)==64

def test_unknown_leap_preserved():
    r=convert_calendar(CalendarInput('korean_lunar',2017,5,1,'unknown'))
    assert [c.solar for c in r.candidates]==[date(2017,5,26),date(2017,6,24)]
    assert r.request.leap=='unknown'

def test_nonexistent_leap_rejected():
    convert_calendar(CalendarInput('gregorian',2026,2,17))
    with pytest.raises(SazuError): convert_calendar(CalendarInput('korean_lunar',2026,1,1,'leap'))
    assert convert_calendar(CalendarInput('gregorian',2017,6,24)).candidates[0].is_leap

@pytest.mark.parametrize('ymd', [(1919,12,31),(2051,1,1)])
def test_range(ymd):
    with pytest.raises(SazuError) as e: convert_calendar(CalendarInput('gregorian',*ymd))
    assert e.value.code=='UNSUPPORTED_RANGE'

@pytest.mark.parametrize('ymd', [(1920,1,1),(2050,12,31)])
def test_target_edges(ymd):
    assert convert_calendar(CalendarInput('gregorian',*ymd)).candidates[0].solar==date(*ymd)

def test_parallel_no_state_leakage():
    inputs=[CalendarInput('gregorian',2026,month,1) for month in range(1,13)]*2
    expected=[convert_calendar(x) for x in inputs]
    with ThreadPoolExecutor(max_workers=4) as pool: assert list(pool.map(convert_calendar,inputs))==expected

@pytest.mark.parametrize('kwargs', [{'lunar_year':True},{'lunar_month':0},{'lunar_day':31},{'is_leap':1}])
def test_result_contract(kwargs):
    base=dict(solar=date(2026,1,1),lunar_year=2025,lunar_month=11,lunar_day=13,is_leap=False)
    with pytest.raises(SazuError): CalendarDate(**(base|kwargs))

def test_identity_stable():
    assert library_identity()==library_identity()
