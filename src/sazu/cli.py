"""One JSON request on stdin. No automatic input persistence or remote fallback."""
from datetime import date, datetime, time
from pathlib import Path
import re
import sys

from .calendar import CalendarInput, convert_calendar, library_identity
from .contracts import SourceManifest
from .errors import SazuError, require
from .serde import canonical_json, parse_request
from .solar_terms import generate_terms, normalize_reference_record
from .sources import verify_file, acquire_source
from .temporal import TimeInput, normalize_time
from .tzif import load_zone

MAX_REQUEST_BYTES = 65536


def _fields(value, required, optional=()):
    require(type(value) is dict and set(required) <= value.keys()
            and value.keys() <= set(required) | set(optional))


def _date(value):
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is not None)
    return date.fromisoformat(value)


def _time(value):
    require(type(value) is str and re.fullmatch(r'\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?', value) is not None)
    return time.fromisoformat(value)


def _manifest(value):
    fields = ('source_id','provider','version','url','sha256','size_bytes','acquired_at',
              'coverage_start','coverage_end','clock','precision','rights_status',
              'rights_url','lineage','parser_version')
    _fields(value, fields)
    data = dict(value)
    require(type(data['acquired_at']) is str and type(data['lineage']) is list)
    data['acquired_at'] = datetime.fromisoformat(data['acquired_at'])
    data['coverage_start'] = _date(data['coverage_start'])
    data['coverage_end'] = _date(data['coverage_end'])
    data['lineage'] = tuple(data['lineage'])
    return SourceManifest(**data)


def dispatch(command: str, request: dict):
    if command == 'calendar':
        _fields(request, ('kind','year','month','day'), ('leap',))
        return convert_calendar(CalendarInput(**request))
    if command == 'normalize-time':
        _fields(request, ('local_date','zone','precision'),
                ('local_time','end_local','start_inclusive','end_inclusive','fold'))
        data = dict(request)
        data['local_date'] = _date(data['local_date'])
        if 'local_time' in data:
            data['local_time'] = _time(data['local_time'])
        if 'end_local' in data:
            require(type(data['end_local']) is str and 'T' in data['end_local'])
            data['end_local'] = datetime.fromisoformat(data['end_local'])
        return normalize_time(TimeInput(**data))
    if command == 'reference-term':
        _fields(request, ('record','manifest'))
        return normalize_reference_record(request['record'], _manifest(request['manifest']))
    if command in ('verify-source','generate-terms','acquire-source'):
        required = ['path','manifest']
        if command == 'generate-terms': required.append('year')
        if command == 'acquire-source': required.append('url')
        _fields(request, required)
        require(type(request['path']) is str and 0 < len(request['path']) <= 4096)
        path = Path(request['path'])
        manifest = _manifest(request['manifest'])
        if command == 'generate-terms': return generate_terms(request['year'],path,manifest)
        if command == 'acquire-source': return {'sha256': acquire_source(request['url'],path,manifest)}
        return {'sha256': verify_file(path,manifest)}
    if command == 'environment':
        _fields(request, ())
        calendar_version, calendar_sha = library_identity()
        zone = load_zone('Asia/Seoul')
        return {'calendar_version':calendar_version,'calendar_sha256':calendar_sha,
                'tzdata_version':zone.version,'iana_version':zone.iana_version,
                'zone_sha256':zone.sha256,'python':sys.version.split()[0]}
    raise SazuError('INVALID_INPUT')


def main(argv=None) -> int:
    try:
        args = list(sys.argv[1:] if argv is None else argv)
        require(len(args) == 1)
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES+1)
        require(len(raw) <= MAX_REQUEST_BYTES, 'REQUEST_TOO_LARGE')
        request = parse_request(raw.decode('utf-8'))
        result = dispatch(args[0], request)
        print(canonical_json({'ok':True,'production_authorized':False,'result':result}))
        return 0
    except SazuError as error:
        print(canonical_json({'ok':False,'error':error.as_dict()}))
        return 2
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        print(canonical_json({'ok':False,'error':SazuError('INVALID_INPUT').as_dict()}))
        return 2
    except Exception:
        print(canonical_json({'ok':False,'error':SazuError('INTERNAL_ERROR').as_dict()}))
        return 3
