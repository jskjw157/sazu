"""Offline administrative CLI. Never exported through the research HTTP service.

Usage: one JSON request on stdin to ``python -m sazu.source_audit inspect|compare``.
Operator-controlled source parent directories are required. Reports do not contain
raw source rows, local paths, credentials, or a production authorization flag set true.
"""
import hashlib
import os
from pathlib import Path
import stat
import sys

from .cli import _fields, _manifest
from .contracts import SourceManifest, strict_int
from .errors import SazuError, require
from .kasi_reference import MAX_DOCUMENT_BYTES, parse_kasi_document
from .serde import canonical_json, parse_request
from .solar_terms import generate_terms
from .sources import verify_file
from .term_audit import compare_term_range, reference_summary

MAX_REQUEST_BYTES = 65536


def read_reference_bytes(path: Path, manifest: SourceManifest) -> bytes:
    """Hash and return the same bounded bytes from a single no-follow descriptor."""
    require(type(manifest) is SourceManifest)
    require(0 < manifest.size_bytes <= MAX_DOCUMENT_BYTES, 'REQUEST_TOO_LARGE')
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                             | getattr(os, 'O_NONBLOCK', 0))
    except FileNotFoundError:
        raise SazuError('SOURCE_NOT_AVAILABLE') from None
    except OSError:
        raise SazuError('DATA_INTEGRITY_FAILED') from None
    try:
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size == manifest.size_bytes,
                    'DATA_INTEGRITY_FAILED')
            raw = stream.read(manifest.size_bytes+1)
            require(len(raw) == manifest.size_bytes
                    and hashlib.sha256(raw).hexdigest() == manifest.sha256,
                    'DATA_INTEGRITY_FAILED')
            return raw
    except OSError:
        raise SazuError('DATA_INTEGRITY_FAILED') from None


def _path(value) -> Path:
    require(type(value) is str and 0 < len(value) <= 4096 and '\x00' not in value)
    return Path(value)


def execute_audit(command: str, request: dict) -> dict:
    if command == 'inspect':
        _fields(request, ('path', 'manifest'))
        manifest = _manifest(request['manifest'])
        document = parse_kasi_document(read_reference_bytes(_path(request['path']), manifest), manifest)
        return {'status': 'inspected', 'production_authorized': False,
                'reference': reference_summary(document)}
    require(command == 'compare')
    _fields(request, ('reference_path', 'reference_manifest', 'kernel_path',
                      'kernel_manifest', 'start_year', 'end_year'))
    first, last = request['start_year'], request['end_year']
    require(strict_int(first, 1919, 2051) and strict_int(last, 1919, 2051)
            and first <= last, 'UNSUPPORTED_RANGE')
    reference_manifest = _manifest(request['reference_manifest'])
    document = parse_kasi_document(
        read_reference_bytes(_path(request['reference_path']), reference_manifest), reference_manifest)
    require(document.start_year <= first <= last <= document.end_year, 'UNSUPPORTED_RANGE')
    kernel_path = _path(request['kernel_path'])
    kernel_manifest = _manifest(request['kernel_manifest'])
    require(kernel_manifest.clock == 'TDB' and kernel_manifest.precision == 'computed'
            and 0 < kernel_manifest.size_bytes <= 64*1024*1024)
    verify_file(kernel_path, kernel_manifest)
    values = []
    for year in range(first, last+1):
        values.extend(generate_terms(year, kernel_path, kernel_manifest))
    return compare_term_range(values, document, first, last)


def main(argv=None) -> int:
    try:
        args = list(sys.argv[1:] if argv is None else argv)
        require(len(args) == 1 and args[0] in ('inspect', 'compare'))
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES+1)
        require(len(raw) <= MAX_REQUEST_BYTES, 'REQUEST_TOO_LARGE')
        report = execute_audit(args[0], parse_request(raw.decode('utf-8')))
        status = report['status']
        passed = status in ('passed', 'inspected')
        print(canonical_json({'ok': passed, 'result': report}))
        return 0 if passed else (1 if status == 'failed' else 2)
    except SazuError as error:
        print(canonical_json({'ok': False, 'error': error.as_dict()}))
        return 2
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        print(canonical_json({'ok': False, 'error': SazuError('INVALID_INPUT').as_dict()}))
        return 2
    except Exception:
        print(canonical_json({'ok': False, 'error': SazuError('INTERNAL_ERROR').as_dict()}))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
