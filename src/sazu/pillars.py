"""S2 four-pillars *research* engine with explicit ruleset and pinned S1 inputs.

No fortune API, hidden midnight/noon defaults, or publication approval.
Solar jie times are inputs, never fitted to published minute cells here.
"""
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from bisect import bisect_right

from .contracts import strict_int, utc_datetime, valid_hash
from .errors import require
from .solar_terms import TERMS
from .temporal import TimeInput, normalize_time
from .tzif import load_zone

RULESET_MIDNIGHT = 's2-civil-midnight-v1'
RULESET_ZI23 = 's2-civil-zi23-v1'
_RULESETS = frozenset({RULESET_MIDNIGHT, RULESET_ZI23})
_STEMS = tuple('갑을병정무기경신임계')
_BRANCHES = tuple('자축인묘진사오미신유술해')
_ELEMENT_NAMES = ('목', '화', '토', '금', '수')
_BRANCH_ELEMENTS = ('수', '토', '목', '목', '토', '화',
                    '화', '토', '금', '금', '토', '수')
_DAY_ANCHOR = date(2000, 1, 1)
_DAY_ANCHOR_INDEX = 54  # 戊午. Independent cross-check: 1984-02-02 is 丙寅.
_FIXED_KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class CyclePillar:
    index: int

    def __post_init__(self):
        require(strict_int(self.index, 0, 59))

    @property
    def stem_index(self) -> int:
        return self.index % 10

    @property
    def branch_index(self) -> int:
        return self.index % 12

    @property
    def name(self) -> str:
        return _STEMS[self.stem_index] + _BRANCHES[self.branch_index]

    @property
    def stem_element(self) -> str:
        return _ELEMENT_NAMES[self.stem_index // 2]

    @property
    def branch_primary_element(self) -> str:
        return _BRANCH_ELEMENTS[self.branch_index]


def sexagenary_pillar(index: int) -> CyclePillar:
    require(type(index) is int and -10**9 <= index <= 10**9)
    return CyclePillar(index % 60)


def day_pillar(local_calendar_date: date) -> CyclePillar:
    """Gregorian civil-date day pillar; no implied 23:00 policy."""
    require(type(local_calendar_date) is date and 1900 <= local_calendar_date.year <= 2050,
            'UNSUPPORTED_RANGE')
    return sexagenary_pillar(_DAY_ANCHOR_INDEX +
                             (local_calendar_date - _DAY_ANCHOR).days)


def _from_pair(stem_index: int, branch_index: int) -> CyclePillar:
    require(strict_int(stem_index, 0, 9) and strict_int(branch_index, 0, 11)
            and stem_index % 2 == branch_index % 2)
    for value in range(60):
        if value % 10 == stem_index and value % 12 == branch_index:
            return CyclePillar(value)
    raise AssertionError('Unreachable sexagenary parity')


@dataclass(frozen=True)
class JieBoundary:
    event_year: int
    term_id: int
    instant_utc: datetime
    source_sha256: str
    ephemeris_model_id: str
    clock_model_id: str
    clock_status: str
    production_authorized: bool = False

    def __post_init__(self):
        require(strict_int(self.event_year, 1900, 2051)
                and strict_int(self.term_id, 1, 23) and self.term_id % 2 == 1)
        require(utc_datetime(self.instant_utc))
        require(self.instant_utc.astimezone(_FIXED_KST).year == self.event_year)
        require(valid_hash(self.source_sha256)
                and valid_hash(self.ephemeris_model_id)
                and valid_hash(self.clock_model_id))
        require(type(self.clock_status) is str and self.clock_status in
                {'modern_utc', 'historical_utc', 'future_utc_assumption',
                 'historical_clock_unresolved'})
        require(self.production_authorized is False)
        require(TERMS[self.term_id-1].is_month_boundary)


@dataclass(frozen=True)
class FourPillars:
    year: CyclePillar
    month: CyclePillar
    day: CyclePillar
    hour: CyclePillar
    instant_utc: datetime
    local_wall: datetime
    ruleset_id: str
    tzdata_version: str
    zone_sha256: str
    source_sha256: str
    ephemeris_model_id: str
    clock_model_id: str
    lichun_boundary_utc: datetime
    month_boundary_utc: datetime
    next_month_boundary_utc: datetime
    month_boundary_term_id: int
    visible_elements: dict[str, int]
    evidence_level: str = 'rules_applied_to_unapproved_term_candidates'
    production_authorized: bool = False


@dataclass(frozen=True)
class ChartCandidates:
    charts: tuple[FourPillars, ...]
    warnings: tuple[str, ...]
    precision: str
    ruleset_id: str
    production_authorized: bool = False


def _review_jie(edges: tuple[JieBoundary, ...], instant: datetime,
                local_year: int) -> tuple[JieBoundary, JieBoundary, JieBoundary]:
    require(type(edges) is tuple and 3 <= len(edges) <= 72
            and all(type(edge) is JieBoundary for edge in edges))
    require(all(e.clock_status in {'modern_utc', 'historical_utc'} for e in edges),
            'RELEASE_NOT_APPROVED')
    provenance = {(e.source_sha256, e.ephemeris_model_id, e.clock_model_id) for e in edges}
    require(len(provenance) == 1, 'SOURCE_CONFLICT')
    times = [e.instant_utc for e in edges]
    require(all(a < b for a, b in zip(times, times[1:])), 'DATA_INTEGRITY_FAILED')
    require(len({(e.event_year, e.term_id) for e in edges}) == len(edges),
            'DATA_INTEGRITY_FAILED')
    # IDs 1,3,...23 denote the 12 jie. Adjacent months must be present.
    require(all((n.term_id - p.term_id) % 24 == 2 for p, n in zip(edges, edges[1:])),
            'SOURCE_NOT_AVAILABLE')
    matching_lichun = [e for e in edges if e.event_year == local_year and e.term_id == 1]
    require(len(matching_lichun) == 1, 'SOURCE_NOT_AVAILABLE')
    rank = bisect_right(times, instant)
    require(0 < rank < len(edges), 'SOURCE_NOT_AVAILABLE')
    return edges[rank - 1], edges[rank], matching_lichun[0]


def _visible_elements(pillars: tuple[CyclePillar, ...]) -> dict[str, int]:
    result = {e: 0 for e in _ELEMENT_NAMES}
    for pillar in pillars:
        result[pillar.stem_element] += 1
        result[pillar.branch_primary_element] += 1
    return result


def calculate_exact_chart(instant_utc: datetime, zone: str,
                          jie_edges: tuple[JieBoundary, ...],
                          ruleset_id: str) -> FourPillars:
    """Four stems+branches at one exact absolute instant, not an S1 time bucket.

    All computed boundaries are model instants, not independently approved
    physical truth. The output can never be promoted to production by caller.
    """
    require(utc_datetime(instant_utc))
    require(type(ruleset_id) is str and ruleset_id in _RULESETS)
    pinned = load_zone(zone)
    wall = instant_utc.astimezone(pinned.zone)
    require(1901 <= wall.year <= 2050, 'UNSUPPORTED_RANGE')
    current, next_month, lichun = _review_jie(jie_edges, instant_utc, wall.year)
    solar_year = wall.year if instant_utc >= lichun.instant_utc else wall.year - 1
    year = sexagenary_pillar(solar_year - 1984)
    month_offset = (current.term_id - 1) // 2
    month_stem = (2 + 2 * (year.stem_index % 5) + month_offset) % 10
    month_branch = (2 + month_offset) % 12
    month = _from_pair(month_stem, month_branch)
    day_date = wall.date()
    if ruleset_id == RULESET_ZI23 and wall.hour == 23:
        day_date += timedelta(days=1)
    day = day_pillar(day_date)
    hour_branch = ((wall.hour + 1) // 2) % 12
    hour_stem = (2 * (day.stem_index % 5) + hour_branch) % 10
    hour = _from_pair(hour_stem, hour_branch)
    pillars = (year, month, day, hour)
    return FourPillars(year, month, day, hour, instant_utc, wall, ruleset_id,
                       pinned.version, pinned.sha256, current.source_sha256,
                       current.ephemeris_model_id, current.clock_model_id,
                       lichun.instant_utc, current.instant_utc,
                       next_month.instant_utc, current.term_id,
                       _visible_elements(pillars))


def calculate_instant_candidates(request: TimeInput,
                                 jie_edges: tuple[JieBoundary, ...],
                                 ruleset_id: str) -> ChartCandidates:
    """Fold ambiguity -> explicit candidate charts. Never impute unknown time.

    Support for uncertain intervals and unknown birth hours is a *separate*
    subsequent task, not achieved by sampling and treating a guess as fact.
    """
    require(type(request) is TimeInput and request.precision == 'instant')
    normalized = normalize_time(request)
    require(bool(normalized.intervals) and all(i.is_point for i in normalized.intervals))
    charts = tuple(calculate_exact_chart(i.start, normalized.zone, jie_edges, ruleset_id)
                   for i in normalized.intervals)
    return ChartCandidates(charts, normalized.warnings, normalized.precision, ruleset_id)


def jie_edges_from_reviewed(events: tuple) -> tuple[JieBoundary, ...]:
    """Bridge to S1 reviewed terms; refuse unprojectable calendar clock events.

    Call with adjacent annual batches from generate_reviewed_terms(), not
    raw Skyfield SolarTermEvent (which may use invalid historical UTC).
    """
    from .term_clock import ReviewedSolarTerm

    require(type(events) is tuple and 3 <= len(events) <= 200
            and all(type(e) is ReviewedSolarTerm for e in events))
    edges = []
    for event in events:
        require(event.production_authorized is False
                and event.clock.production_authorized is False)
        if event.kasi_id % 2 == 0:
            continue
        require(event.clock.comparable_as_utc
                and event.clock.status in {'modern_utc', 'historical_utc'}
                and utc_datetime(event.clock.instant_utc), 'RELEASE_NOT_APPROVED')
        edges.append(JieBoundary(event.event_year, event.kasi_id,
                                 event.clock.instant_utc,
                                 event.source_sha256,
                                 event.ephemeris_model_id,
                                 event.clock.clock_model_id,
                                 event.clock.status))
    result = tuple(sorted(edges, key=lambda b: b.instant_utc))
    # Validate global month sequence and remove ability to skip a boundary
    # before calculate_exact_chart() selects the right interval.
    require(3 <= len(result) <= 72, 'SOURCE_NOT_AVAILABLE')
    require(all((n.term_id-p.term_id) % 24 == 2 for p,n in zip(result,result[1:])),
            'SOURCE_NOT_AVAILABLE')
    return result
