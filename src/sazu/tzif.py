"""Read pinned tzdata resources, with exact TZif transition boundaries.

The small structural reader follows RFC 8536/9636. ZoneInfo performs the
actual timezone interpretation. POSIX future rules use dateutil's public API.
Unsupported extensions fail closed rather than freezing the last offset.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
import hashlib
from importlib import resources
import io
import re
import struct
import warnings
from zoneinfo import ZoneInfo

from dateutil.tz import tzstr
import tzdata

from .errors import SazuError, require

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class TzifData:
    transitions: tuple[int, ...]
    footer: str


def parse_tzif(raw: bytes) -> TzifData:
    require(type(raw) is bytes and 44 <= len(raw) <= 131072, 'DATA_INTEGRITY_FAILED')

    def block(pos: int, width: int) -> tuple[int, tuple[int, ...], bytes]:
        require(pos + 44 <= len(raw) and raw[pos:pos+4] == b'TZif',
                'DATA_INTEGRITY_FAILED')
        version = raw[pos+4:pos+5]
        require(version in (b'\x00', b'2', b'3', b'4'), 'DATA_INTEGRITY_FAILED')
        gmt, std, leap, ntime, ntype, nchar = struct.unpack_from('>6I', raw, pos+20)
        require(0 < ntype <= 256 and ntime <= 10000 and nchar <= 16384
                and gmt in (0, ntype) and std in (0, ntype) and leap == 0,
                'DATA_INTEGRITY_FAILED')
        start = pos + 44
        end = start + ntime*(width+1) + ntype*6 + nchar + leap*(width+4) + std + gmt
        require(end <= len(raw), 'DATA_INTEGRITY_FAILED')
        fmt = 'q' if width == 8 else 'i'
        transitions = struct.unpack_from('>'+fmt*ntime, raw, start) if ntime else ()
        require(all(a < b for a, b in zip(transitions, transitions[1:])),
                'DATA_INTEGRITY_FAILED')
        indices = raw[start+ntime*width:start+ntime*(width+1)]
        require(all(x < ntype for x in indices), 'DATA_INTEGRITY_FAILED')
        type_start = start + ntime*(width+1)
        for i in range(ntype):
            offset, dst, abbreviation = struct.unpack_from('>iBB', raw, type_start+i*6)
            require(-86400 < offset < 86400 and dst in (0, 1) and abbreviation < nchar,
                    'DATA_INTEGRITY_FAILED')
        return end, transitions, version

    try:
        end, transitions, version = block(0, 4)
        footer = ''
        if version != b'\x00':
            end, transitions, second_version = block(end, 8)
            require(second_version == version, 'DATA_INTEGRITY_FAILED')
            tail = raw[end:]
            require(tail.startswith(b'\n') and tail.endswith(b'\n')
                    and tail.count(b'\n') == 2, 'DATA_INTEGRITY_FAILED')
            footer = tail[1:-1].decode('ascii')
        else:
            require(end == len(raw), 'DATA_INTEGRITY_FAILED')
        return TzifData(tuple(transitions), footer)
    except (struct.error, UnicodeError, OverflowError):
        raise SazuError('DATA_INTEGRITY_FAILED') from None


@dataclass(frozen=True)
class PinnedZone:
    zone: ZoneInfo
    version: str
    iana_version: str
    sha256: str
    data: TzifData

    def boundaries(self, start: datetime, end: datetime) -> tuple[datetime, ...]:
        low, high = (start-EPOCH).total_seconds(), (end-EPOCH).total_seconds()
        values = {EPOCH+timedelta(seconds=t) for t in self.data.transitions if low < t < high}
        last = self.data.transitions[-1] if self.data.transitions else float('-inf')
        if self.data.footer and high > last:
            # Angle-bracket abbreviations may contain numeric signs. Their names
            # do not affect transition arithmetic, so give dateutil simple labels.
            labels = iter(('AAA', 'BBB'))
            try:
                footer = re.sub(r'<[^>]+>', lambda _: next(labels), self.data.footer)
                with warnings.catch_warnings():
                    warnings.simplefilter('error')
                    rule = tzstr(footer, posix_offset=True)
                probe = datetime(2000, 1, 1, tzinfo=rule)
                standard_offset = probe.utcoffset() - probe.dst()
                for year in range(start.year-1, end.year+2):
                    for wall in rule.transitions(year) or ():
                        instant = (wall-standard_offset).replace(tzinfo=UTC)
                        if start < instant < end and (instant-EPOCH).total_seconds() > last:
                            values.add(instant)
            except (ValueError, TypeError, OverflowError, StopIteration, Warning):
                raise SazuError('UNSUPPORTED_TIMEZONE_RULE') from None
        return tuple(sorted(values))


@lru_cache(maxsize=256)
def load_zone(key: str) -> PinnedZone:
    require(isinstance(key, str) and 0 < len(key) <= 200
            and all(re.fullmatch(r'[A-Za-z0-9_+\-]+', part) for part in key.split('/')))
    try:
        raw = resources.files('tzdata.zoneinfo').joinpath(*key.split('/')).read_bytes()
        data = parse_tzif(raw)
        zone = ZoneInfo.from_file(io.BytesIO(raw), key=key)
        return PinnedZone(zone, tzdata.__version__, tzdata.IANA_VERSION,
                          hashlib.sha256(raw).hexdigest(), data)
    except (FileNotFoundError, IsADirectoryError, ModuleNotFoundError):
        raise SazuError('SOURCE_NOT_AVAILABLE') from None
    except (ValueError, OSError):
        raise SazuError('DATA_INTEGRITY_FAILED') from None
