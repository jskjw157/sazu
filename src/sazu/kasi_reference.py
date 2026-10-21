"""Strict complete KASI TXT parser. Parsing is not a reuse or production permit.

Format was inspected on 2026-10-21. Header changes require explicit review;
corrupt rows are never skipped. Full source coverage is kept separate from the
narrower computational range accepted by the existing runtime adapter.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import re

from .contracts import SourceManifest, strict_int
from .errors import SazuError, require
from .solar_terms import TERMS, FIXED_KST, normalize_reference_record, validate_annual_terms

KASI_URL = 'https://astro.kasi.re.kr/kor/almanac/solarTerms/download'
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_DOCUMENT_LINES = 10000
PARSER_VERSION = 'kasi-txt-v1'
_ORDER = (23, 24, *range(1, 23))
_TITLE = re.compile(r'\[\s*([0-9]{4})년-([0-9]{4})년\s+24기 입기 시각\s*\]')
_ROW = re.compile(r'\s*([0-9]{1,2})\s*,\s*([0-9]{4})\s*,\s*([0-9]{1,2})\s*,'
                  r'\s*([0-9]{1,2})\s*,\s*([0-9]{1,2})\s*,\s*([0-9]{1,2})\s*')


@dataclass(frozen=True)
class KasiRow:
    kasi_id: int
    year: int
    month: int
    day: int
    hour: int
    minute: int
    source_line: int

    def fields(self) -> tuple[int, ...]:
        return (self.kasi_id, self.year, self.month, self.day, self.hour, self.minute)

    def local_datetime(self) -> datetime:
        return datetime(self.year, self.month, self.day, tzinfo=FIXED_KST) + timedelta(
            hours=self.hour, minutes=self.minute)


@dataclass(frozen=True)
class KasiDocument:
    manifest: SourceManifest
    encoding: str
    header_date: date
    start_year: int
    end_year: int
    rows: tuple[KasiRow, ...]
    header_sha256: str


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            return raw.decode(encoding), encoding
        except UnicodeError:
            continue
    raise SazuError('DATA_INTEGRITY_FAILED')


def parse_kasi_document(raw: bytes, manifest: SourceManifest) -> KasiDocument:
    """Check exact source bytes, documented semantics and every declared row."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_DOCUMENT_BYTES)
    require(type(manifest) is SourceManifest)
    require(len(raw) == manifest.size_bytes
            and hashlib.sha256(raw).hexdigest() == manifest.sha256, 'DATA_INTEGRITY_FAILED')
    require(manifest.url == KASI_URL and manifest.clock == 'fixed-UTC+9'
            and manifest.precision == 'rounded_minute'
            and manifest.parser_version == PARSER_VERSION, 'SOURCE_CONFLICT')
    text, encoding = _decode(raw)
    require(not any(ord(c) < 32 and c not in '\r\n\t' for c in text), 'DATA_INTEGRITY_FAILED')
    lines = text.splitlines()
    require(1 <= len(lines) <= MAX_DOCUMENT_LINES
            and all(len(line) <= 4096 for line in lines), 'DATA_INTEGRITY_FAILED')
    title = _TITLE.fullmatch(lines[0].strip())
    require(title is not None, 'DATA_INTEGRITY_FAILED')
    first, last = map(int, title.groups())
    require(1900 <= first <= last <= 2200, 'UNSUPPORTED_RANGE')
    require(manifest.coverage_start == date(first, 1, 1)
            and manifest.coverage_end == date(last, 12, 31), 'SOURCE_CONFLICT')
    columns = [i for i, line in enumerate(lines[:64])
               if line.split() == ['구분', '년도', '월', '일', '시', '분']]
    require(len(columns) == 1, 'DATA_INTEGRITY_FAILED')
    column = columns[0]
    header = '\n'.join(lines[:column])
    stamp = re.findall(r'현재\(([0-9]{4})년\s*([0-9]{1,2})월\s*([0-9]{1,2})일\)'
                       r'\s*KST\(=UTC\+9h\) 기준', header)
    require(len(stamp) == 1 and '반올림' in header and '24시 0분' in header
            and '과거 표준자오선 변경이나 써머타임은 고려하지 않음.' in header,
            'DATA_INTEGRITY_FAILED')
    try:
        header_date = date(*map(int, stamp[0]))
    except ValueError:
        raise SazuError('DATA_INTEGRITY_FAILED') from None
    require(manifest.version == header_date.isoformat(), 'SOURCE_CONFLICT')
    mappings = re.findall(r'(?<![0-9])([0-9]{1,2}):\s*([가-힣]+)', header)
    require(mappings == [(str(t.kasi_id), t.name) for t in TERMS], 'DATA_INTEGRITY_FAILED')
    require(column+1 < len(lines) and re.fullmatch(r'-{5,}', lines[column+1].strip()),
            'DATA_INTEGRITY_FAILED')
    rows = []
    for number, line in enumerate(lines[column+2:], start=column+3):
        if not line.strip():
            continue
        match = _ROW.fullmatch(line)
        require(match is not None, 'DATA_INTEGRITY_FAILED')
        fields = tuple(map(int, match.groups()))
        n, year, month, day, hour, minute = fields
        require(1 <= n <= 24 and first <= year <= last and 0 <= hour <= 24
                and 0 <= minute <= 59 and (hour != 24 or minute == 0),
                'DATA_INTEGRITY_FAILED')
        require(month == (1 if n >= 23 else (n+3)//2), 'DATA_INTEGRITY_FAILED')
        row = KasiRow(*fields, number)
        try:
            require(row.local_datetime().year == year, 'DATA_INTEGRITY_FAILED')
        except ValueError:
            raise SazuError('DATA_INTEGRITY_FAILED') from None
        rows.append(row)
    # Exact sequence detects missing years, duplicates and reordering, including
    # rows outside the later selected numerical-comparison interval.
    expected = [(year, n) for year in range(first, last+1) for n in _ORDER]
    require([(r.year, r.kasi_id) for r in rows] == expected, 'DATA_INTEGRITY_FAILED')
    require(all(a.local_datetime() < b.local_datetime() for a, b in zip(rows, rows[1:])),
            'DATA_INTEGRITY_FAILED')
    return KasiDocument(manifest, encoding, header_date, first, last, tuple(rows),
                        hashlib.sha256(header.encode('utf-8')).hexdigest())


def reference_events(document: KasiDocument, start_year: int, end_year: int):
    """Normalize only the existing computational range; not all source years."""
    require(type(document) is KasiDocument)
    require(strict_int(start_year, 1919, 2051) and strict_int(end_year, 1919, 2051)
            and start_year <= end_year, 'UNSUPPORTED_RANGE')
    require(document.start_year <= start_year <= end_year <= document.end_year,
            'UNSUPPORTED_RANGE')
    result = []
    for year in range(start_year, end_year+1):
        records = [normalize_reference_record(row.fields(), document.manifest)
                   for row in document.rows if row.year == year]
        result.extend(validate_annual_terms(records, year))
    return tuple(result)
