"""Clock experiments must not silently redefine the production model."""
from datetime import timedelta
from dataclasses import replace
import math

import pytest

from sazu.errors import SazuError
from sazu.serde import digest
from tests.test_term_audit import comparison_inputs


def test_utc_baseline_preserved_while_a_separate_hypothesis_is_compared():
    from tools.diagnose_term_clocks import diagnose_clocks
    doc, events = comparison_inputs()
    events[0] = replace(events[0], instant_utc=events[0].instant_utc-timedelta(seconds=40))
    original = digest(events)
    report = diagnose_clocks(events, doc, 1993, 1993, lambda e: 20.0)
    assert report['baseline']['matched'] == 23
    assert report['ut1_display_hypothesis']['matched'] == 24
    assert report['changed_keys'] == [[1993, 23]]
    assert report['adopted'] is False and report['production_authorized'] is False
    assert report['baseline_candidate_sha256'] == original == digest(events)
    assert report['reference_clock_claim'] == 'fixed-UTC+9'
    assert report['diagnosis_status'] == 'hypothesis_only_not_reference_clock_confirmation'


def test_hypothesis_can_worsen_not_only_improve_counts():
    from tools.diagnose_term_clocks import diagnose_clocks
    doc, events = comparison_inputs()
    report = diagnose_clocks(events, doc, 1993, 1993, lambda e: 40.0)
    assert report['baseline']['matched'] == 24
    assert report['ut1_display_hypothesis']['matched'] == 0
    assert report['ut1_display_hypothesis']['mismatched'] == 24


@pytest.mark.parametrize('shift', [math.nan, math.inf, -math.inf, True, '20', None])
def test_nonfinite_or_non_numeric_clock_shifts_rejected(shift):
    from tools.diagnose_term_clocks import diagnose_clocks
    doc, events = comparison_inputs()
    with pytest.raises(SazuError):
        diagnose_clocks(events, doc, 1993, 1993, lambda e: shift)


def test_incomplete_candidates_do_not_create_partial_success():
    from tools.diagnose_term_clocks import diagnose_clocks
    doc, events = comparison_inputs()
    with pytest.raises(SazuError):
        diagnose_clocks(events[1:], doc, 1993, 1993, lambda e: 0.0)


def test_interval_counts_are_exhaustive_and_disjoint():
    from tools.diagnose_term_clocks import diagnose_clocks
    doc, events = comparison_inputs(1971, 1972)
    r = diagnose_clocks(events, doc, 1971, 1972, lambda e: 0.0)
    assert [(s['period'],s['total']) for s in r['periods']] == [('before_1972',24),('1972_through_2025',24)]
    assert sum(s['total'] for s in r['periods']) == 48
    assert r['changed_keys'] == []
