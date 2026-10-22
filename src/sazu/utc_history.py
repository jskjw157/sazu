"""1960--1971 UTC conversion using the SOFA-derived ERFA drift model.

Skyfield's leap-second projection is deliberately not used for this period.
There is no historical UTC before 1960; this helper rejects that interval.
TT is supplied as a two-part Julian date to preserve sub-second precision.
"""
from datetime import UTC, datetime
import hashlib
from importlib.metadata import version
import math
from pathlib import Path
import warnings

from .errors import SazuError, require

POLICY = 'utc-history-erfa-1960-1971-v1'
_START_JD = 2436934.5
_START_TT_SECONDS = 32.184 + 0.943482
_END_JD = 2441317.5
_END_TT_SECONDS = 32.184 + 10.0


def _split(jd1: float, jd2: float) -> tuple[float, float]:
    require(type(jd1) in (float, int) and type(jd2) in (float, int))
    require(math.isfinite(jd1) and math.isfinite(jd2)
            and 2400000 <= jd1 <= 2500000 and abs(jd2) <= 100000)
    return float(jd1), float(jd2)


def historical_utc_from_tt(jd1: float, jd2: float) -> datetime:
    """Return UTC only in [1960-01-01, 1972-01-01); never guess a clock."""
    jd1, jd2 = _split(jd1, jd2)
    since_start = ((jd1-_START_JD) + jd2)*86400
    since_end = ((jd1-_END_JD) + jd2)*86400
    require(since_start >= _START_TT_SECONDS-1e-9
            and since_end < _END_TT_SECONDS, 'UNSUPPORTED_RANGE')
    try:
        import erfa
    except ImportError:
        raise SazuError('SOURCE_NOT_AVAILABLE') from None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', erfa.ErfaWarning)
            tai1, tai2 = erfa.tttai(jd1, jd2)
            utc1, utc2 = erfa.taiutc(tai1, tai2)
            year, month, day, fields = erfa.d2dtf('UTC', 6, utc1, utc2)
        # datetime cannot encode a second numbered 60. Never roll it silently.
        require(int(fields['s']) < 60, 'UNSUPPORTED_RANGE')
        return datetime(int(year), int(month), int(day), int(fields['h']),
                        int(fields['m']), int(fields['s']), int(fields['f']), tzinfo=UTC)
    except SazuError:
        raise
    except (erfa.ErfaWarning, erfa.ErfaError, ValueError, OverflowError):
        raise SazuError('DATA_INTEGRITY_FAILED') from None


def erfa_identity() -> dict:
    """Pin actual compiled ERFA bytes and the loaded UTC table, not just a name."""
    try:
        import erfa
        from erfa import ufunc
        return {'pyerfa': version('pyerfa'), 'erfa': erfa.version.erfa_version,
                'sofa': erfa.version.sofa_version,
                'compiled_sha256': hashlib.sha256(Path(ufunc.__file__).read_bytes()).hexdigest(),
                'utc_table_sha256': hashlib.sha256(erfa.leap_seconds.get().tobytes()).hexdigest(),
                'policy': POLICY}
    except (ImportError, OSError):
        raise SazuError('SOURCE_NOT_AVAILABLE') from None


def project_solar_time(time) -> tuple[datetime, str]:
    """Project a scalar Skyfield TT event with an explicit clock provenance.

    Pre-1960 legacy values are retained ONLY so prior research can be reproduced.
    Their label prevents an apparent match from certifying nonexistent UTC.
    Modern conversion intentionally remains byte-for-byte the existing model;
    future leap seconds are still an assumption, not a prediction.
    """
    jd1, jd2 = _split(float(time.whole), float(time.tt_fraction))
    if ((jd1-_START_JD)+jd2)*86400 < _START_TT_SECONDS-1e-9:
        basis = 'legacy_pre1960_projection'
    elif ((jd1-_END_JD)+jd2)*86400 < _END_TT_SECONDS:
        return historical_utc_from_tt(jd1, jd2), 'erfa_historical_utc'
    else:
        basis = 'skyfield_utc_leap_table'
    value = time.utc_datetime()
    require(type(value) is datetime and value.tzinfo is UTC, 'DATA_INTEGRITY_FAILED')
    return value, basis
