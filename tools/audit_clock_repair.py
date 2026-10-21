"""Replay recorded numeric evidence, never call this a new KASI acquisition.

Input is the exact derived clock-probe artifact from CI run 39654192006.
No original KASI TXT or JPL kernel is included or downloaded by this tool.
"""
import argparse
from collections import Counter
import hashlib
from importlib import metadata, resources
import math
import os
from pathlib import Path
import stat

from sazu.contracts import strict_int
from sazu.errors import SazuError, require
from sazu.serde import canonical_json, parse_request, digest
from sazu.term_clock import project_tt_to_utc, clock_identity, UTC_RULES_REVIEWED_THROUGH

PROBE_SHA256 = '5c33bcb86f9ad8aa59a128994860fa52f32883d490c8bce1da1c2a7fdfe1025f'
BASELINE_SHA256 = '1d775590cab5d641429f12188043ebbfe8579b680a557eb727c2a22e119a8b82'
CANDIDATE_SHA256 = 'c136a26bac55f6fec41ed377ba433e446abcf574f85f8265f17dbfc344902546'


def load_replay(path: Path) -> dict:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                     | getattr(os, 'O_NONBLOCK', 0))
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 1024*1024,
                    'DATA_INTEGRITY_FAILED')
            raw = stream.read(1024*1024+1)
        require(hashlib.sha256(raw).hexdigest() == PROBE_SHA256, 'DATA_INTEGRITY_FAILED')
        result = parse_request(raw.decode('utf-8'))
        require(result['baseline_sha256'] == BASELINE_SHA256
                and result['candidate_sha256'] == CANDIDATE_SHA256
                and result['production_authorized'] is False, 'DATA_INTEGRITY_FAILED')
        rows = result['rows']
        require(len(rows) == 3144 and {(r['year'], r['term']) for r in rows}
                == {(y,t) for y in range(1920,2051) for t in range(1,25)},
                'DATA_INTEGRITY_FAILED')
        return result
    except (OSError, ValueError, KeyError, TypeError):
        raise SazuError('DATA_INTEGRITY_FAILED') from None


def summarize_rows(rows: list[dict]) -> dict:
    from skyfield.api import load
    require(type(rows) is list and 0 < len(rows) <= 3144)
    assets = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
              for p in resources.files('skyfield.data').iterdir()
              if p.name.endswith(('.npy','.npz','.data'))}
    legacy_model = digest({'skyfield':metadata.version('skyfield'), 'builtin_time_assets':assets,
                           'kernel':'c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2',
                           'mapping':'kasi-longitude-v1', 'epsilon_days':1e-8})
    require(legacy_model == 'c1b5092e6dd26c5e35e59c9118c05b7cd708782fe5e3900aefbb0f9c58dc5744',
            'SOURCE_CONFLICT')
    ts = load.timescale(builtin=True)
    counts = Counter()
    keys = set()
    fixed = []
    remaining = []
    for row in rows:
        require(type(row) is dict and strict_int(row.get('year'),1920,2050)
                and strict_int(row.get('term'),1,24))
        require(all(type(row.get(k)) in (float,int) and -1e9 < row[k] < 1e9
                    and math.isfinite(row[k]) for k in ('utc_delta','tt_jd')))
        key = row['year'], row['term']
        require(key not in keys, 'DATA_INTEGRITY_FAILED')
        keys.add(key)
        old_delta = row['utc_delta']
        old_match = -30 <= old_delta < 30
        counts['baseline_matched' if old_match else 'baseline_mismatched'] += 1
        projection = project_tt_to_utc(row['tt_jd'])
        counts[projection.status] += 1
        if not projection.comparable_as_utc:
            counts['blocked_original_mismatches'] += int(not old_match)
            continue
        legacy = ts.tt_jd(row['tt_jd']).utc_datetime()
        new_delta = old_delta + (projection.instant_utc-legacy).total_seconds()
        matched = -30 <= new_delta < 30
        counts['comparable_matched' if matched else 'comparable_mismatched'] += 1
        item = {'year':row['year'], 'kasi_id':row['term'],
                'old_delta_seconds':old_delta, 'new_delta_seconds':round(new_delta,6)}
        if matched and not old_match:
            fixed.append(item)
        if not matched:
            remaining.append(item)
        counts['new_mismatches'] += int(old_match and not matched)
    names = ('baseline_matched','baseline_mismatched','comparable_matched',
             'comparable_mismatched','historical_clock_unresolved','future_utc_assumption',
             'utc_conversion_warning','leap_second_unrepresentable',
             'blocked_original_mismatches','new_mismatches')
    return {'status':'blocked', 'production_authorized':False, 'total':len(rows),
            **{key:counts[key] for key in names},
            'minute_cell':'[-30,30) seconds from reference display',
            'fixed_original_mismatches':len(fixed), 'fixed_cases':fixed,
            'remaining_comparable_mismatches':remaining,
            'clock_identity':clock_identity(UTC_RULES_REVIEWED_THROUGH),
            'evidence_basis':'replay_of_prior_audit_not_new_official_acquisition',
            'limitation':'Clock conversion repaired; historical convention, future schedule, '
                         'remaining model differences and production approval are not resolved.'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = summarize_rows(load_replay(args.probe)['rows'])
        report.update({'probe_sha256':PROBE_SHA256, 'baseline_sha256':BASELINE_SHA256,
                       'legacy_candidate_sha256':CANDIDATE_SHA256})
        print(canonical_json(report))
        return 1  # Numeric/clock blockers remain; never a production-success exit.
    except SazuError as error:
        print(canonical_json({'status':'error','production_authorized':False,
                              'error':error.as_dict()}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
