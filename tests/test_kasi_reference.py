"""Synthetic format fixtures only: these are NOT official astronomical values."""
from dataclasses import replace
from datetime import UTC, date, datetime
import hashlib

import pytest

from sazu.contracts import SourceManifest
from sazu.errors import SazuError

URL = 'https://astro.kasi.re.kr/kor/almanac/solarTerms/download'
NAMES = '입춘 우수 경칩 춘분 청명 곡우 입하 소만 망종 하지 소서 대서 입추 처서 백로 추분 한로 상강 입동 소설 대설 동지 소한 대한'.split()


def document_bytes(first=1993, last=1993, encoding='utf-8', rollover=False):
    header = [f'[ {first}년-{last}년 24기 입기 시각 ]', '-'*40,
              '반올림 결과 날짜가 바뀌는 경우 날짜 변동 없이 24시 0분으로 표기됩니다.',
              '시험용 합성 자료이며 천문 계산값이 아닙니다.',
              '아래 모든 시각 데이터는 현재(2026년 9월 1일) KST(=UTC+9h) 기준이며, 과거 표준자오선 변경이나 써머타임은 고려하지 않음.',
              '-'*40, '', '<24기 구분>']
    for start in range(0, 24, 6):
        header.append(', '.join(f'{i+1}: {NAMES[i]}' for i in range(start, start+6)))
    header += ['', '구분\t년도\t월\t일\t시\t분', '-'*30]
    rows = []
    for year in range(first, last+1):
        for n in [23, 24, *range(1, 23)]:
            month = 1 if n >= 23 else (n+3)//2
            day = 5 if n % 2 else 20
            hour = 24 if rollover and n == 24 else 0
            rows.append(f'{n:2}, {year}, {month:2}, {day:2}, {hour:2},  0')
    return ('\n'.join(header+rows)+'\n').encode(encoding)


def reference_manifest(raw, first=1993, last=1993, **overrides):
    values = dict(source_id='synthetic-kasi-fixture', provider='Synthetic test fixture',
        version='2026-09-01', url=URL, sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw), acquired_at=datetime(2026,10,21,tzinfo=UTC),
        coverage_start=date(first,1,1), coverage_end=date(last,12,31),
        clock='fixed-UTC+9', precision='rounded_minute', rights_status='unreviewed',
        rights_url='https://www.kasi.re.kr/kor/pageView/134',
        lineage=('kasi-ephemeris-lineage-unestablished',), parser_version='kasi-txt-v1')
    values.update(overrides)
    return SourceManifest(**values)


def parse(raw, first=1993, last=1993, **overrides):
    from sazu.kasi_reference import parse_kasi_document
    return parse_kasi_document(raw, reference_manifest(raw, first, last, **overrides))


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'cp949'])
def test_complete_document_and_encoding(encoding):
    doc = parse(document_bytes(encoding=encoding))
    assert doc.start_year == doc.end_year == 1993
    assert len(doc.rows) == 24
    assert doc.header_date == date(2026,9,1)
    assert [r.kasi_id for r in doc.rows] == [23,24,*range(1,23)]
    assert doc.encoding in ('utf-8-sig', 'cp949')
    assert doc.manifest.rights_status == 'unreviewed'


def test_full_source_does_not_expand_runtime_range():
    from sazu.kasi_reference import reference_events
    doc = parse(document_bytes(1920,2100),1920,2100)
    assert len(doc.rows) == 4344
    assert len(reference_events(doc,1920,2050)) == 3144
    with pytest.raises(SazuError) as error:
        reference_events(doc,2099,2100)
    assert error.value.code == 'UNSUPPORTED_RANGE'


def test_rollover_preserves_original_and_fixed_clock():
    from sazu.kasi_reference import reference_events
    doc = parse(document_bytes(1950,1950,rollover=True),1950,1950)
    r = reference_events(doc,1950,1950)[1]
    assert r.instant_utc == datetime(1950,1,20,15,tzinfo=UTC)
    assert r.original_time == '1950-01-20T24:00'
    assert r.source_sha256 == doc.manifest.sha256
    assert r.precision == 'rounded_minute'


