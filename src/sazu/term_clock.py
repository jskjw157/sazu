"""Reviewed TT→UTC projection, separate from solar geometry and KASI matching.

Skyfield's pre-1972 constant TAI-UTC extrapolation is not historical UTC.
Use ERFA/SOFA's historical UTC drift/steps for 1961–1971. Earlier events
retain TT but deliberately have no asserted UTC. Never relabel UT1 as UTC.

Sources: IERS UTC-TAI.history; ERFA/SOFA taiutc/utctai/dat. Future leap
schedules and independent verification of the solar model remain separate.
"""
from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib.metadata import version
import math
from pathlib import Path

from .contracts import SourceManifest
from .errors import SazuError, require
from .serde import digest
from .solar_terms import SolarTermEvent, generate_terms

POLICY = 'erfa-historical-utc-v1'
UTC_RULES_REVIEWED_THROUGH = date(2026, 10, 22)
UTC_CHANGES_SHA256 = '5498bf6298f38b5f63c8f79ea786fc02ffb86df96d6bbf6cf8341e739e7c842f'
# IERS: at 1961-01-01 00:00 UTC, TAI-UTC = 1.422818 s; TT-TAI = 32.184 s.
HISTORICAL_UTC_START_JD = 2437300.5
HISTORICAL_UTC_START_TT_FRACTION = (1.422818 + 32.184) / 86400


@dataclass(frozen=True)
class UtcProjection:
    instant_utc: datetime | None
    status: str
    comparable_as_utc: bool
    clock_model_id: str
    reviewed_through: date
    tt_part1: float
    tt_part2: float
    erfa_status: int | None
    production_authorized: bool = False


def clock_identity(reviewed_through: date) -> dict:
    require(type(reviewed_through) is date)
    try:
        import erfa
    except ImportError:
        raise SazuError('SOURCE_NOT_AVAILABLE') from None
    # Snapshot actual active data, not just a package name. No automatic updates.
    changes = [[int(row['year']), int(row['month']), float(row['tai_utc'])]
               for row in erfa.leap_seconds.get()]
    require(version('pyerfa') == '2.0.1.5'
            and erfa.version.erfa_version == '2.0.1'
            and erfa.version.sofa_version == '20231011'
            and digest(changes) == UTC_CHANGES_SHA256, 'SOURCE_CONFLICT')
    return {'policy': POLICY, 'pyerfa': version('pyerfa'),
            'erfa': erfa.version.erfa_version, 'sofa': erfa.version.sofa_version,
            'utc_changes_sha256': digest(changes),
            'reviewed_through': reviewed_through,
            'source': 'https://hpiers.obspm.fr/iers/bul/bulc/UTC-TAI.history'}


def project_tt_to_utc(tt_part1: float, tt_part2: float = 0.0, *,
                      reviewed_through: date = UTC_RULES_REVIEWED_THROUGH) -> UtcProjection:
    """Preserve a split JD. A UTC-looking datetime is NOT automatic approval.

    The review horizon records the reviewed leap-second schedule, not the end
    of the ephemeris. Positive ERFA status is retained, never silently ignored.
    UTC leap seconds that datetime cannot encode are returned without a value.
    """
    require(all(type(v) in (int, float) and -1e9 < v < 1e9
                and math.isfinite(v) for v in (tt_part1, tt_part2)))
    require(type(reviewed_through) is date
            and date(1972, 1, 1) <= reviewed_through <= UTC_RULES_REVIEWED_THROUGH)
    require(date(1850, 1, 1).toordinal()+1721424.5 <= tt_part1+tt_part2
            < date(2151, 1, 1).toordinal()+1721424.5, 'UNSUPPORTED_RANGE')
    first, second = float(tt_part1), float(tt_part2)
    model = digest(clock_identity(reviewed_through))

    def result(instant, status, comparable, erfa_status=None):
        return UtcProjection(instant, status, comparable, model, reviewed_through,
                             first, second, erfa_status)

    if (first-HISTORICAL_UTC_START_JD)+second < HISTORICAL_UTC_START_TT_FRACTION:
        return result(None, 'historical_clock_unresolved', False)
    import erfa
    try:
        tai1, tai2, tai_status = erfa.ufunc.tttai(first, second)
        utc1, utc2, utc_status = erfa.ufunc.taiutc(tai1, tai2)
        year, month, day, hms, calendar_status = erfa.ufunc.d2dtf('UTC', 6, utc1, utc2)
        status = max(int(tai_status), int(utc_status), int(calendar_status))
        require(min(int(tai_status), int(utc_status), int(calendar_status)) >= 0,
                'DATA_INTEGRITY_FAILED')
        if int(hms['s']) >= 60:
            return result(None, 'leap_second_unrepresentable', False, status)
        instant = datetime(int(year), int(month), int(day), int(hms['h']), int(hms['m']),
                           int(hms['s']), int(hms['f']), tzinfo=UTC)
    except (ValueError, TypeError, OverflowError):
        raise SazuError('DATA_INTEGRITY_FAILED') from None
    # Reject a global table change during conversion as well. This module never updates it.
    require(digest(clock_identity(reviewed_through)) == model, 'SOURCE_CONFLICT')
    if instant.date() > reviewed_through:
        return result(instant, 'future_utc_assumption', False, status)
    if status:
        return result(instant, 'utc_conversion_warning', False, status)
    return result(instant, 'historical_utc' if instant.year < 1972 else 'modern_utc', True, status)


@dataclass(frozen=True)
class ReviewedSolarTerm:
    event_year: int
    kasi_id: int
    name: str
    longitude: int
    tt_jd: float
    clock: UtcProjection
    ephemeris_model_id: str
    model_id: str
    source_id: str
    source_sha256: str
    physical_uncertainty: str = 'unknown'
    production_authorized: bool = False


def project_computed_term(event: SolarTermEvent) -> ReviewedSolarTerm:
    require(type(event) is SolarTermEvent and event.precision == 'computed')
    clock = project_tt_to_utc(event.tt_jd)
    model = digest({'ephemeris_model_id': event.model_id, 'clock_model_id': clock.clock_model_id})
    return ReviewedSolarTerm(event.event_year, event.kasi_id, event.name, event.longitude,
                             event.tt_jd, clock, event.model_id, model,
                             event.source_id, event.source_sha256)


def generate_reviewed_terms(year: int, kernel_path: Path,
                            manifest: SourceManifest) -> tuple[ReviewedSolarTerm, ...]:
    """Reuse one geometry engine; discard its legacy UTC display for new outputs.

    All annual keys remain present, including unsupported clock projections.
    The legacy generator remains solely for reproducible historical audits.
    """
    return tuple(project_computed_term(e) for e in generate_terms(year, kernel_path, manifest))
