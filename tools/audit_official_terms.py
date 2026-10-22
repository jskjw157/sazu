"""Explicit research experiment; downloads belong to a separate acquisition step."""
import argparse
from dataclasses import asdict
from datetime import UTC, date, datetime
import hashlib
from importlib.metadata import version
from pathlib import Path
import platform
import sys

from sazu.cli import _manifest
from sazu.contracts import SourceManifest, strict_int, utc_datetime
from sazu.errors import SazuError, require
from sazu.kasi_reference import KASI_URL
from sazu.serde import canonical_json, digest, parse_request
from sazu.solar_terms import generate_terms
from sazu.source_audit import execute_audit
from sazu.utc_history import POLICY, erfa_identity

KASI_SHA256 = '508761248c7d18eb1ca1bcb1fcace2ba29f3f511d085321ae1e633c74d8e9e34'
KERNEL_SHA256 = 'c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2'
KERNEL_URL = 'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp'
ROOT = Path(__file__).resolve().parents[1]


def build_request(kasi: Path, kernel: Path, acquired_at: datetime,
                  first: int, last: int) -> dict:
    require(utc_datetime(acquired_at))
    require(strict_int(first, 1920, 2050) and strict_int(last, 1920, 2050)
            and first <= last, 'UNSUPPORTED_RANGE')
    reference = SourceManifest('kasi-24-terms-20260901', 'KASI', '2026-09-01', KASI_URL,
        KASI_SHA256, kasi.stat().st_size, acquired_at, date(1920,1,1), date(2100,12,31),
        'fixed-UTC+9', 'rounded_minute', 'unreviewed', 'https://www.kasi.re.kr/kor/pageView/134',
        ('kasi-ephemeris-lineage-unestablished',), 'kasi-txt-v1')
    ephemeris = SourceManifest('jpl-de440s', 'JPL', 'DE440s', KERNEL_URL,
        KERNEL_SHA256, kernel.stat().st_size, acquired_at, date(1850,1,1), date(2149,1,1),
        'TDB', 'computed', 'unreviewed', 'https://naif.jpl.nasa.gov/naif/rules.html',
        ('jpl-de440s',), 'skyfield-local-v1')
    # Known hashes are assertions, never replaced with hashes of unknown input.
    return parse_request(canonical_json({'reference_path':str(kasi),
        'reference_manifest':asdict(reference), 'kernel_path':str(kernel),
        'kernel_manifest':asdict(ephemeris), 'start_year':first, 'end_year':last}))


def run_audit(kasi: Path, kernel: Path, acquired_at: datetime,
              first: int = 1920, last: int = 2050) -> dict:
    request = build_request(kasi, kernel, acquired_at, first, last)
    comparison = execute_audit('compare', request)
    # Auxiliary years support future boundary lookups. Structural generation is
    # explicitly NOT counted as official numerical comparison.
    auxiliary = []
    for year in (first-1, last+1):
        events = generate_terms(year, kernel, _manifest(request['kernel_manifest']))
        auxiliary.append({'year':year, 'event_count':len(events), 'sha256':digest(events),
                          'evidence_level':'structure_only_not_reference_comparison'})
    packages = {name:version(name) for name in
                ('skyfield','jplephem','sgp4','numpy','korean-lunar-calendar','tzdata')}
    code_paths = ('src/sazu/kasi_reference.py','src/sazu/term_audit.py',
                  'src/sazu/source_audit.py','src/sazu/solar_terms.py','src/sazu/utc_history.py',
                  'tools/audit_official_terms.py')
    output = {'status':comparison['status'], 'production_authorized':False,
        'reference_comparison':comparison, 'auxiliary_years':auxiliary,
        'time_conversion': {'policy': POLICY, 'historical_utc': erfa_identity(),
            'pre1960': 'legacy_projection_not_historical_utc',
            'future_utc': 'existing_leap_table_extrapolation_not_prediction'},
        'environment':{'python':platform.python_version(), 'packages':packages,
            'code_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in code_paths}},
        'uncompleted_gates':[
            {'gate':'korean-lunar-official-full-range','status':'not_run'},
            {'gate':'source-rights-review','status':'not_approved'},
            {'gate':'physical-ephemeris-independence','status':'not_established'},
            {'gate':'production-activation','status':'not_implemented'}]}
    output['artifact_sha256'] = digest(output)
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kasi',type=Path,required=True)
    parser.add_argument('--kernel',type=Path,required=True)
    parser.add_argument('--acquired-at',required=True,help='Actual acquisition UTC timestamp, ISO 8601')
    parser.add_argument('--start-year',type=int,default=1920)
    parser.add_argument('--end-year',type=int,default=2050)
    args = parser.parse_args(argv)
    try:
        acquired = datetime.fromisoformat(args.acquired_at)
        require(utc_datetime(acquired))
        report = run_audit(args.kasi,args.kernel,acquired.astimezone(UTC),args.start_year,args.end_year)
        print(canonical_json(report))
        return 0 if report['status']=='passed' else (1 if report['status']=='failed' else 2)
    except FileNotFoundError:
        error = SazuError('SOURCE_NOT_AVAILABLE')
    except SazuError as exc:
        error = exc
    except (ValueError,TypeError,OverflowError):
        error = SazuError('INVALID_INPUT')
    except OSError:
        error = SazuError('DATA_INTEGRITY_FAILED')
    except Exception:
        print(canonical_json({'status':'blocked','production_authorized':False,
                              'error':SazuError('INTERNAL_ERROR').as_dict()}))
        return 3
    print(canonical_json({'status':'blocked','production_authorized':False,'error':error.as_dict()}))
    return 2


if __name__ == '__main__':
    sys.exit(main())
