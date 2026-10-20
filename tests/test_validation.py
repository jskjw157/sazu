from datetime import date
from hashlib import sha256
from dataclasses import replace
import pytest
from sazu.calendar import CalendarInput,convert_calendar
from sazu.errors import SazuError
from tests.test_core import manifest


def rows():
    return [convert_calendar(CalendarInput('gregorian',2026,1,i)).candidates[0] for i in (1,2)]

def test_missing_reference_blocked():
    from sazu.validation import compare_calendar_records
    assert compare_calendar_records(rows(),None,('same',),())['status']=='blocked'

def test_shared_lineage_not_independent():
    from sazu.validation import compare_calendar_records
    r=compare_calendar_records(rows(),rows(),('same',),('same',))
    assert r['status']=='blocked' and not r['independent']

def test_full_matching_keyset():
    from sazu.validation import compare_calendar_records
    r=compare_calendar_records(rows(),rows(),('candidate',),('reference',))
    assert r['status']=='passed' and r['matched']==2
    assert r['evidence_level']=='independent_reference_candidate_not_release_approval'

@pytest.mark.parametrize('case',['missing','duplicate','mismatch','extra'])
def test_reference_conflicts(case):
    from sazu.validation import compare_calendar_records
    a=rows();b=rows()
    if case=='missing':b=b[:1]
    if case=='duplicate':b.append(b[0])
    if case=='mismatch':b[0]=replace(b[0],lunar_day=1)
    if case=='extra':b.append(convert_calendar(CalendarInput('gregorian',2026,1,3)).candidates[0])
    assert compare_calendar_records(a,b,('candidate',),('reference',))['status']=='failed'

@pytest.mark.parametrize('path',['../a','/tmp/a','a/../../b','a\\b','a\n.txt','.','a//b'])
def test_artifact_path_rejected(path):
    from sazu.datasets import Artifact
    with pytest.raises(SazuError): Artifact(path,'a'*64,3)

def test_candidate_files_and_production_block(tmp_path):
    from sazu.datasets import Artifact,DatasetCandidate,verify_candidate_files,require_production_release,blockers
    p=tmp_path/'data.json';p.write_bytes(b'abc')
    a=Artifact('data.json',sha256(b'abc').hexdigest(),3)
    c=DatasetCandidate('candidate-v1',date(1920,1,1),date(2050,12,31),('Asia/Seoul',),(a,),(manifest(),),())
    assert verify_candidate_files(tmp_path,c)
    assert 'TRUSTED_RELEASE_AUTHORIZATION_NOT_IMPLEMENTED' in blockers(c)
    assert c.production_authorized is False
    with pytest.raises(SazuError) as e: require_production_release(c)
    assert e.value.code=='RELEASE_NOT_APPROVED'
    p.write_bytes(b'bad')
    with pytest.raises(SazuError): verify_candidate_files(tmp_path,c)

def test_no_forged_approval():
    from sazu.datasets import DatasetCandidate
    with pytest.raises(TypeError): DatasetCandidate(production_authorized=True)

def test_empty_comparison_not_success():
    from sazu.validation import compare_calendar_records
    assert compare_calendar_records([],[],('a',),('b',))['status']=='blocked'
