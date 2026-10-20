from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
import math
import pytest
from sazu.contracts import SourceManifest, UtcInterval
from sazu.serde import canonical_json, digest, parse_request
from sazu.errors import SazuError


def manifest(**changes):
    x = SourceManifest('synthetic', 'Fixture', 'v1', 'https://astro.kasi.re.kr/example',
                       'a'*64, 3, datetime(2026,1,1,tzinfo=UTC), date(1920,1,1), date(2050,12,31),
                       'fixed-UTC+9', 'rounded_minute', 'unreviewed',
                       'https://astro.kasi.re.kr/terms', ('synthetic',), 'v1')
    return replace(x, **changes)

@pytest.mark.parametrize('changes', [
 {'source_id':'../evil'}, {'sha256':'a'*63}, {'sha256':'Z'*64}, {'size_bytes':True},
 {'size_bytes':-1}, {'size_bytes':1.5}, {'acquired_at':datetime(2026,1,1)},
 {'coverage_end':date(1910,1,1)}, {'precision':'exact_microsecond'}, {'precision':[]},
 {'rights_status':'approved'}, {'lineage':()}, {'url':'http://example.com/a'},
 {'url':'https://example.com/?token=secret'}, {'url':'https://user:pass@example.com/a'},
 {'url':'https://example.com/a#key'}, {'url':'https://example.com:444/a'},
])
def test_invalid_manifest(changes):
    with pytest.raises(SazuError): manifest(**changes)

def test_canonical_identity():
    assert canonical_json({'b':2,'a':1}) == '{"a":1,"b":2}'
    assert digest({'a':1,'b':2}) == digest({'b':2,'a':1})
    assert '2026-01-01T00:00:00Z' in canonical_json(manifest())

@pytest.mark.parametrize('text', ['[]','null','{"x":1,"x":2}','{"x":NaN}',
                                    '{"x":Infinity}','{"x":1e999}','{"x":-1e999}','{bad}'])
def test_invalid_json(text):
    with pytest.raises(SazuError): parse_request(text)

@pytest.mark.parametrize('value', [{1:'a','1':'b'}, {'x':math.nan}, {'x':math.inf}, datetime(2026,1,1)])
def test_invalid_canonical(value):
    with pytest.raises(SazuError): canonical_json(value)

def test_interval_boundaries():
    a=datetime(2026,1,1,tzinfo=UTC)
    assert UtcInterval(a,a,True,True).is_point
    assert not UtcInterval(a,a+timedelta(seconds=1)).is_point
    with pytest.raises(SazuError): UtcInterval(a,a)
    with pytest.raises(SazuError): UtcInterval(a,a-timedelta(seconds=1))
    with pytest.raises(SazuError): UtcInterval(a.replace(tzinfo=None),a)

def test_unknown_error_sanitized():
    error=SazuError('secret-token')
    assert error.code=='INTERNAL_ERROR'
    assert 'secret' not in str(error)
