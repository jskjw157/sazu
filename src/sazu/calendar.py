"""Strict Korean calendar adapter; never a four-pillars calculation engine."""
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import hashlib
from importlib.metadata import version
import inspect
from pathlib import Path

from korean_lunar_calendar import KoreanLunarCalendar

from .contracts import strict_int
from .errors import SazuError, require

TARGET_START = date(1920, 1, 1)
TARGET_END = date(2050, 12, 31)


@dataclass(frozen=True)
class CalendarInput:
    kind: str
    year: int
    month: int
    day: int
    leap: str | None = None

    def __post_init__(self) -> None:
        require(type(self.kind) is str and self.kind in {'gregorian', 'korean_lunar'})
        require(strict_int(self.year, 1, 9999) and strict_int(self.month, 1, 12)
                and strict_int(self.day, 1, 31))
        if self.kind == 'gregorian':
            require(self.leap is None)
            try:
                date(self.year, self.month, self.day)
            except ValueError:
                raise SazuError('INVALID_INPUT') from None
        else:
            require(type(self.leap) is str and self.leap in {'regular', 'leap', 'unknown'})
            require(self.day <= 30)


@dataclass(frozen=True)
class CalendarDate:
    solar: date
    lunar_year: int
    lunar_month: int
    lunar_day: int
    is_leap: bool

    def __post_init__(self) -> None:
        require(type(self.solar) is date and strict_int(self.lunar_year, 1, 9999)
                and strict_int(self.lunar_month, 1, 12) and strict_int(self.lunar_day, 1, 30)
                and type(self.is_leap) is bool)


@dataclass(frozen=True)
class CalendarResult:
    request: CalendarInput
    candidates: tuple[CalendarDate, ...]
    library_version: str
    library_sha256: str
    evidence_level: str = 'library_regression_not_official_verification'


@lru_cache(maxsize=1)
def library_identity() -> tuple[str, str]:
    """Hash the actual source containing the upstream table, not its name."""
    try:
        path = Path(inspect.getfile(KoreanLunarCalendar))
        return version('korean-lunar-calendar'), hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise SazuError('SOURCE_NOT_AVAILABLE') from None


def _read(calendar: KoreanLunarCalendar) -> CalendarDate:
    return CalendarDate(date(calendar.solarYear, calendar.solarMonth, calendar.solarDay),
                        calendar.lunarYear, calendar.lunarMonth, calendar.lunarDay,
                        bool(calendar.isIntercalation))


def convert_calendar(request: CalendarInput) -> CalendarResult:
    require(type(request) is CalendarInput)
    candidates: list[CalendarDate] = []
    if request.kind == 'gregorian':
        solar = date(request.year, request.month, request.day)
        require(TARGET_START <= solar <= TARGET_END, 'UNSUPPORTED_RANGE')
        calendar = KoreanLunarCalendar()
        require(calendar.setSolarDate(request.year, request.month, request.day),
                'DATA_INTEGRITY_FAILED')
        result = _read(calendar)
        require(result.solar == solar, 'DATA_INTEGRITY_FAILED')
        candidates.append(result)
    else:
        # 1919 lunar dates can normalize into the beginning of solar 1920.
        require(1919 <= request.year <= 2050, 'UNSUPPORTED_RANGE')
        flags = (False, True) if request.leap == 'unknown' else (request.leap == 'leap',)
        for leap in flags:
            calendar = KoreanLunarCalendar()
            if not calendar.setLunarDate(request.year, request.month, request.day, leap):
                continue
            result = _read(calendar)
            # Older upstream versions silently accept nonexistent leap requests.
            if (result.lunar_year, result.lunar_month, result.lunar_day, result.is_leap) != (
                    request.year, request.month, request.day, leap):
                continue
            check = KoreanLunarCalendar()
            require(check.setSolarDate(result.solar.year, result.solar.month, result.solar.day),
                    'DATA_INTEGRITY_FAILED')
            require(_read(check) == result, 'DATA_INTEGRITY_FAILED')
            # Do not silently drop an out-of-range possible birth date.
            require(TARGET_START <= result.solar <= TARGET_END, 'UNSUPPORTED_RANGE')
            candidates.append(result)
        require(bool(candidates))
    library_version, library_sha = library_identity()
    return CalendarResult(request, tuple(sorted(set(candidates), key=lambda c: c.solar)),
                          library_version, library_sha)
