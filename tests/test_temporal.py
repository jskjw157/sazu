from datetime import UTC, date, datetime, time, timedelta
import pytest
from sazu.temporal import TimeInput, normalize_time
from sazu.tzif import load_zone, parse_tzif
from sazu.errors import SazuError

@pytest.mark.parametrize('ymd,offset', [((1953,1,1),9),((1955,1,1),8.5),((1962,1,1),9),
                                         ((1987,7,1),10),((1988,7,1),10),((1989,7,1),9)])
def test_historical_korean_offsets(ymd,offset):
    r=normalize_time(TimeInput(date(*ymd),'Asia/Seoul','instant',time(12)))
    assert r.intervals[0].start==datetime(*ymd,12,tzinfo=UTC)-timedelta(hours=offset)
    assert r.tzdata_version=='2026.2' and len(r.zone_sha256)==64

def test_fold_two_candidates_and_selection():
    day=date(2026,11,1)
    r=normalize_time(TimeInput(day,'America/New_York','instant',time(1,30)))
    assert [i.start.hour for i in r.intervals]==[5,6]
    assert 'AMBIGUOUS_LOCAL_TIME' in r.warnings
    for fold in (0,1):
        s=normalize_time(TimeInput(day,'America/New_York','instant',time(1,30),fold=fold))
        assert s.intervals==(r.intervals[fold],)

def test_gap_rejected():
    with pytest.raises(SazuError) as e: normalize_time(TimeInput(date(2026,3,8),'America/New_York','instant',time(2,30)))
    assert e.value.code=='NONEXISTENT_LOCAL_TIME'

@pytest.mark.parametrize('day,zone,hours', [
 (date(2026,3,8),'America/New_York',23), (date(2026,11,1),'America/New_York',25),
 (date(2026,4,5),'Australia/Lord_Howe',24.5), (date(2040,3,11),'America/New_York',23),
 (date(2026,1,1),'Asia/Seoul',24)])
def test_unknown_full_day(day,zone,hours):
    r=normalize_time(TimeInput(day,zone,'unknown'))
    assert sum((i.end-i.start).total_seconds() for i in r.intervals)==hours*3600
    assert all(not i.is_point for i in r.intervals)

def test_skipped_date():
    with pytest.raises(SazuError) as e: normalize_time(TimeInput(date(2011,12,30),'Pacific/Apia','unknown'))
    assert e.value.code=='NONEXISTENT_LOCAL_TIME'

@pytest.mark.parametrize('precision,startsecond', [('minute_bucket',0),('rounded_minute',30)])
def test_minute_precision(precision,startsecond):
    r=normalize_time(TimeInput(date(2026,1,2),'Asia/Seoul',precision,time(12)))
    i=r.intervals[0]
    assert i.start.second==startsecond and (i.end-i.start).total_seconds()==60
    assert i.start_inclusive and not i.end_inclusive

def test_disjoint_fold_interval():
    r=normalize_time(TimeInput(date(2026,11,1),'America/New_York','interval',time(1,10),datetime(2026,11,1,1,20)))
    assert len(r.intervals)==2
    assert all((i.end-i.start).total_seconds()==600 for i in r.intervals)

def test_partial_gap():
    r=normalize_time(TimeInput(date(2026,3,8),'America/New_York','interval',time(1,30),datetime(2026,3,8,3,30)))
    assert sum((i.end-i.start).total_seconds() for i in r.intervals)==3600
    assert 'PARTIAL_LOCAL_GAP' in r.warnings

@pytest.mark.parametrize('kwargs', [
 {'precision':[]},{'precision':'exact_minute'}, {'precision':'instant','local_time':None},
 {'precision':'unknown','local_time':time(12)}, {'precision':'minute_bucket','local_time':time(12,0,1)},
 {'precision':'instant','local_time':time(12),'fold':True},
 {'precision':'minute_bucket','local_time':time(12),'fold':0},
 {'precision':'interval','local_time':time(12),'end_local':datetime(2026,1,1,11)},
])
def test_bad_contract(kwargs):
    with pytest.raises(SazuError): TimeInput(date(2026,1,1),'Asia/Seoul',**kwargs)

@pytest.mark.parametrize('zone', ['../UTC','/UTC','Asia//Seoul','Asia/Seoul/','Unknown/City'])
def test_bad_zone(zone):
    with pytest.raises(SazuError): load_zone(zone)

@pytest.mark.parametrize('raw',[b'',b'TZif',b'X'*100,b'TZif2'+b'\x00'*100])
def test_corrupt_tzif(raw):
    with pytest.raises(SazuError): parse_tzif(raw)

def test_pinned_not_os(monkeypatch):
    import zoneinfo
    monkeypatch.setattr(zoneinfo,'TZPATH',('/nonexistent',))
    assert load_zone('Asia/Seoul').zone.key=='Asia/Seoul'
