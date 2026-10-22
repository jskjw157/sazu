"""Synthetic policy fixtures; not independent physical ephemeris verification."""
from dataclasses import replace
from datetime import timedelta
import importlib.util

import erfa
import pytest

from sazu.errors import SazuError
from sazu.serde import digest
from tests.test_term_audit import comparison_inputs


def candidates(year=1993, *, shift=0.0, legacy_shift=0.0):
    document, values = comparison_inputs(year, year)
    result = []
    for value in values:
        instant = value.instant_utc + timedelta(seconds=shift)
        u1, u2 = erfa.dtf2d('UTC', instant.year, instant.month, instant.day,
                           instant.hour, instant.minute,
                           instant.second + instant.microsecond/1e6)
        a1, a2 = erfa.utctai(u1, u2)
        t1, t2 = erfa.taitt(a1, a2)
        result.append(replace(value, tt_jd=float(t1+t2),
                              instant_utc=instant+timedelta(seconds=legacy_shift)))
    return document, result


def reviewed(values, doc, first=1993, last=1993):
    spec = importlib.util.find_spec('sazu.reviewed_term_audit')
    assert spec is not None, 'Reviewed-clock audit is missing from the official comparison path'
    from sazu.reviewed_term_audit import compare_reviewed_term_range
    return compare_reviewed_term_range(values, doc, first, last)


def test_official_command_must_use_the_reviewed_clock(tmp_path, monkeypatch):
    import sazu.source_audit as module
    from tests.test_source_audit import request
    payload = request(tmp_path)
    _, values = candidates()
    monkeypatch.setattr(module, 'generate_terms', lambda *args: tuple(values))
    report = module.execute_audit('compare', payload)
    assert report['clock_projection'] == 'erfa-historical-utc-v2-c72'
    assert report['matched'] == 24 and report['status'] == 'passed'
    assert report['production_authorized'] is False


def test_reviewed_clock_fixes_a_legacy_historical_disagreement_without_fitting():
    doc, values = candidates(1965, shift=-25, legacy_shift=-7)
    report = reviewed(values, doc, 1965, 1965)
    assert report['matched'] == 24 and report['status'] == 'passed'
    assert len(report['legacy_comparison']['mismatches']) == 24
    assert len(report['resolved_legacy_mismatch_keys']) == 24
    assert report['unresolved_legacy_mismatch_keys'] == []
    assert report['production_authorized'] is False


def test_modern_pass_and_digest_are_deterministic():
    doc, values = candidates()
    report = reviewed(values, doc)
    assert report == reviewed(list(reversed(values)), doc)
    assert report['matched'] == 24 and report['comparable_count'] == 24
    assert report['unresolved_count'] == 0
    assert report['report_sha256'] == digest({k:v for k,v in report.items()
                                            if k != 'report_sha256'})
    assert report['reference']['rights_status'] == 'unreviewed'
    assert report['comparison_policy'] == 'nearest-minute-half-up-v1'
    assert report['physical_source_independence'] == 'not_established'


def test_pre_1960_legacy_agreement_is_not_verified_utc():
    doc, values = comparison_inputs(1950, 1950)
    # Use a plausible TT label without inventing historical UTC.
    values = [replace(v, tt_jd=float(v.instant_utc.timestamp()/86400+2440587.5))
              for v in values]
    report = reviewed(values, doc, 1950, 1950)
    assert report['legacy_comparison']['matched'] == 24
    assert report['status'] == 'blocked' and report['matched'] == 0
    assert report['unresolved_count'] == 24 and report['comparable_count'] == 0
    assert {r['reason'] for r in report['unresolved']} == {'historical_clock_unresolved'}


def test_future_numbers_are_diagnostic_only_even_when_they_match():
    doc, values = candidates(2027)
    report = reviewed(values, doc, 2027, 2027)
    assert report['status'] == 'blocked' and report['matched'] == 0
    assert report['unresolved_count'] == 24
    assert report['provisional']['matched'] == 24
    assert report['provisional']['mismatches'] == []
    assert report['production_authorized'] is False


def test_unresolved_legacy_failures_never_count_as_resolved():
    doc, values = candidates(2027, shift=0, legacy_shift=-31)
    report = reviewed(values, doc, 2027, 2027)
    assert report['resolved_legacy_mismatch_keys'] == []
    assert len(report['unresolved_legacy_mismatch_keys']) == 24
    assert report['status'] == 'blocked'


@pytest.mark.parametrize('seconds,expected', [(-30.001,'failed'),(-29.999,'passed'),
                                              (29.999,'passed'),(30.001,'failed')])
def test_minute_cell_is_not_widened(seconds, expected):
    doc, values = candidates(shift=seconds)
    report = reviewed(values, doc)
    assert report['status'] == expected
    assert report['matched'] == (24 if expected == 'passed' else 0)
    assert len(report['mismatches']) == (24 if expected == 'failed' else 0)


