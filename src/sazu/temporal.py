"""Exact local-time inverse images, not hourly sampling or assumed noon."""
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from .calendar import TARGET_END, TARGET_START
from .contracts import UtcInterval, strict_int
from .errors import require
from .tzif import load_zone


@dataclass(frozen=True)
class TimeInput:
    local_date: date
    zone: str
    precision: str
    local_time: time | None = None
    end_local: datetime | None = None
    start_inclusive: bool = True
    end_inclusive: bool = False
    fold: int | None = None

    def __post_init__(self) -> None:
        require(type(self.local_date) is date)
        require(type(self.zone) is str and 0 < len(self.zone) <= 200)
        require(TARGET_START <= self.local_date <= TARGET_END, 'UNSUPPORTED_RANGE')
        require(type(self.precision) is str and self.precision in {'instant', 'minute_bucket', 'rounded_minute', 'interval', 'unknown'})
        require(type(self.start_inclusive) is bool and type(self.end_inclusive) is bool)
        require(self.fold is None or strict_int(self.fold, 0, 1))
        require(self.fold is None or self.precision == 'instant')
        if self.precision == 'unknown':
            require(self.local_time is None and self.end_local is None)
        else:
            require(type(self.local_time) is time and self.local_time.tzinfo is None
                    and self.local_time.fold == 0)
        if self.precision == 'interval':
            require(type(self.end_local) is datetime and self.end_local.tzinfo is None
                    and self.end_local.fold == 0)
            start = datetime.combine(self.local_date, self.local_time)
            require(timedelta(0) < self.end_local-start <= timedelta(days=31))
            limit = datetime.combine(TARGET_END+timedelta(days=1), time())
            require(self.end_local < limit or (self.end_local == limit and not self.end_inclusive),
                    'UNSUPPORTED_RANGE')
        else:
            require(self.end_local is None and self.start_inclusive and not self.end_inclusive)
        if self.precision in {'minute_bucket', 'rounded_minute'}:
            require(self.local_time.second == 0 and self.local_time.microsecond == 0)


@dataclass(frozen=True)
class NormalizedBirth:
    precision: str
    zone: str
    intervals: tuple[UtcInterval, ...]
    tzdata_version: str
    iana_version: str
    zone_sha256: str
    warnings: tuple[str, ...]
    evidence_level: str = 'pinned_timezone_computation_not_production_approval'


def _points(wall: datetime, zone, fold: int | None = None) -> list[datetime]:
    found = set()
    for flag in (0, 1):
        utc = wall.replace(tzinfo=zone, fold=flag).astimezone(UTC)
        restored = utc.astimezone(zone)
        if restored.replace(tzinfo=None) == wall:
            if fold is None or restored.fold == fold:
                found.add(utc)
    return sorted(found)


def _union(intervals: list[UtcInterval]) -> tuple[UtcInterval, ...]:
    result: list[UtcInterval] = []
    for item in sorted(intervals, key=lambda i: (i.start, not i.start_inclusive, i.end)):
        if not result:
            result.append(item)
            continue
        prev = result[-1]
        if item.start < prev.end or (item.start == prev.end and (prev.end_inclusive or item.start_inclusive)):
            end = max(prev.end, item.end)
            end_inclusive = ((prev.end == end and prev.end_inclusive)
                             or (item.end == end and item.end_inclusive))
            result[-1] = UtcInterval(prev.start, end, prev.start_inclusive, end_inclusive)
        else:
            result.append(item)
    return tuple(result)


def _wall_union_seconds(pieces: list[tuple[datetime, datetime]]) -> float:
    merged: list[list[datetime]] = []
    for lo, hi in sorted(pieces):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    return sum((hi-lo).total_seconds() for lo, hi in merged)


def normalize_time(request: TimeInput) -> NormalizedBirth:
    require(type(request) is TimeInput)
    pinned = load_zone(request.zone)
    warnings: set[str] = set()
    wall = datetime.combine(request.local_date, request.local_time or time())
    if request.precision == 'instant':
        all_points = _points(wall, pinned.zone)
        require(bool(all_points), 'NONEXISTENT_LOCAL_TIME')
        if len(all_points) > 1:
            warnings.add('AMBIGUOUS_LOCAL_TIME')
        points = all_points if request.fold is None else _points(wall, pinned.zone, request.fold)
        require(bool(points))
        intervals = tuple(UtcInterval(p, p, True, True) for p in points)
    else:
        if request.precision == 'unknown':
            low, high = wall, wall+timedelta(days=1)
        elif request.precision == 'minute_bucket':
            low, high = wall, wall+timedelta(minutes=1)
        elif request.precision == 'rounded_minute':
            low, high = wall-timedelta(seconds=30), wall+timedelta(seconds=30)
        else:
            low, high = wall, request.end_local
        lower_limit = datetime.combine(TARGET_START, time())
        upper_limit = datetime.combine(TARGET_END+timedelta(days=1), time())
        require(low >= lower_limit and (high < upper_limit or
                (high == upper_limit and not request.end_inclusive)), 'UNSUPPORTED_RANGE')
        # All TZif offsets are validated to be strictly within one day.
        start = low.replace(tzinfo=UTC)-timedelta(days=1)
        end = high.replace(tzinfo=UTC)+timedelta(days=1)
        boundaries = (start, *pinned.boundaries(start, end), end)
        pieces: list[UtcInterval] = []
        walls: list[tuple[datetime, datetime]] = []
        for a, b in zip(boundaries, boundaries[1:]):
            offset = a.astimezone(pinned.zone).utcoffset()
            require(offset == (b-timedelta(microseconds=1)).astimezone(pinned.zone).utcoffset(),
                    'UNSUPPORTED_TIMEZONE_RULE')
            local_a = (a+offset).replace(tzinfo=None)
            local_b = (b+offset).replace(tzinfo=None)
            lo, hi = max(low, local_a), min(high, local_b)
            lo_inc = request.start_inclusive if lo == low else True
            hi_inc = request.end_inclusive if hi == high else False
            if hi == local_b:
                hi_inc = False
            if lo < hi or (lo == hi and lo_inc and hi_inc):
                pieces.append(UtcInterval((lo-offset).replace(tzinfo=UTC),
                                          (hi-offset).replace(tzinfo=UTC), lo_inc, hi_inc))
                walls.append((lo, hi))
        require(bool(pieces), 'NONEXISTENT_LOCAL_TIME')
        wall_coverage = _wall_union_seconds(walls)
        if (wall_coverage < (high-low).total_seconds()
                or (request.start_inclusive and not _points(low, pinned.zone))
                or (request.end_inclusive and not _points(high, pinned.zone))):
            warnings.add('PARTIAL_LOCAL_GAP')
        if sum((hi-lo).total_seconds() for lo, hi in walls) > wall_coverage:
            warnings.add('AMBIGUOUS_LOCAL_TIME')
        intervals = _union(pieces)
    return NormalizedBirth(request.precision, request.zone, intervals,
                           pinned.version, pinned.iana_version, pinned.sha256,
                           tuple(sorted(warnings)))
