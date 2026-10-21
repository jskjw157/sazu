"""Research-only UTC versus UT1-display experiment. Never modifies the engine.

The official header says UTC+9. Better agreement under UT1 would NOT establish
that KASI uses UT1, nor authorize replacing the model's UTC conversion.
"""
import argparse
from datetime import datetime, timedelta
import math
from pathlib import Path

from sazu.cli import _manifest
from sazu.errors import require
from sazu.kasi_reference import parse_kasi_document, reference_events
from sazu.serde import canonical_json, digest
from sazu.solar_terms import compare_reference, generate_terms, validate_annual_terms
from sazu.source_audit import read_reference_bytes
from tools.audit_official_terms import build_request


def diagnose_clocks(candidate, document, first: int, last: int, offset_seconds) -> dict:
    reference = reference_events(document, first, last)
    require(type(candidate) in (list, tuple) and len(candidate) == len(reference))
    ordered = []
    for year in range(first, last+1):
        ordered.extend(validate_annual_terms([e for e in candidate if e.event_year == year], year))
    require(all(e.precision == 'computed' for e in ordered))
    require(len({(e.source_id, e.source_sha256, e.model_id) for e in ordered}) == 1)
    periods = {}
    changed = []
    for ref, value in zip(reference, ordered):
        require((ref.event_year, ref.kasi_id) == (value.event_year, value.kasi_id))
        shift = offset_seconds(value)
        require(type(shift) in (float, int) and math.isfinite(shift) and abs(shift) <= 3600)
        baseline = compare_reference(ref, value.instant_utc) == 'match'
        # A display hypothesis only: this adjusted value is never emitted as UTC.
        hypothesis = compare_reference(ref, value.instant_utc+timedelta(seconds=shift)) == 'match'
        period = ('before_1972' if value.event_year < 1972 else
                  '1972_through_2025' if value.event_year <= 2025 else '2026_through_2050')
        bucket = periods.setdefault(period, {'period': period, 'total': 0,
            'baseline_matched': 0, 'ut1_hypothesis_matched': 0,
            'minimum_dut1_seconds': shift, 'maximum_dut1_seconds': shift})
        bucket['total'] += 1
        bucket['baseline_matched'] += baseline
        bucket['ut1_hypothesis_matched'] += hypothesis
        bucket['minimum_dut1_seconds'] = min(bucket['minimum_dut1_seconds'], shift)
        bucket['maximum_dut1_seconds'] = max(bucket['maximum_dut1_seconds'], shift)
        if baseline != hypothesis:
            changed.append([value.event_year, value.kasi_id])
    total = len(ordered)
    baseline = sum(p['baseline_matched'] for p in periods.values())
    hypothesis = sum(p['ut1_hypothesis_matched'] for p in periods.values())
    return {'diagnosis_status': 'hypothesis_only_not_reference_clock_confirmation',
        'reference_clock_claim': document.manifest.clock,
        'adopted': False, 'production_authorized': False,
        'reference_sha256': document.manifest.sha256,
        'baseline_candidate_sha256': digest(candidate),
        'baseline': {'total': total, 'matched': baseline, 'mismatched': total-baseline},
        'ut1_display_hypothesis': {'total': total, 'matched': hypothesis, 'mismatched': total-hypothesis},
        'periods': list(periods.values()), 'changed_keys': sorted(changed),
        'note': 'No fitted correction, tolerance relaxation, reference edits or operational model changes.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kasi', type=Path, required=True)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--acquired-at', required=True)
    args = parser.parse_args()
    request = build_request(args.kasi, args.kernel, datetime.fromisoformat(args.acquired_at), 1920, 2050)
    manifest = _manifest(request['reference_manifest'])
    reference = parse_kasi_document(read_reference_bytes(args.kasi, manifest), manifest)
    candidates = []
    for year in range(1920, 2051):
        candidates.extend(generate_terms(year, args.kernel, _manifest(request['kernel_manifest'])))
    from skyfield.api import load
    ts = load.timescale(builtin=True)
    report = diagnose_clocks(candidates, reference, 1920, 2050,
                             lambda event: float(ts.tt_jd(event.tt_jd).dut1))
    report['experiment_model'] = 'Skyfield builtin DUT1 at the same computed TT event'
    report['limitations'] = ['UT1 is not UTC.', 'Source clock interpretation remains unconfirmed.',
                            'This diagnostic cannot authorize a production release.']
    print(canonical_json(report))


if __name__ == '__main__':
    main()