def test_missing_duplicate_extra_cannot_pass():
    doc, values = candidates()
    _, other = candidates(1994)
    report = reviewed(values[1:]+[values[1], other[0]], doc)
    assert report['status'] == 'failed'
    assert report['missing_candidate_keys'] == [[1993,23]]
    assert report['duplicate_candidate_keys'] == [[1993,24]]
    assert report['extra_candidate_keys'] == [[1994,23]]
    assert report['matched'] == 0  # Invalid structure is rejected before projections.


def test_empty_never_passes():
    doc, _ = candidates()
    report = reviewed([], doc)
    assert report['status'] == 'failed' and report['matched'] == 0
    assert len(report['missing_candidate_keys']) == 24


@pytest.mark.parametrize('field,value',[('source_id','other'),('source_sha256','e'*64),
                                        ('model_id','e'*64)])
def test_mixed_models_still_block(field, value):
    doc, values = candidates()
    values[0] = replace(values[0], **{field:value})
    report = reviewed(values, doc)
    assert report['status'] == 'blocked'
    assert 'MIXED_CANDIDATE_IDENTITIES' in report['blockers']


def test_reference_cannot_be_its_own_candidate():
    doc, values = candidates()
    values = [replace(v, source_sha256=doc.manifest.sha256) for v in values]
    assert reviewed(values, doc)['status'] == 'blocked'


def test_wrong_tt_order_is_not_silently_accepted():
    doc, values = candidates()
    values[0] = replace(values[0], tt_jd=values[1].tt_jd+1.0)
    report = reviewed(values, doc)
    assert report['status'] == 'failed'
    assert report['invalid_tt_structure'] == [1993]


def test_a_known_mismatch_is_not_masked_by_other_unresolved_years():
    from tests.test_kasi_reference import parse, document_bytes
    doc = parse(document_bytes(2026,2027),2026,2027)
    _, a = candidates(2026,shift=-31)
    _, b = candidates(2027)
    report = reviewed(a+b,doc,2026,2027)
    assert report['status'] == 'failed'
    assert report['mismatches'] and report['unresolved_count'] > 0
    assert report['matched']+len(report['mismatches'])+report['unresolved_count'] == 48


def test_clock_projection_failure_is_not_silently_skipped(monkeypatch):
    doc, values = candidates()
    assert importlib.util.find_spec('sazu.reviewed_term_audit') is not None
    import sazu.reviewed_term_audit as module
    def fail(*args):
        raise SazuError('SOURCE_CONFLICT')
    monkeypatch.setattr(module,'project_computed_term',fail)
    with pytest.raises(SazuError):
        reviewed(values,doc)


def test_tool_records_clock_and_projection_code_provenance():
    from pathlib import Path
    tool=(Path(__file__).resolve().parents[1]/'tools/audit_official_terms.py').read_text()
    assert 'src/sazu/term_clock.py' in tool
    assert 'src/sazu/reviewed_term_audit.py' in tool
    assert "'pyerfa'" in tool


def test_ci_summary_must_not_hide_unresolved_or_conditional_rows(tmp_path):
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys
    import yaml
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root/'.github/workflows/official-validation.yml').read_text())
    steps = workflow['jobs']['reference-comparison']['steps']
    command = next(s['run'] for s in steps if s.get('name') == 'Numerical result summary')
    code = command.split("python - <<'PY'\n",1)[1].rsplit('\nPY',1)[0]
    fake = {'status':'failed','reference_comparison': {
        'clock_projection':'erfa-historical-utc-v1', 'matched':1559, 'expected':3144,
        'comparable_count':1579, 'mismatches':[{}]*20, 'unresolved_count':1565,
        'provisional':{'mismatches':[{}]*12},
        'legacy_comparison':{'mismatches':[{}]*314},
        'resolved_legacy_mismatch_keys':[[1965,1]]*20,
        'unresolved_legacy_mismatch_keys':[[1950,1]]*294}}
    (tmp_path/'official-audit.json').write_text(json.dumps(fake))
    process = subprocess.run([sys.executable,'-c',code],text=True,capture_output=True,
        env={**os.environ,'RUNNER_TEMP':str(tmp_path)},check=True)
    summary = json.loads(process.stdout)
    assert summary['unresolved_count'] == 1565
    assert summary['provisional_mismatch_count'] == 12
    assert summary['legacy_mismatch_count'] == 314
    assert summary['resolved_legacy_mismatch_count'] == 20
    assert summary['remaining_legacy_mismatch_count'] == 294
    assert summary['status']=='failed' and summary['production_authorized'] is False


@pytest.mark.parametrize('year', [1960,2026])
def test_current_evidence_is_used_for_all_synthetic_terms_in_supported_years(year):
    doc, values = candidates(year)
    report = reviewed(values,doc,year,year)
    assert report['matched'] == 24
    assert report['unresolved_count'] == 0
    assert report['status'] == 'passed'
    assert report['production_authorized'] is False
    assert report['clock_evidence']['utc_offset_confirmed_through'].isoformat() == '2026-12-31'
    assert report['clock_model_ids'] == [digest(report['clock_evidence'])]
