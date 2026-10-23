"""Versioned TT -> UTC projection; never extrapolate UTC before its introduction.

ERFA implements the SOFA/USNO pre-1972 frequency-drift expressions. Skyfield's
backward constant leap-offset extension is useful for reproduction but is not
historical UTC. UTC did not exist before 1960; an optional UT1 reconstruction
must remain a separately named quantity, not a UTC datetime.

The confirmation horizon is deliberately frozen to IERS Bulletin C 72. It is
not read from the host clock, nor automatically extended by a library update.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
import hashlib
from importlib.metadata import version
import math
from pathlib import Path
import warnings

from .contracts import utc_datetime
from .errors import SazuError, require
from .serde import digest

POLICY_ID = 'sofa-utc-v2'
CONFIRMED_BEFORE = datetime(2027, 1, 1, tzinfo=UTC)
CONFIRMATION_SOURCE = 'https://datacenter.iers.org/data/html/bulletinc-072.html'


@dataclass(frozen=True)
class UtcProjection:
    tt_day: float
    tt_fraction: float
    instant_utc: datetime | None
    utc_text: str | None
    status: str
    policy_id: str
    assumptions: tuple[str, ...]
    production_authorized: bool = False

    def __post_init__(self) -> None:
        require(type(self.tt_day) is float and math.isfinite(self.tt_day)
                and type(self.tt_fraction) is float and math.isfinite(self.tt_fraction)
                and 0 <= self.tt_fraction < 1)
        require(self.policy_id == POLICY_ID and self.production_authorized is False
                and type(self.assumptions) is tuple
                and all(type(a) is str for a in self.assumptions))
        statuses = {'historical_utc_drift', 'utc_leap_table', 'utc_future_assumption',
                    'utc_undefined_before_1960', 'utc_leap_second'}
        require(type(self.status) is str and self.status in statuses)
        if self.status == 'utc_undefined_before_1960':
            require(self.instant_utc is None and self.utc_text is None
                    and self.tt_day+self.tt_fraction < 2436934.501)
        elif self.status == 'utc_leap_second':
            require(self.instant_utc is None and type(self.utc_text) is str
                    and ':60.' in self.utc_text and self.utc_text.endswith('Z'))
        else:
            require(utc_datetime(self.instant_utc))
            expected_text = self.instant_utc.isoformat(timespec='microseconds').replace('+00:00','Z')
            require(self.utc_text == expected_text)
            y = self.instant_utc.year
            require((self.status == 'historical_utc_drift' and 1960 <= y < 1972)
                    or (self.status == 'utc_leap_table' and 1972 <= y < 2027)
                    or (self.status == 'utc_future_assumption' and y >= 2027))
            require((self.status == 'utc_future_assumption') ==
                    ('future_leap_seconds_not_predicted' in self.assumptions))


def _erfa():
    try:
        import erfa
        return erfa
    except ImportError:
        raise SazuError('SOURCE_NOT_AVAILABLE') from None


@lru_cache(maxsize=1)
def _binary_identity() -> dict:
    erfa = _erfa()
    try:
        return {'pyerfa': version('pyerfa'), 'erfa': erfa.version.erfa_version,
                'sofa': erfa.version.sofa_version,
                'erfa_binary_sha256': hashlib.sha256(Path(erfa.ufunc.__file__).read_bytes()).hexdigest()}
    except (OSError, AttributeError):
        raise SazuError('SOURCE_NOT_AVAILABLE') from None


def projection_identity() -> dict:
    """Fresh table fingerprint; mutable process-global ERFA tables are not trusted by name."""
    erfa = _erfa()
    return {**_binary_identity(), 'policy_id': POLICY_ID,
            'leap_table_sha256': digest(erfa.leap_seconds.get().tolist()),
            'confirmed_before_utc': '2027-01-01T00:00:00Z',
            'confirmation_source': CONFIRMATION_SOURCE,
            'before_1960': 'UTC_UNDEFINED', 'future': 'last_known_leap_table_assumption'}


def project_tt(tt_day: float, tt_fraction: float) -> UtcProjection:
    """Project a two-part TT Julian date, retaining leap seconds without datetime coercion.

    Two parts avoid losing sub-millisecond information by subtracting large JDs.
    Supported research interval is 1900--2100; this does not approve any dataset.
    """
    require(type(tt_day) in (float, int) and type(tt_fraction) in (float, int)
            and math.isfinite(tt_day) and math.isfinite(tt_fraction))
    require(0 <= tt_fraction < 1)
    day, fraction = float(tt_day), float(tt_fraction)
    require(2415020.5 <= day+fraction < 2488434.5, 'UNSUPPORTED_RANGE')
    erfa = _erfa()
    if day+fraction < 2436934.5:
        return UtcProjection(day, fraction, None, None, 'utc_undefined_before_1960',
                             POLICY_ID, ('historical_civil_clock_requires_separate_policy',))
    try:
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter('always', erfa.ErfaWarning)
            tai_day, tai_fraction = erfa.tttai(day, fraction)
            utc_day, utc_fraction = erfa.taiutc(tai_day, tai_fraction)
            year, month, date, hms = erfa.d2dtf('UTC', 6, utc_day, utc_fraction)
        y, m, d = int(year), int(month), int(date)
        if y < 1960:
            return UtcProjection(day, fraction, None, None, 'utc_undefined_before_1960',
                                 POLICY_ID, ('historical_civil_clock_requires_separate_policy',))
        h, minute, second, microsecond = (int(hms[k]) for k in ('h', 'm', 's', 'f'))
        future = (y, m, d) >= (2027, 1, 1)
        require(not notices or future, 'DATA_INTEGRITY_FAILED')
        require(all(issubclass(n.category, erfa.ErfaWarning) for n in notices),
                'DATA_INTEGRITY_FAILED')
        text = f'{y:04}-{m:02}-{d:02}T{h:02}:{minute:02}:{second:02}.{microsecond:06}Z'
        assumptions = ('future_leap_seconds_not_predicted',) if future else ()
        if second == 60:
            return UtcProjection(day, fraction, None, text, 'utc_leap_second', POLICY_ID,
                                 (*assumptions, 'datetime_cannot_represent_leap_second'))
        instant = datetime(y, m, d, h, minute, second, microsecond, tzinfo=UTC)
        status = ('utc_future_assumption' if future else
                  'historical_utc_drift' if y < 1972 else 'utc_leap_table')
        return UtcProjection(day, fraction, instant, text, status, POLICY_ID, assumptions)
    except SazuError:
        raise
    except (ValueError, OverflowError, TypeError):
        raise SazuError('DATA_INTEGRITY_FAILED') from None
