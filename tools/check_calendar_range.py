"""Finite-range round trips. This is not independent KASI validation."""
import argparse
from datetime import date,timedelta
import json
import time
from sazu.calendar import CalendarInput,convert_calendar,library_identity


def check(start: date,end: date) -> dict:
    current=start;count=0;failures=[];began=time.perf_counter()
    while current<=end:
        c=convert_calendar(CalendarInput('gregorian',current.year,current.month,current.day)).candidates[0]
        back=convert_calendar(CalendarInput('korean_lunar',c.lunar_year,c.lunar_month,c.lunar_day,
                                           'leap' if c.is_leap else 'regular')).candidates[0]
        if back!=c: failures.append(current.isoformat())
        count+=1;current+=timedelta(days=1)
    ver,sha=library_identity()
    return {'start':start.isoformat(),'end':end.isoformat(),'checked_dates':count,'failures':failures,
            'status':'failed' if failures else 'passed','elapsed_seconds':round(time.perf_counter()-began,3),
            'evidence_level':'self_consistency_not_independent_official_validation',
            'library_version':ver,'library_sha256':sha}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--start',default='1920-01-01');p.add_argument('--end',default='2050-12-31')
    args=p.parse_args();start=date.fromisoformat(args.start);end=date.fromisoformat(args.end)
    if not date(1920,1,1)<=start<=end<=date(2050,12,31):p.error('outside declared target range')
    result=check(start,end);print(json.dumps(result,sort_keys=True));raise SystemExit(1 if result['failures'] else 0)
