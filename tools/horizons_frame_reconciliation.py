"""Research-only Skyfield / ERFA / JPL Horizons frame discrimination.

Never interpret bare IAU 1976/1980 calculations as reproducing Horizons:
Horizons applies historically measured Earth orientation pole corrections
(EOP) to that nominal model, which this offline diagnostic DOES NOT have.

No KASI minutes are changed; this script is not an operating saju engine.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import stat
import statistics
import sys

import numpy as np

FROZEN_REPORT_SHA256 = 'd74e7d75a53280f8578f4450130f7646562d53cb6502cb4af8976136e2e4f245'
FROZEN_ROWS_SHA256 = '6ff56fc6f0e0af3d2841ee94508528fb69ee4095c86b6f4274fa317aa79a9dd4'
KERNEL_SHA256 = 'c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2'
FROZEN_PROBE_SHA256 = '5c33bcb86f9ad8aa59a128994860fa52f32883d490c8bce1da1c2a7fdfe1025f'
MAX_FILE_BYTES = 131072


class EvidenceError(ValueError):
    """Research evidence is incomplete, invalid, or nonreproducible."""


def _load_json(path: Path) -> dict:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE_BYTES:
            raise EvidenceError('Source file unsafe, empty, or oversized')
        data = json.loads(path.read_text(encoding='utf-8'), parse_constant=lambda _: None)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise EvidenceError('Cannot read research file') from exc
    if not isinstance(data, dict):
        raise EvidenceError('Research root must be object')
    return data


def _ordered_rows_sha(rows: list) -> str:
    body = json.dumps(rows, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(body).hexdigest()


def load_cases(fixture: Path, references: Path) -> list[dict]:
    data = _load_json(fixture)
    official = _load_json(references)
    if (data.get('schema_version') != 1 or data.get('research_only') is not True
        or data.get('production_authorized') is not False
        or data.get('release_approval') != 'BLOCKED'
        or data.get('source_report_sha256') != FROZEN_REPORT_SHA256
        or data.get('skyfield_kernel_sha256') != KERNEL_SHA256
        or official.get('research_only') is not True
        or official.get('production_authorized') is not False
        or official.get('release_approval') != 'BLOCKED'):
        raise EvidenceError('Research source identity or approval mismatch')
    rows = data.get('rows')
    refs = official.get('cases')
    if not isinstance(rows, list) or not isinstance(refs, list) or len(rows) != 20 or len(refs) != 20:
        raise EvidenceError('Expected exactly twenty cases')
    if _ordered_rows_sha(rows) != FROZEN_ROWS_SHA256:
        raise EvidenceError('Horizons recorded numbers differ from checked artifact')
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise EvidenceError('Invalid numeric case')
        y, idx, jd = row.get('year'), row.get('kasi_term_id'), row.get('tt_jd')
        if (type(y) is not int or not 1960 <= y <= 2026
            or type(idx) is not int or not 1 <= idx <= 24
            or type(jd) is not float or not math.isfinite(jd) or not 2430000 < jd < 2470000):
            raise EvidenceError('Incorrect reference epoch or key')
        for name in ('horizons_obs_ecliptic_lon_deg', 'skyfield_2000b_ecliptic_lon_deg'):
            val = row.get(name)
            if type(val) not in (float, int) or not math.isfinite(val) or not 0 <= val < 360:
                raise EvidenceError('Invalid recorded longitude')
        if (y, idx) in seen:
            raise EvidenceError('Duplicate research event')
        seen.add((y, idx))
    if [r['tt_jd'] for r in rows] != sorted(r['tt_jd'] for r in rows):
        raise EvidenceError('Research events must remain chronological')
    known = []
    for r in refs:
        if (not isinstance(r, dict) or type(r.get('year')) is not int
            or type(r.get('kasi_term_id')) is not int
            or r.get('production_authorized') is not False):
            raise EvidenceError('Invalid reference catalogue row')
        known.append((r['year'], r['kasi_term_id']))
    if len(set(known)) != 20 or set(known) != seen:
        raise EvidenceError('Source catalogues disagree on the cases')
    return rows


def iau1976_1980_ecliptic_matrix(tt_jd: float) -> np.ndarray:
    """Uncorrected ERFA IAU76/80 equinox & ecliptic-of-date matrix.

    This deliberately EXCLUDES measured celestial-pole offsets (dPsi/dEps)
    from Horizons EOP files; do not label its result Horizons matched.
    """
    if not isinstance(tt_jd, (float, np.floating)) or not math.isfinite(tt_jd) or not 2430000 < tt_jd < 2470000:
        raise EvidenceError('Invalid TT julian date')
    import erfa
    d1, d2 = 2451545., tt_jd - 2451545.
    _, deps = erfa.nut80(d1, d2)
    true_obliquity = erfa.obl80(d1, d2) + deps
    # ERFA rx uses passive rotation sign convention; +epsilon is correct.
    return erfa.rx(true_obliquity, erfa.pnm80(d1, d2).copy())


def ecliptic_longitude_deg(matrix, vector) -> float:
    try:
        rot = np.asarray(matrix, dtype=float)
        vec = np.asarray(vector, dtype=float)
    except (TypeError, ValueError):
        raise EvidenceError('Invalid vector or rotation') from None
    if (rot.shape != (3, 3) or vec.shape != (3,) or not np.isfinite(rot).all()
        or not np.isfinite(vec).all() or np.linalg.norm(vec) == 0):
        raise EvidenceError('Invalid vector size or nonfinite data')
    x, y, _ = rot @ vec
    return (math.degrees(math.atan2(float(y), float(x))) + 360.) % 360.


def wrap_degrees(value: float, base: float) -> float:
    if any(type(z) not in (float, int) or not math.isfinite(z) for z in (value, base)):
        raise EvidenceError('Invalid angle')
    return (value - base + 180.0) % 360.0 - 180.0


def _verify_kernel(path: Path) -> None:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 67108864:
            raise EvidenceError('JPL kernel is not a bounded regular file')
        # Prevent symlink use; the hash is the published version identity.
        with path.open('rb') as f:
            identity = hashlib.file_digest(f, 'sha256').hexdigest()
    except OSError as err:
        raise EvidenceError('Local JPL kernel missing') from err
    if identity != KERNEL_SHA256:
        raise EvidenceError('JPL kernel digest mismatch')


def compute_local(rows: list[dict], kernel: Path) -> tuple[list[dict], dict]:
    """All frames consume one apparent ICRF photon direction at each TT."""
    _verify_kernel(kernel)
    import erfa
    from skyfield.api import Loader, load_file
    from skyfield.framelib import ecliptic_frame
    from skyfield.nutationlib import iau2000a_radians, iau2000b_radians
    from skyfield import __version__ as sf_version
    if sf_version != '1.55' or erfa.__version__ != '2.0.1.5':
        raise EvidenceError('Unreviewed astronomy implementation version')
    ts = Loader(str(kernel.parent)).timescale(builtin=True)
    out = []
    with closing(load_file(str(kernel))) as eph:
        earth, sun = eph['earth'], eph['sun']
        for row in rows:
            t_b = ts.tt_jd(row['tt_jd'])
            t_b._nutation_angles_radians = iau2000b_radians(t_b)
            icrf = earth.at(t_b).observe(sun).apparent().xyz.au
            modern_b = ecliptic_longitude_deg(ecliptic_frame.rotation_at(t_b), icrf)
            t_a = ts.tt_jd(row['tt_jd'])
            t_a._nutation_angles_radians = iau2000a_radians(t_a)
            modern_a = ecliptic_longitude_deg(ecliptic_frame.rotation_at(t_a), icrf)
            old = ecliptic_longitude_deg(iau1976_1980_ecliptic_matrix(row['tt_jd']), icrf)
            if abs(wrap_degrees(modern_b, row['skyfield_2000b_ecliptic_lon_deg'])) * 3600 > 0.002:
                raise EvidenceError('Original frozen Skyfield results not reproducible')
            out.append({'year': row['year'], 'kasi_term_id': row['kasi_term_id'],
                        'skyfield_2000b_deg': modern_b, 'skyfield_2000a_deg': modern_a,
                        'erfa_uncorrected_1976_1980_deg': old})
    return out, {'kernel_sha256': KERNEL_SHA256, 'skyfield_version': sf_version,
                 'pyerfa_version': erfa.__version__, 'model': 'unadjusted-iau1976-1980',
                 'horizons_eop_corrections_included': False}


def summarize(rows: list[dict], measured: list[dict], source: dict) -> dict:
    if not rows or len(rows) != len(measured):
        raise EvidenceError('Incomplete cases')
    samples = []
    for row, s in zip(rows, measured):
        if (row['year'], row['kasi_term_id']) != (s['year'], s['kasi_term_id']):
            raise EvidenceError('TT epochs and projections do not align')
        horizon = row['horizons_obs_ecliptic_lon_deg']
        old = s['erfa_uncorrected_1976_1980_deg']
        new = s['skyfield_2000b_deg']
        a = s['skyfield_2000a_deg']
        samples.append({'year': row['year'], 'kasi_term_id': row['kasi_term_id'],
                        'horizons_minus_skyfield_2000b_arcsec': round(wrap_degrees(horizon, new) * 3600, 6),
                        'horizons_minus_raw_1976_1980_arcsec': round(wrap_degrees(horizon, old) * 3600, 6),
                        'raw_1976_1980_minus_skyfield_2000b_arcsec': round(wrap_degrees(old, new) * 3600, 6),
                        'skyfield_2000a_minus_2000b_arcsec': round(wrap_degrees(a, new) * 3600, 6),
                        'physical_tt_error_proved': False, 'production_authorized': False})
    def measure(column):
        vals = [r[column] for r in samples]
        return {'min': min(vals), 'median': statistics.median(vals), 'max': max(vals)}
    return {'schema_version': 1, 'status': 'diagnostic_only', 'research_only': True,
            'production_authorized': False, 'release_approval': 'BLOCKED',
            'horizons_frame_includes_eop': True, 'erfa_1976_1980_is_horizons_matched': False,
            'eop_corrections_applied': False, 'sample_count': len(samples),
            'interpretation': 'Skyfield IAU2000B/2000A compared with bare ERFA IAU76/80; '
                              'Horizons uses EOP-corrected IAU76/80, which is not recreated here.',
            'statistics_arcsec': {
                'horizons_minus_raw_1976_1980': measure('horizons_minus_raw_1976_1980_arcsec'),
                'horizons_minus_skyfield_2000b': measure('horizons_minus_skyfield_2000b_arcsec'),
                'raw_1976_1980_minus_skyfield_2000b': measure('raw_1976_1980_minus_skyfield_2000b_arcsec'),
                'skyfield_2000a_minus_2000b': measure('skyfield_2000a_minus_2000b_arcsec')},
            'source': source, 'samples': samples}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        rows = load_cases(args.observations, args.references)
        local, identity = compute_local(rows, args.kernel)
        identity['recorded_horizons_report_sha256'] = FROZEN_REPORT_SHA256
        report = summarize(rows, local, identity)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                               encoding='utf-8')
        print(json.dumps({'status': report['status'], 'samples': len(report['samples']),
                          'production_authorized': False}))
        return 0
    except (EvidenceError, ImportError, OSError, TypeError, ValueError) as err:
        args.output.write_text(json.dumps({'status': 'blocked', 'production_authorized': False,
                                           'error': type(err).__name__}, ensure_ascii=False) + '\n')
        print(json.dumps({'status': 'blocked', 'production_authorized': False,
                          'error': type(err).__name__}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
