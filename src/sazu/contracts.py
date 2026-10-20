"""Small immutable contracts shared by offline foundation modules."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from urllib.parse import urlsplit

from .errors import require

IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')
SHA256 = re.compile(r'[a-f0-9]{64}\Z')
PRECISIONS = frozenset({'instant', 'minute_bucket', 'rounded_minute',
                        'interval', 'unknown', 'computed'})


def valid_id(value: object) -> bool:
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def valid_hash(value: object) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def strict_int(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def utc_datetime(value: object) -> bool:
    return (type(value) is datetime and value.tzinfo is not None
            and value.utcoffset() == timedelta(0))


def public_url(value: object) -> bool:
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        return False
    try:
        u = urlsplit(value)
        return (u.scheme == 'https' and bool(u.hostname) and u.port in (None, 443)
                and not u.username and not u.password and not u.query and not u.fragment)
    except ValueError:
        return False


@dataclass(frozen=True)
class SourceManifest:
    source_id: str
    provider: str
    version: str
    url: str
    sha256: str
    size_bytes: int
    acquired_at: datetime
    coverage_start: date
    coverage_end: date
    clock: str
    precision: str
    rights_status: str
    rights_url: str
    lineage: tuple[str, ...]
    parser_version: str

    def __post_init__(self) -> None:
        require(valid_id(self.source_id) and valid_id(self.version)
                and valid_id(self.parser_version))
        require(isinstance(self.provider, str) and 0 < len(self.provider) <= 200)
        require(public_url(self.url) and public_url(self.rights_url))
        require(valid_hash(self.sha256) and strict_int(self.size_bytes, 0, 1 << 40))
        require(utc_datetime(self.acquired_at))
        require(type(self.coverage_start) is date and type(self.coverage_end) is date)
        require(self.coverage_start <= self.coverage_end)
        require(isinstance(self.clock, str) and 0 < len(self.clock) <= 100)
        require(type(self.precision) is str and self.precision in PRECISIONS)
        require(type(self.rights_status) is str and self.rights_status in {'unreviewed', 'permitted', 'restricted'})
        require(type(self.lineage) is tuple and bool(self.lineage)
                and all(valid_id(x) for x in self.lineage))


@dataclass(frozen=True)
class UtcInterval:
    """A closed point or explicitly bounded UTC interval."""
    start: datetime
    end: datetime
    start_inclusive: bool = True
    end_inclusive: bool = False

    def __post_init__(self) -> None:
        require(utc_datetime(self.start) and utc_datetime(self.end))
        require(type(self.start_inclusive) is bool and type(self.end_inclusive) is bool)
        require(self.start <= self.end)
        require(self.start < self.end or (self.start_inclusive and self.end_inclusive))

    @property
    def is_point(self) -> bool:
        return self.start == self.end
