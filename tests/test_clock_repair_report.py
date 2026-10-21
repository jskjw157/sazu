"""Regression report classifications must never turn missing clocks into matches."""
from datetime import UTC, datetime
import importlib
import json

from skyfield.api import load
import pytest

from sazu.errors import SazuError
from tests.test_term_clock_repair import tt_from_utc_with_known_offset


def tool():
    spec=importlib.util.find_spec('tools.audit_clock_repair')
    assert spec is not None, 'Missing clock repair report tool'
    return importlib.import_module('tools.audit_clock_repair')


def row(year, term=1, offset=37, delta=-35.):
    instant=datetime(year,2,4,tzinfo=UTC)
    first,second=tt_from_utc_with_known_offset(instant,offset)
    return {'year':year, 'term':term, 'utc_delta':delta,
            'tt_jd':first+second, 'dut1':0., 'delta_t':0.}


def test_pre_1961_remains_blocked_even_when_legacy_minute_was_match():
    report=tool().summarize_rows([row(1950,offset=0,delta=0.)])
    assert report['status']=='blocked'
    assert report['comparable_matched']==0
    assert report['historical_clock_unresolved']==1
    assert report['baseline_matched']==1
    assert report['production_authorized'] is False


def test_historical_fix_is_counted_without_tolerance_relaxation():
    r=row(1965,offset=3.584194,delta=-35.)
    report=tool().summarize_rows([r])
    assert report['fixed_original_mismatches']==1
    assert report['comparable_matched']==1
    assert report['minute_cell']=='[-30,30) seconds from reference display'
    assert report['status']=='blocked'  # Clock repair is never production approval.


def test_unresolved_modern_error_is_not_silently_dropped():
    report=tool().summarize_rows([row(2001,offset=32,delta=-30.5)])
    assert report['comparable_mismatched']==1
    assert report['fixed_original_mismatches']==0
    assert report['remaining_comparable_mismatches'][0]['year']==2001


def test_future_projection_is_counted_separately_even_if_number_matches():
    report=tool().summarize_rows([row(2040,delta=0.)])
    assert report['future_utc_assumption']==1
    assert report['comparable_matched']==0


def test_invalid_and_duplicate_replay_rows_are_rejected():
    for rows in ([],[row(2000),row(2000)],[{**row(2000),'utc_delta':float('nan')}],
                 [{**row(2000),'year':True}],[{**row(2000),'term':25}]):
        with pytest.raises(SazuError):
            tool().summarize_rows(rows)


def test_probe_with_wrong_hash_is_not_evidence(tmp_path):
    path=tmp_path/'probe.json'; path.write_text(json.dumps({'rows':[row(2000)]}))
    with pytest.raises(SazuError) as error:
        tool().load_replay(path)
    assert error.value.code=='DATA_INTEGRITY_FAILED'


def test_symlink_is_not_followed(tmp_path):
    target=tmp_path/'original'; target.write_bytes(b'{}')
    link=tmp_path/'symlink'; link.symlink_to(target)
    with pytest.raises(SazuError):
        tool().load_replay(link)


def test_legacy_and_new_modern_time_agree_to_microseconds():
    # Legacy display used only to replay the observed delta, never as reference truth.
    ts=load.timescale(builtin=True)
    r=row(2020,offset=37,delta=5.)
    report=tool().summarize_rows([r])
    assert report['comparable_matched']==1
    from sazu.term_clock import project_tt_to_utc
    assert abs((project_tt_to_utc(r['tt_jd']).instant_utc
                - ts.tt_jd(r['tt_jd']).utc_datetime()).total_seconds()) < .0001


def test_existing_audit_is_explicitly_legacy_evidence():
    from sazu.term_audit import compare_term_range
    from tests.test_term_audit import comparison_inputs
    document,candidates=comparison_inputs(2026,2026)
    result=compare_term_range(candidates,document,2026,2026)
    assert result['clock_projection']=='legacy_skyfield_utc_for_replay_only'
    assert result['production_authorized'] is False


def test_replay_rejects_different_legacy_time_model(monkeypatch):
    from importlib import metadata
    original=metadata.version
    monkeypatch.setattr(metadata,'version',lambda name:'different' if name=='skyfield' else original(name))
    with pytest.raises(SazuError) as error:
        tool().summarize_rows([row(2020,delta=0.)])
    assert error.value.code=='SOURCE_CONFLICT'
