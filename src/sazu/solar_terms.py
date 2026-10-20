"""Explicit term mapping and offline ephemeris adapter; not a saju rule engine."""
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
import hashlib
from importlib import resources
from importlib.metadata import version
import math
from pathlib import Path

from .contracts import SourceManifest, strict_int, utc_datetime, valid_hash, valid_id
from .errors import SazuError, require
from .serde import digest
from .sources import verify_file

FIXED_KST = timezone(timedelta(hours=9))
_NAMES = ('입춘 우수 경칩 춘분 청명 곡우 입하 소만 망종 하지 소서 대서 '
          '입추 처서 백로 추분 한로 상강 입동 소설 대설 동지 소한 대한').split()


@dataclass(frozen=True)
class Term:
    kasi_id: int
    name: str
    longitude: int
    is_month_boundary: bool


TERMS = tuple(Term(i+1, name, (315+15*i) % 360, i % 2 == 0)
              for i, name in enumerate(_NAMES))


@dataclass(frozen=True)
class SolarTermEvent:
    event_year: int
    kasi_id: int
    name: str
    longitude: int
    instant_utc: datetime
    original_time: str | None
    precision: str
    lower_utc: datetime | None
    upper_utc: datetime | None
    source_id: str
    source_sha256: str
    tt_jd: float | None = None
    model_id: str | None = None
    numerical_tolerance_days: float | None = None
    physical_uncertainty: str = 'unknown'

    def __post_init__(self):
        require(strict_int(self.event_year, 1919, 2051) and strict_int(self.kasi_id, 1, 24))
        term = TERMS[self.kasi_id-1]
        require(self.name == term.name and type(self.longitude) is int
                and self.longitude == term.longitude)
        require(utc_datetime(self.instant_utc) and valid_hash(self.source_sha256)
                and valid_id(self.source_id))
        require(self.instant_utc.astimezone(FIXED_KST).year == self.event_year)
        require(type(self.precision) is str and self.precision in {'computed', 'rounded_minute', 'unknown'})
        if self.precision == 'rounded_minute':
            require(self.lower_utc == self.instant_utc-timedelta(seconds=30)
                    and self.upper_utc == self.instant_utc+timedelta(seconds=30))
        else:
            require(self.lower_utc is None and self.upper_utc is None)
        if self.precision == 'computed':
            require(type(self.tt_jd) is float and math.isfinite(self.tt_jd)
                    and valid_hash(self.model_id)
                    and type(self.numerical_tolerance_days) is float
                    and 0 < self.numerical_tolerance_days <= 1e-6)
        else:
            require(self.tt_jd is None and self.model_id is None)
        require(self.physical_uncertainty == 'unknown')


def normalize_reference_record(record, manifest: SourceManifest) -> SolarTermEvent:
    """Normalize a six-field record (term, year, month, day, hour, minute).

    This is deliberately NOT a parser for the complete upstream TXT document.
    `rounded_minute` uses a declared half-up cell [display-30s, display+30s).
    Unknown rounding remains unknown. A manifest never grants reuse rights.
    """
    require(type(manifest) is SourceManifest and manifest.clock == 'fixed-UTC+9'
            and manifest.precision in {'rounded_minute', 'unknown'})
    require(type(record) in (tuple, list) and len(record) == 6)
    identifier, year, month, day, hour, minute = record
    require(strict_int(identifier, 1, 24) and strict_int(year, 1919, 2051)
            and strict_int(month, 1, 12) and strict_int(day, 1, 31)
            and strict_int(hour, 0, 24) and strict_int(minute, 0, 59))
    require(hour != 24 or minute == 0)
    try:
        raw_date = date(year, month, day)
        require(manifest.coverage_start <= raw_date <= manifest.coverage_end, 'UNSUPPORTED_RANGE')
        value = datetime(year, month, day, tzinfo=FIXED_KST) + timedelta(hours=hour, minutes=minute)
    except SazuError:
        raise
    except ValueError:
        raise SazuError('INVALID_INPUT') from None
    instant = value.astimezone(UTC)
    delta = timedelta(seconds=30)
    bounded = manifest.precision == 'rounded_minute'
    term = TERMS[identifier-1]
    return SolarTermEvent(value.year, identifier, term.name, term.longitude, instant,
                          f'{raw_date.isoformat()}T{hour:02}:{minute:02}', manifest.precision,
                          instant-delta if bounded else None, instant+delta if bounded else None,
                          manifest.source_id, manifest.sha256)


