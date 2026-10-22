"""Audit the reviewed clock, retaining the legacy audit as immutable evidence.

Numerical agreement, clock eligibility, reference provenance, and operational
approval are distinct. An unresolved or future clock never contributes to matched.
"""
from collections import Counter

from .errors import require
from .kasi_reference import KasiDocument, reference_events
from .serde import digest
from .solar_terms import FIXED_KST, compare_reference
from .term_audit import compare_term_range
from .term_clock import POLICY, project_computed_term, clock_identity


_STRUCTURE_FIELDS = ('missing_candidate_keys', 'extra_candidate_keys',
                     'duplicate_candidate_keys', 'invalid_annual_structure')


def _finish(report: dict) -> dict:
    report['report_sha256'] = digest(report)
    return report


def compare_reviewed_term_range(candidate, document: KasiDocument,
                                start_year: int, end_year: int) -> dict:
    """Apply the current TT→UTC policy to every key, without editing geometry.

    The existing comparator remains responsible for input, identity, source and
    annual-coverage checks. Its numeric result is retained, not used as the new
    verdict. A bad source or incomplete set is rejected before clock projection.
    """
    legacy = compare_term_range(candidate, document, start_year, end_year)
    report = {k: v for k, v in legacy.items() if k not in (
        'report_sha256', 'matched', 'mismatches', 'by_year')}
    report.update({
        'schema_version': 2, 'status': 'blocked', 'clock_projection': POLICY,
        'evidence_level': 'published_reference_reviewed_clock_comparison',
        'legacy_comparison': legacy,
        'matched': 0, 'mismatches': [], 'by_year': [], 'comparable_count': 0,
        'unresolved': [], 'unresolved_count': 0,
        'provisional': {'matched': 0, 'mismatches': []},
        'clock_status_counts': {}, 'projection_sha256': None,
        'clock_model_ids': [], 'clock_evidence': clock_identity(),
        'invalid_tt_structure': [],
        'invalid_clock_keys': [],
        'resolved_legacy_mismatch_keys': [],
        'unresolved_legacy_mismatch_keys': [
            [r['year'], r['kasi_id']] for r in legacy['mismatches']],
        'new_mismatch_keys': [],
    })
    if legacy['blockers']:
        return _finish(report)
    if any(legacy[key] for key in _STRUCTURE_FIELDS):
        report['status'] = 'failed'
        return _finish(report)
    for year in range(start_year, end_year+1):
        annual = sorted((e for e in candidate if e.event_year == year),
                        key=lambda e: e.tt_jd)
        if [e.kasi_id for e in annual] != [23, 24, *range(1, 23)] or any(
                a.tt_jd >= b.tt_jd for a, b in zip(annual, annual[1:])):
            report['invalid_tt_structure'].append(year)
    if report['invalid_tt_structure']:
        report['status'] = 'failed'
        return _finish(report)

    ordered = sorted(candidate, key=lambda e: (e.event_year, e.kasi_id))
    projected = tuple(project_computed_term(e) for e in ordered)
    report['projection_sha256'] = digest(projected)
    report['clock_model_ids'] = sorted({e.clock.clock_model_id for e in projected})
    require(report['clock_model_ids'] == [digest(report['clock_evidence'])], 'SOURCE_CONFLICT')
    report['clock_status_counts'] = dict(sorted(Counter(
        e.clock.status for e in projected).items()))
    references = {(e.event_year, e.kasi_id): e for e in
                  reference_events(document, start_year, end_year)}
    known_matches = set()
    for year in range(start_year, end_year+1):
        matched, mismatched, unresolved = 0, 0, 0
        for event in (e for e in projected if e.event_year == year):
            key = (event.event_year, event.kasi_id)
            reference = references[key]
            clock = event.clock
            if not clock.comparable_as_utc:
                unresolved += 1
                report['unresolved'].append({
                    'year': year, 'kasi_id': key[1], 'name': event.name,
                    'reason': clock.status, 'erfa_status': clock.erfa_status,
                })
                # Only diagnostic numbers. Never used by matched or status=passed.
                if clock.status == 'future_utc_assumption' and clock.instant_utc is not None:
                    delta = (clock.instant_utc-reference.instant_utc).total_seconds()
                    if compare_reference(reference, clock.instant_utc) == 'match':
                        report['provisional']['matched'] += 1
                    else:
                        report['provisional']['mismatches'].append({
                            'year': year, 'kasi_id': key[1], 'name': event.name,
                            'delta_seconds_from_display': delta})
                continue
            require(clock.instant_utc is not None
                    and clock.status in ('historical_utc', 'modern_utc')
                    and clock.erfa_status == 0
                    and clock.instant_utc.date() <= min(clock.reviewed_through,
                                                       clock.utc_offset_confirmed_through),
                    'DATA_INTEGRITY_FAILED')
            if clock.instant_utc.astimezone(FIXED_KST).year != year:
                report['invalid_clock_keys'].append(list(key))
                continue
            if compare_reference(reference, clock.instant_utc) == 'match':
                matched += 1
                known_matches.add(key)
            else:
                mismatched += 1
                report['mismatches'].append({
                    'year': year, 'kasi_id': key[1], 'name': event.name,
                    'delta_seconds_from_display': (
                        clock.instant_utc-reference.instant_utc).total_seconds()})
        report['matched'] += matched
        report['comparable_count'] += matched+mismatched
        report['unresolved_count'] += unresolved
        report['by_year'].append({'year': year, 'matched': matched,
                                 'mismatched': mismatched, 'unresolved': unresolved})
    old_bad = {(r['year'], r['kasi_id']) for r in legacy['mismatches']}
    new_bad = {(r['year'], r['kasi_id']) for r in report['mismatches']}
    report['resolved_legacy_mismatch_keys'] = [list(k) for k in sorted(old_bad & known_matches)]
    report['unresolved_legacy_mismatch_keys'] = [list(k) for k in sorted(old_bad-known_matches)]
    report['new_mismatch_keys'] = [list(k) for k in sorted(new_bad-old_bad)]
    require(report['comparable_count']+report['unresolved_count']+
            len(report['invalid_clock_keys']) == report['expected'], 'DATA_INTEGRITY_FAILED')
    if report['mismatches'] or report['invalid_clock_keys']:
        report['status'] = 'failed'
    elif report['unresolved_count']:
        report['status'] = 'blocked'
    else:
        report['status'] = 'passed'
    return _finish(report)
