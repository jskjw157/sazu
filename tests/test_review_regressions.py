from datetime import date,time
import pytest
from sazu.temporal import TimeInput,normalize_time
from sazu.errors import SazuError

@pytest.mark.parametrize('zone',[[],{},None,True,''])
def test_invalid_zone_contract(zone):
    with pytest.raises(SazuError): TimeInput(date(2026,1,1),zone,'unknown')


def test_rounded_cell_cannot_extend_beyond_supported_local_dates():
    with pytest.raises(SazuError) as e:
        normalize_time(TimeInput(date(1920,1,1),'Asia/Seoul','rounded_minute',time(0)))
    assert e.value.code=='UNSUPPORTED_RANGE'
