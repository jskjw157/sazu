"""Evidence comparison. Agreement is not equivalent to source independence."""
from datetime import date, timedelta
from .calendar import CalendarInput, CalendarDate, TARGET_START, TARGET_END, convert_calendar
from .contracts import valid_id
from .errors import require
from .serde import digest


def build_calendar_rows(start: date, end: date):
    require(type(start) is date and type(end) is date and TARGET_START <= start <= end <= TARGET_END)
    current = start
    while current <= end:
        yield convert_calendar(CalendarInput('gregorian', current.year, current.month, current.day)).candidates[0]
        current += timedelta(days=1)


def compare_calendar_records(candidate, reference, candidate_lineage, reference_lineage):
    candidate = tuple(candidate)
    require(all(type(row) is CalendarDate for row in candidate))
    require(type(candidate_lineage) is tuple and all(valid_id(x) for x in candidate_lineage))
    require(type(reference_lineage) is tuple and all(valid_id(x) for x in reference_lineage))
    report = {'status': 'blocked', 'independent': False, 'matched': 0,
              'evidence_level': 'insufficient_independent_evidence',
              'candidate_sha256': digest(candidate), 'reference_sha256': None,
              'missing': [], 'extra': [], 'mismatched': [], 'duplicate': []}
    if reference is None:
        return report
    reference = tuple(reference)
    require(all(type(row) is CalendarDate for row in reference))
    report['reference_sha256'] = digest(reference)
    if not candidate or not reference or not candidate_lineage or not reference_lineage:
        return report
    if set(candidate_lineage) & set(reference_lineage):
        report['evidence_level'] = 'shared_lineage_not_independent'
        return report
    report['independent'] = True  # Conditional on the supplied, audited lineage labels.
    report['evidence_level'] = 'independent_reference_candidate_not_release_approval'
    a, b = {}, {}
    for label, records, index in [('candidate', candidate, a), ('reference', reference, b)]:
        for row in records:
            if row.solar in index:
                report['duplicate'].append({'side': label, 'date': row.solar.isoformat()})
            index[row.solar] = row
    report['missing'] = [d.isoformat() for d in sorted(a.keys()-b.keys())]
    report['extra'] = [d.isoformat() for d in sorted(b.keys()-a.keys())]
    report['mismatched'] = [d.isoformat() for d in sorted(a.keys() & b.keys()) if a[d] != b[d]]
    report['matched'] = sum(a[d] == b[d] for d in a.keys() & b.keys())
    report['status'] = 'failed' if any(report[k] for k in ('missing', 'extra', 'mismatched', 'duplicate')) else 'passed'
    return report