def compare_reference(reference: SolarTermEvent, instant: datetime) -> str:
    require(type(reference) is SolarTermEvent and utc_datetime(instant))
    if reference.lower_utc is None:
        return 'unknown'
    return 'match' if reference.lower_utc <= instant < reference.upper_utc else 'mismatch'


def validate_annual_terms(events, year: int) -> tuple[SolarTermEvent, ...]:
    require(strict_int(year, 1919, 2051))
    events = tuple(events)
    require(len(events) == 24 and all(type(e) is SolarTermEvent for e in events),
            'DATA_INTEGRITY_FAILED')
    require(all(e.event_year == year for e in events) and
            {e.kasi_id for e in events} == set(range(1, 25)), 'DATA_INTEGRITY_FAILED')
    ordered = tuple(sorted(events, key=lambda e: e.instant_utc))
    require([e.kasi_id for e in ordered] == [23, 24, *range(1, 23)], 'DATA_INTEGRITY_FAILED')
    require(all(a.instant_utc < b.instant_utc for a, b in zip(ordered, ordered[1:])),
            'DATA_INTEGRITY_FAILED')
    require(len({(e.source_id, e.source_sha256, e.model_id) for e in ordered}) == 1,
            'SOURCE_CONFLICT')
    return ordered


def generate_terms(year: int, kernel_path: Path, manifest: SourceManifest) -> tuple[SolarTermEvent, ...]:
    """Compute with a verified LOCAL BSP. No runtime downloads are permitted."""
    require(strict_int(year, 1919, 2051))
    require(type(manifest) is SourceManifest and manifest.clock == 'TDB'
            and manifest.precision == 'computed')
    verify_file(kernel_path, manifest)
    try:
        from skyfield.api import Loader, load_file
        from skyfield import almanac, almanac_east_asia
    except ImportError:
        raise SazuError('SOURCE_NOT_AVAILABLE') from None
    require(manifest.coverage_start <= date(year, 1, 1)
            and date(year+1, 1, 1) <= manifest.coverage_end, 'UNSUPPORTED_RANGE')
    root = resources.files('skyfield.data')
    assets = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in root.iterdir() if p.name.endswith(('.npy', '.npz', '.data'))}
    require(bool(assets), 'SOURCE_NOT_AVAILABLE')
    model = digest({'skyfield': version('skyfield'), 'builtin_time_assets': assets,
                    'kernel': manifest.sha256, 'mapping': 'kasi-longitude-v1',
                    'epsilon_days': 1e-8})
    ts = Loader(str(Path(kernel_path).parent)).timescale(builtin=True)
    low = datetime(year, 1, 1, tzinfo=FIXED_KST).astimezone(UTC)
    high = datetime(year+1, 1, 1, tzinfo=FIXED_KST).astimezone(UTC)
    start, end = ts.from_datetime(low), ts.from_datetime(high)
    try:
        with load_file(str(kernel_path)) as eph:
            relevant = [s for s in eph.spk.segments if s.target in (3, 10, 399)]
            require({s.target for s in relevant} >= {3, 10, 399}, 'DATA_INTEGRITY_FAILED')
            require(all(s.start_jd <= float(start.tdb) and float(end.tdb) <= s.end_jd
                        for s in relevant), 'UNSUPPORTED_RANGE')
            times, indices = almanac.find_discrete(start, end, almanac_east_asia.solar_terms(eph),
                                                 epsilon=1e-8)
            events = []
            for t, index in zip(times, indices):
                instant = t.utc_datetime()
                if not low <= instant < high:
                    continue
                identifier = ((int(index)*15-315) % 360)//15+1
                term = TERMS[identifier-1]
                events.append(SolarTermEvent(year, identifier, term.name, term.longitude, instant,
                                             None, 'computed', None, None, manifest.source_id,
                                             manifest.sha256, float(t.tt), model, 1e-8))
            return validate_annual_terms(events, year)
    except SazuError:
        raise
    except (OSError, ValueError, KeyError):
        raise SazuError('DATA_INTEGRITY_FAILED') from None
