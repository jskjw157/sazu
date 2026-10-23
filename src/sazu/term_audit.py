"""Deterministic numerical evidence, deliberately separate from release approval."""
from collections import Counter

from .contracts import strict_int
from .errors import SazuError, require
from .kasi_reference import KasiDocument, reference_events
from .serde import canonical_json, digest
from .solar_terms import SolarTermEvent, compare_reference, validate_annual_terms


def reference_summary(document: KasiDocument) -> dict:
    require(type(document) is KasiDocument)
    m = document.manifest
    return {'source_id': m.source_id, 'url': m.url, 'version': m.version,
            'sha256': m.sha256, 'size_bytes': m.size_bytes,
            'acquired_at': m.acquired_at, 'clock': m.clock, 'precision': m.precision,
            'parser_version': m.parser_version, 'header_sha256': document.header_sha256,
            'encoding': document.encoding, 'source_coverage': [document.start_year, document.end_year],
            'row_count': len(document.rows), 'rights_status': m.rights_status,
            'rights_url': m.rights_url, 'lineage': m.lineage,
            'identity_assurance': 'manifest_assertion_not_provider_signature'}


def compare_term_range(candidate, document: KasiDocument, start_year: int, end_year: int) -> dict:
    """Compare every requested key. Never turn subset agreement into full coverage.

    ``passed`` means numerical minute-cell agreement only; KASI ephemeris ancestry
    has not been established and matching results never activate a release.
    """
    require(type(document) is KasiDocument)
    require(type(candidate) in (tuple, list) and len(candidate) <= 10000)
    require(all(type(event) is SolarTermEvent for event in candidate))
    require(strict_int(start_year, 1919, 2051) and strict_int(end_year, 1919, 2051)
            and start_year <= end_year, 'UNSUPPORTED_RANGE')
    ordered = sorted(candidate, key=lambda e: (e.event_year, e.kasi_id, canonical_json(e)))
    expected_keys = {(y, i) for y in range(start_year, end_year+1) for i in range(1, 25)}
    counts = Counter((e.event_year, e.kasi_id) for e in ordered)
    report = {'schema_version': 2, 'status': 'blocked', 'production_authorized': False,
              'evidence_level': 'published_reference_numerical_comparison',
              'physical_source_independence': 'not_established',
              'comparison_policy': 'nearest-minute-half-up-v1',
              'requested_years': [start_year, end_year], 'expected': len(expected_keys),
              'candidate_count': len(ordered), 'candidate_sha256': digest(ordered),
              'reference': reference_summary(document), 'candidate_identities': [],
              'matched': 0, 'mismatches': [], 'by_year': [],
              'unresolved_clock_keys': [], 'provisional_clock_keys': [],
              'missing_candidate_keys': [list(k) for k in sorted(expected_keys-counts.keys())],
              'extra_candidate_keys': [list(k) for k in sorted(counts.keys()-expected_keys)],
              'duplicate_candidate_keys': [list(k) for k in sorted(k for k,n in counts.items() if n > 1)],
              'invalid_annual_structure': [], 'blockers': []}
    identities = {(e.source_id, e.source_sha256, e.model_id) for e in ordered}
    report['candidate_identities'] = [dict(source_id=i[0], source_sha256=i[1], model_id=i[2])
                                      for i in sorted(identities, key=str)]
    if not document.start_year <= start_year <= end_year <= document.end_year:
        report['blockers'].append('REFERENCE_COVERAGE_UNAVAILABLE')
    if any(e.precision != 'computed' for e in ordered):
        report['blockers'].append('COMPUTED_CANDIDATE_REQUIRED')
    if len(identities) > 1:
        report['blockers'].append('MIXED_CANDIDATE_IDENTITIES')
    if any(e.source_sha256 == document.manifest.sha256 for e in ordered):
        report['blockers'].append('REFERENCE_SOURCE_REUSED')
    if report['blockers']:
        return _finish(report)
    references = {(e.event_year, e.kasi_id): e
                  for e in reference_events(document, start_year, end_year)}
    unique = {(e.event_year, e.kasi_id): e for e in ordered
              if counts[(e.event_year, e.kasi_id)] == 1}
    for year in range(start_year, end_year+1):
        yearly = [e for e in ordered if e.event_year == year]
        try:
            validate_annual_terms(yearly, year)
        except SazuError:
            report['invalid_annual_structure'].append(year)
        matched, mismatched = 0, 0
        for key in sorted(k for k in references if k[0] == year):
            if key not in unique:
                continue
            ref, computed = references[key], unique[key]
            if computed.instant_utc is None or computed.event_year < 1960:
                report['unresolved_clock_keys'].append(list(key))
                continue
            if (computed.utc_projection is not None
                    and computed.utc_projection.status == 'utc_future_assumption'):
                report['provisional_clock_keys'].append(list(key))
            if compare_reference(ref, computed.instant_utc) == 'match':
                matched += 1
            else:
                mismatched += 1
                report['mismatches'].append({
                    'year': year, 'kasi_id': key[1], 'name': ref.name,
                    'delta_seconds_from_display': (computed.instant_utc-ref.instant_utc).total_seconds()})
        report['matched'] += matched
        report['by_year'].append({'year': year, 'matched': matched, 'mismatched': mismatched})
    errors = ('missing_candidate_keys', 'extra_candidate_keys', 'duplicate_candidate_keys',
              'invalid_annual_structure', 'mismatches')
    if report['unresolved_clock_keys']:
        report['blockers'].append('REFERENCE_CLOCK_UNRESOLVED_BEFORE_1960_OR_LEAP_SECOND')
    report['status'] = ('failed' if any(report[k] for k in errors) else
                        'blocked' if report['blockers'] else 'passed')
    report['numerically_compared'] = report['matched']+len(report['mismatches'])
    return _finish(report)


def _finish(report):
    report['report_sha256'] = digest(report)
    return report
