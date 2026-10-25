"""Offline, research-only IAU1980 CPO sensitivity; never a Horizons replica.

USNO finals.all Bulletin A dPsi/dEps are relative to IAU1980, in mas,
with daily MJD(UTC) arguments. This explicit alternative EOP series is
not the frozen Horizons eop.261022.p270118 snapshot. No fitted corrections,
release approval, runtime imports, or automatic downloads are introduced.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import stat
import sys

import erfa
import numpy as np

from tools.horizons_frame_reconciliation import (
    compute_local, load_cases, wrap_degrees,
)

SOURCE_URL = 'https://maia.usno.navy.mil/ser7/finals.all'
SOURCE_SHA256 = 'd1e3293efcb2a4bc2a39b8aa73279e6d04ace357f1cd51eb7df5bac36bc727d7'
MAX_BYTES = 5_000_000
MAS_TO_RAD = math.pi / (180 * 3_600_000)


class AuditError(ValueError):
    """Missing, malformed, mixed-frame or unreviewed evidence."""


@dataclass(frozen=True)
class FinalsRow:
    mjd_utc: float
    flag: str
    dpsi_mas: float | None
    deps_mas: float | None
    dpsi_sigma_mas: float | None
    deps_sigma_mas: float | None


def parse_finals(text: str) -> tuple[FinalsRow, ...]:
    """Fixed columns from USNO readme.finals, Bulletin A only; no B fallback."""
    if type(text) is not str or not 0 < len(text) <= MAX_BYTES or not text.isascii():
        raise AuditError('Invalid finals text')
    out = []
    for line in text.splitlines():
        if not 185 <= len(line) <= 187:
            raise AuditError('Unexpected finals record length')
        try:
            mjd = float(line[7:15])
            if not math.isfinite(mjd) or not mjd.is_integer() or not 40000 <= mjd <= 70000:
                raise AuditError('Invalid MJD UTC')
            year = int(line[:2]) + (1900 if mjd <= 51543 else 2000)
            printed = date(year, int(line[2:4]), int(line[4:6]))
            if printed != date(1858, 11, 17) + timedelta(days=int(mjd)):
                raise AuditError('Calendar label and MJD disagree')
            if out and mjd != out[-1].mjd_utc + 1:
                raise AuditError('Duplicate, unordered or missing daily record')
            flag = line[95:96]
            parts = [line[97:106], line[106:115], line[116:125], line[125:134]]
            if all(not s.strip() for s in parts) and flag == ' ':
                values = [None] * 4
            elif flag in ('I', 'P') and all(s.strip() for s in parts):
                values = [float(s) for s in parts]
                if not all(math.isfinite(v) for v in values) or min(values[1::2]) < 0:
                    raise AuditError('Invalid nutation value or uncertainty')
            else:
                raise AuditError('Partial nutation fields or unknown quality flag')
        except (ValueError, OverflowError) as exc:
            raise AuditError('Invalid finals record') from exc
        out.append(FinalsRow(mjd, flag, values[0], values[2], values[1], values[3]))
    if len(out) < 2:
        raise AuditError('Insufficient daily records')
    return tuple(out)


def load_source(path: Path, expected_sha256: str = SOURCE_SHA256):
    if expected_sha256 != SOURCE_SHA256:
        raise AuditError('Unreviewed source identity; change requires a new research revision')
    try:
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        with os.fdopen(os.open(path, flags), 'rb') as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
                raise AuditError('Source must be a bounded regular file')
            data = f.read(MAX_BYTES + 1)
            if len(data) != info.st_size or hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
                raise AuditError('Source size or SHA mismatch')
        records = parse_finals(data.decode('ascii'))
    except (OSError, UnicodeError) as exc:
        raise AuditError('Source unavailable or unsafe') from exc
    return records, {'url': SOURCE_URL, 'source_sha256': SOURCE_SHA256,
                     'size_bytes': len(data), 'row_count': len(records),
                     'frame': 'IAU1976/1980', 'columns': 'Bulletin A dPsi/dEps only',
                     'unit': 'mas', 'argument': 'MJD(UTC)',
                     'first_mjd_utc': records[0].mjd_utc,
                     'last_mjd_utc': records[-1].mjd_utc,
                     'horizons_snapshot_equivalence': False,
                     'url_is_mutable': True}


def sample(records: tuple[FinalsRow, ...], tt_jd: float) -> dict:
    if type(tt_jd) is not float or not math.isfinite(tt_jd) or not 2430000 < tt_jd < 2470000:
        raise AuditError('Invalid TT')
    if erfa.__version__ != '2.0.1.5':
        raise AuditError('Unreviewed ERFA version')
    # SOFA quasi-JD UTC, not the EOP2 MJD(TAI) formula from PR13.
    tai1, tai2 = erfa.tttai(2451545., tt_jd-2451545.)
    utc1, utc2 = erfa.taiutc(tai1, tai2)
    mjd = float((utc1-2400000.5)+utc2)
    days = [r.mjd_utc for r in records]
    idx = bisect_right(days, mjd)-1
    out = {'mjd_utc': mjd, 'production_authorized': False,
           'interpolation': 'research_linear_MJD_UTC_not_JPL_algorithm'}
    if idx < 0 or idx >= len(records)-1:
        return {**out, 'status': 'unavailable', 'reason': 'outside_source_range'}
    left, right = records[idx:idx+2]
    if right.mjd_utc-left.mjd_utc != 1:
        raise AuditError('Missing daily bracket')
    out['bracket_mjd_utc'] = [left.mjd_utc, right.mjd_utc]
    if left.dpsi_mas is None or right.dpsi_mas is None:
        return {**out, 'status': 'unavailable', 'reason': 'missing_nutation_fields'}
    fraction = mjd-left.mjd_utc
    out.update(status='sampled', nutation_flags=[left.flag, right.flag],
               prediction_in_bracket='P' in (left.flag, right.flag))
    for name in ('dpsi_mas', 'deps_mas'):
        out[name] = (1-fraction)*getattr(left, name)+fraction*getattr(right, name)
    # Preserve endpoint errors, rather than claim independent daily errors
    # or a rigorous uncertainty for an interpolated value.
    out['endpoint_offsets_mas'] = [[r.dpsi_mas, r.deps_mas] for r in (left, right)]
    out['endpoint_sigma_mas'] = [[r.dpsi_sigma_mas, r.deps_sigma_mas] for r in (left, right)]
    return out


def matrix(tt_jd: float, dpsi_mas: float, deps_mas: float) -> np.ndarray:
    """Nutation-corrected alternative under PR12's dynamical-J2000 assumption.

    No ICRF/FK5 frame bias is guessed. Matching obliquity in both rotations
    makes dEps cancel from the ecliptic matrix; this is conditional algebra,
    not evidence of Horizons' implementation or its equinox convention.
    """
    if (type(tt_jd) is not float or not math.isfinite(tt_jd) or not 2430000 < tt_jd < 2470000
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in (dpsi_mas, deps_mas))):
        raise AuditError('Invalid epoch or nutation offsets')
    d1, d2 = 2451545., tt_jd-2451545.
    dp, de = erfa.nut80(d1, d2)
    eps = erfa.obl80(d1, d2)
    dp += dpsi_mas*MAS_TO_RAD
    de += deps_mas*MAS_TO_RAD
    return erfa.rx(eps+de, erfa.numat(eps, dp, de) @ erfa.pmat76(d1, d2))


def audit(rows, records, source, local=None):
    if len(rows) != 20:
        raise AuditError('Expected frozen twenty-case catalogue')
    if local is not None and (len(local) != len(rows) or any(
        (a['year'], a['kasi_term_id']) != (b['year'], b['kasi_term_id'])
        for a, b in zip(rows, local)
    )):
        raise AuditError('Local models do not align with frozen cases')
    samples = []
    for i, row in enumerate(rows):
        s = {**row, **sample(records, row['tt_jd'])}
        if s['status'] == 'sampled' and local is not None:
            raw = local[i]['erfa_uncorrected_1976_1980_deg']
            # Exact ecliptic rotation response established by numat algebra
            # and tested independently with vectors, not fitted to Horizons.
            alt = (raw+s['dpsi_mas']/3_600_000) % 360
            s.update(raw_iau76_80_deg=raw, alternative_iau1980_cpo_deg=alt,
                     alternative_minus_raw_mas=s['dpsi_mas'],
                     horizons_minus_raw_mas=wrap_degrees(row['horizons_obs_ecliptic_lon_deg'], raw)*3_600_000,
                     horizons_minus_alternative_mas=wrap_degrees(row['horizons_obs_ecliptic_lon_deg'], alt)*3_600_000)
        samples.append(s)
    return {'schema_version': 1, 'status': 'diagnostic_only', 'research_only': True,
            'production_authorized': False, 'release_approval': 'BLOCKED',
            'horizons_frame_reproduced': False, 'newly_resolved_case_count': 0,
            'existing_unresolved_case_count': 289, 'source': source,
            'epoch_count': 20, 'sampled_count': sum(s['status']=='sampled' for s in samples),
            'unavailable_count': sum(s['status']=='unavailable' for s in samples),
            'prediction_bracket_count': sum(s.get('prediction_in_bracket', False) for s in samples),
            'numerical_projection_executed': local is not None,
            'precision_limit': 'Frozen Horizons floats lie on a 1e-7 degree grid (0.36 mas); '
                               'raw output tokens and rounding policy were not preserved. '
                               'Residual digits are diagnostics, not physical accuracy bounds.',
            'assumptions': ['PR12 no additional ICRF-to-dynamical-J2000 bias',
                            'IAU1976 precession; IAU1980 nutation plus Bulletin A dPsi/dEps',
                            'same corrected obliquity in nutation and ecliptic projection',
                            'linear daily UTC interpolation; not JPL interpolation'],
            'samples': samples}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eop', type=Path, required=True)
    p.add_argument('--observations', type=Path, required=True)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--kernel', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        records, source = load_source(args.eop)
        rows = load_cases(args.observations, args.references)
        local, kernel_identity = compute_local(rows, args.kernel) if args.kernel else (None, None)
        report = audit(rows, records, source, local)
        report['local_model'] = kernel_identity
        report['environment'] = {'python': platform.python_version(), 'pyerfa': erfa.__version__,
                                 'numpy': np.__version__}
        report['checked_at_utc'] = datetime.now(UTC).isoformat()
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
        print(json.dumps({k: report[k] for k in ('status', 'sampled_count', 'unavailable_count',
              'prediction_bracket_count', 'numerical_projection_executed', 'production_authorized')}))
        return 0
    except (ValueError, OSError, ImportError, TypeError, KeyError) as exc:
        args.output.write_text(json.dumps({'status': 'blocked', 'production_authorized': False,
                                           'error': type(exc).__name__})+'\n')
        print('Research blocked: '+str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
