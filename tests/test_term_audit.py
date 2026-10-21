from dataclasses import replace
from datetime import timedelta

import pytest
from sazu.errors import SazuError
from sazu.serde import digest
from tests.test_kasi_reference import document_bytes, parse


def comparison_inputs(first=1993,last=1993):
    from sazu.kasi_reference import reference_events
    doc=parse(document_bytes(first,last),first,last)
    ref=reference_events(doc,first,last)
    computed=[replace(r,source_id='synthetic-computed',source_sha256='c'*64,
                      precision='computed',original_time=None,lower_utc=None,upper_utc=None,
                      tt_jd=2440000.0,model_id='d'*64,numerical_tolerance_days=1e-8) for r in ref]
    return doc,computed


def audit(values,doc,first=1993,last=1993):
    from sazu.term_audit import compare_term_range
    return compare_term_range(values,doc,first,last)


def test_all_match_not_production_approval():
    doc,values=comparison_inputs()
    r=audit(values,doc)
    assert r['status']=='passed' and r['matched']==24 and r['expected']==24
    assert r['mismatches']==[] and r['production_authorized'] is False
    assert r['physical_source_independence']=='not_established'
    assert r['reference']['rights_status']=='unreviewed'
    assert r['reference']['sha256']==doc.manifest.sha256
    assert r['comparison_policy']=='nearest-minute-half-up-v1'
    assert r['report_sha256']==digest({k:v for k,v in r.items() if k!='report_sha256'})


def test_empty_candidate_cannot_vacuously_pass():
    doc,_=comparison_inputs();r=audit([],doc)
    assert r['status']=='failed' and len(r['missing_candidate_keys'])==24
    assert r['matched']==0


def test_missing_extra_and_duplicate_are_distinct():
    doc,values=comparison_inputs()
    _,other=comparison_inputs(1994,1994)
    r=audit(values[1:]+[values[1],other[0]],doc)
    assert r['status']=='failed'
    assert r['missing_candidate_keys']==[[1993,23]]
    assert r['extra_candidate_keys']==[[1994,23]]
    assert r['duplicate_candidate_keys']==[[1993,24]]
    assert r['matched']==22


@pytest.mark.parametrize('seconds,status',[(-30,'passed'),(-30.000001,'failed'),(29.999999,'passed'),(30,'failed')])
def test_exact_rounding_cell_edges(seconds,status):
    doc,values=comparison_inputs()
    values[0]=replace(values[0],instant_utc=values[0].instant_utc+timedelta(seconds=seconds))
    r=audit(values,doc)
    assert r['status']==status
    assert len(r['mismatches'])==(status=='failed')
    if status=='failed':
        assert r['mismatches'][0]['delta_seconds_from_display']==seconds


def test_every_mismatch_is_recorded_not_just_first():
    doc,values=comparison_inputs(1993,1994)
    for i in (0,4,25):values[i]=replace(values[i],instant_utc=values[i].instant_utc+timedelta(seconds=31))
    r=audit(values,doc,1993,1994)
    assert r['matched']==45 and len(r['mismatches'])==3 and r['expected']==48
    assert r['by_year']==[{'year':1993,'matched':22,'mismatched':2}, {'year':1994,'matched':23,'mismatched':1}]


def test_no_overlap_only_success():
    doc,values=comparison_inputs()
    r=audit(values,doc,1993,1994)
    assert r['status']=='blocked'
    assert 'REFERENCE_COVERAGE_UNAVAILABLE' in r['blockers']


@pytest.mark.parametrize('field,value', [('model_id','e'*64),('source_sha256','e'*64),('source_id','different')])
def test_model_and_source_mixing_blocked(field,value):
    doc,values=comparison_inputs();values[0]=replace(values[0],**{field:value})
    r=audit(values,doc)
    assert r['status']=='blocked' and 'MIXED_CANDIDATE_IDENTITIES' in r['blockers']


def test_same_reference_bytes_cannot_be_independent_calculation():
    doc,values=comparison_inputs()
    values=[replace(v,source_sha256=doc.manifest.sha256) for v in values]
    assert 'REFERENCE_SOURCE_REUSED' in audit(values,doc)['blockers']


def test_displayed_reference_not_accepted_as_computed():
    from sazu.kasi_reference import reference_events
    doc,_=comparison_inputs()
    assert audit(reference_events(doc,1993,1993),doc)['status']=='blocked'


def test_deterministic_sorted_input_and_no_full_raw_reference_in_report():
    doc,values=comparison_inputs()
    a=audit(values,doc);b=audit(list(reversed(values)),doc)
    assert a==b
    assert 'rows' not in a['reference']
    assert 'original_time' not in str(a)


@pytest.mark.parametrize('first,last',[(True,1993),(1993.0,1993),(1994,1993),(1900,1993),(1993,2100)])
def test_range_contract(first,last):
    doc,values=comparison_inputs()
    with pytest.raises(SazuError):audit(values,doc,first,last)


def test_wrong_event_order_in_time_is_not_accepted():
    doc,values=comparison_inputs()
    values[0]=replace(values[0],instant_utc=values[1].instant_utc+timedelta(seconds=1))
    r=audit(values,doc)
    assert r['status']=='failed'
    assert r['invalid_annual_structure']==[1993]