@pytest.mark.parametrize('mutate', [
    lambda b:b.replace(b'23, 1993', b'25, 1993',1),
    lambda b:b.replace(b'23, 1993,  1,  5,  0,  0',b'23, 1993,  2, 30,  0,  0'),
    lambda b:b.replace(b'23, 1993,  1,  5,  0,  0',b'23, 1993,  1,  5, 24,  1'),
    lambda b:b.replace(b'23, 1993,  1,  5,  0,  0',b'23, 1993,  1,  5,  0, 60'),
    lambda b:b.replace(b'23, 1993,  1,  5,  0,  0',b'23, 1993,  1,  5, -1,  0'),
    lambda b:b.replace(b'23, 1993',b'23.0, 1993',1),
    lambda b:b.replace(b'23, 1993',b'True, 1993',1),
    lambda b:b.replace(b'23, 1993',b'23, 1992',1),
    lambda b:b.replace(b'23, 1993',b'23, 1994',1),
    lambda b:b+b'garbage footer\n',
    lambda b:b+b'23, 1993, 1, 5, 0, 0\n',
    lambda b:b.replace(b'23, 1993,  1,  5,  0,  0\n',b''),
    lambda b:b.replace(b' 1, 1993,  2,  5,  0,  0',b' 1, 1993,  1,  6,  0,  0'),
    lambda b:b.replace(b' 1, 1993,  2,  5,  0,  0',b' 1, 1993,  2,  5,  0,  0, 99'),
])
def test_invalid_data_rejected_even_when_checksum_matches(mutate):
    with pytest.raises(SazuError): parse(mutate(document_bytes()))


def test_duplicate_replacing_missing_row_rejected():
    b=document_bytes(); rows=b.splitlines()
    rows[-1]=rows[-2]
    with pytest.raises(SazuError): parse(b'\n'.join(rows))


def test_original_chronological_order_required():
    rows=document_bytes().splitlines();rows[-1],rows[-2]=rows[-2],rows[-1]
    with pytest.raises(SazuError): parse(b'\n'.join(rows))


@pytest.mark.parametrize('old,new', [
    ('KST(=UTC+9h)', 'KST(=UTC+8h)'),
    ('반올림', '버림'),
    ('과거 표준자오선 변경이나 써머타임은 고려하지 않음.', '역사적 시각 적용'),
    ('1: 입춘', '1: 경칩'),
    ('24: 대한', '24: 소한'),
    ('구분\t년도\t월\t일\t시\t분', '년도\t구분\t월\t일\t시\t분'),
    ('2026년 9월 1일', '2026년 2월 30일'),
    ('[ 1993년-1993년 24기 입기 시각 ]', '[ 1993년-1994년 24기 입기 시각 ]'),
])
def test_header_semantics_not_inferred(old,new):
    raw=document_bytes().decode().replace(old,new).encode()
    with pytest.raises(SazuError): parse(raw)


def test_corruption_outside_requested_window_still_rejected():
    raw=document_bytes(1993,1994).replace(b'22, 1994, 12, 20,  0,  0\n',b'')
    with pytest.raises(SazuError): parse(raw,1993,1994)


@pytest.mark.parametrize('changes', [dict(sha256='b'*64),dict(size_bytes=1),
    dict(clock='Asia/Seoul'),dict(precision='instant'),dict(version='2026-09-02'),
    dict(coverage_end=date(1993,6,30)),dict(url='https://example.org/not-official')])
def test_source_assertions_are_enforced(changes):
    with pytest.raises(SazuError): parse(document_bytes(),**changes)


def test_unknown_rounding_not_promoted():
    with pytest.raises(SazuError): parse(document_bytes(),precision='unknown')


@pytest.mark.parametrize('raw',[b'',b'\x00',b'\xff\xff',b'<html>denied</html>',b'x'*(1048576+1)], ids=['empty','nul','binary','html','oversize'])
def test_empty_binary_html_and_excessive_bytes(raw):
    with pytest.raises(SazuError): parse(raw)


def test_line_and_header_limits():
    raw=document_bytes().replace(b'\n',b'\n'+b' '*4097+b'\n',1)
    with pytest.raises(SazuError): parse(raw)


def test_crlf_supported():
    doc=parse(document_bytes().replace(b'\n',b'\r\n'))
    assert len(doc.rows)==24


def test_source_manifest_not_rewritten_by_parser():
    from sazu.kasi_reference import parse_kasi_document
    raw=document_bytes(); m=reference_manifest(raw)
    doc=parse_kasi_document(raw,m)
    assert doc.manifest is m
    assert replace(m, rights_status='restricted').rights_status=='restricted'
