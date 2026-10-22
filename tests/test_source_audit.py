from dataclasses import asdict, replace
from datetime import UTC, date, datetime
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sazu.contracts import SourceManifest
from sazu.errors import SazuError
from sazu.serde import canonical_json
from tests.test_kasi_reference import document_bytes, reference_manifest
from tests.test_term_audit import comparison_inputs

ROOT=Path(__file__).resolve().parents[1]


def files(tmp_path):
    raw=document_bytes(); path=tmp_path/'private-reference.txt';path.write_bytes(raw)
    return path,reference_manifest(raw)


def kernel_manifest():
    return SourceManifest('synthetic-kernel','Synthetic test','test-v1',
      'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp',
      hashlib.sha256(b'kernel').hexdigest(),6,datetime(2026,10,21,tzinfo=UTC),
      date(1900,1,1),date(2100,1,1),'TDB','computed','unreviewed',
      'https://naif.jpl.nasa.gov/naif/rules.html',('synthetic',),'v1')


def request(tmp_path):
    path,m=files(tmp_path);kernel=tmp_path/'kernel.bsp';kernel.write_bytes(b'kernel')
    return json.loads(canonical_json({'reference_path':str(path),'reference_manifest':asdict(m),
       'kernel_path':str(kernel),'kernel_manifest':asdict(kernel_manifest()),'start_year':1993,'end_year':1993}))


def run_cli(command,body):
    return subprocess.run([sys.executable,'-m','sazu.source_audit',command],input=body,
        capture_output=True,cwd=ROOT,env={**os.environ,'PYTHONPATH':str(ROOT/'src')},timeout=10)


def test_cli_inspection_real_process(tmp_path):
    path,m=files(tmp_path)
    result=run_cli('inspect',canonical_json({'path':str(path),'manifest':asdict(m)}).encode())
    assert result.returncode==0,result.stderr.decode()
    output=json.loads(result.stdout)
    assert output['ok'] is True and output['result']['status']=='inspected'
    assert output['result']['reference']['row_count']==24
    assert output['result']['production_authorized'] is False
    assert 'private-reference' not in result.stdout.decode()
    assert 'rows' not in output['result']['reference']
    assert result.stderr==b''


@pytest.mark.parametrize('body',[b'{}',b'[]',b'{"path":"a","path":"b"}',b'NaN',b'\xff',b'x'*65537],
                         ids=['missing','array','duplicate','nonfinite','encoding','oversize'])
def test_cli_malformed_requests_no_traceback(body):
    result=run_cli('inspect',body)
    assert result.returncode==2
    assert json.loads(result.stdout)['ok'] is False
    assert result.stderr==b''


def test_unknown_command_and_extra_field(tmp_path):
    path,m=files(tmp_path)
    for command,payload in [('delete',{'path':str(path),'manifest':asdict(m)}),
                            ('inspect',{'path':str(path),'manifest':asdict(m),'approved':True})]:
        r=run_cli(command,canonical_json(payload).encode())
        assert r.returncode==2 and json.loads(r.stdout)['error']['code']=='INVALID_INPUT'


def test_no_user_paths_in_missing_file_error(tmp_path):
    _,m=files(tmp_path)
    r=run_cli('inspect',canonical_json({'path':str(tmp_path/'private-MISSING'),'manifest':asdict(m)}).encode())
    assert r.returncode==2
    assert json.loads(r.stdout)['error']['code']=='SOURCE_NOT_AVAILABLE'
    assert 'private-MISSING' not in r.stdout.decode() and r.stderr==b''


def test_read_same_descriptor_hash_and_symlink_checks(tmp_path):
    from sazu.source_audit import read_reference_bytes
    path,m=files(tmp_path)
    assert read_reference_bytes(path,m)==path.read_bytes()
    alias=tmp_path/'alias';alias.symlink_to(path)
    with pytest.raises(SazuError):read_reference_bytes(alias,m)
    with pytest.raises(SazuError):read_reference_bytes(path,replace(m,sha256='a'*64))
    with pytest.raises(SazuError):read_reference_bytes(path,replace(m,size_bytes=m.size_bytes-1))
    with pytest.raises(SazuError):read_reference_bytes(path,replace(m,size_bytes=1048577))
    with pytest.raises(SazuError):read_reference_bytes(tmp_path,m)


def test_fifo_rejected_without_hanging(tmp_path):
    from sazu.source_audit import read_reference_bytes
    _,m=files(tmp_path);fifo=tmp_path/'fifo';os.mkfifo(fifo)
    with pytest.raises(SazuError):read_reference_bytes(fifo,m)


def test_batch_uses_existing_generator_and_compares(tmp_path,monkeypatch):
    import sazu.source_audit as module
    payload=request(tmp_path);_,candidate=comparison_inputs()
    monkeypatch.setattr(module,'generate_terms',lambda year,path,m:tuple(candidate))
    report=module.execute_audit('compare',payload)
    assert report['matched']==24 and report['status']=='passed'


@pytest.mark.parametrize('status,exit_code,ok',[('passed',0,True),('failed',1,False),('blocked',2,False)])
def test_main_keeps_mismatch_and_blocked_exit_codes(status,exit_code,ok,monkeypatch):
    import sazu.source_audit as module
    monkeypatch.setattr(module,'execute_audit',lambda *args:dict(status=status,production_authorized=False))
    monkeypatch.setattr(sys,'stdin',io.TextIOWrapper(io.BytesIO(b'{}'),encoding='utf-8'))
    output=io.StringIO();monkeypatch.setattr(sys,'stdout',output)
    assert module.main(['compare'])==exit_code
    result=json.loads(output.getvalue())
    assert result['ok'] is ok and result['result']['production_authorized'] is False


def test_incomplete_reference_range_does_not_generate(tmp_path,monkeypatch):
    import sazu.source_audit as module
    payload=request(tmp_path);payload['end_year']=1994
    def forbidden(*args):raise AssertionError('must reject before generation')
    monkeypatch.setattr(module,'generate_terms',forbidden)
    with pytest.raises(SazuError) as error:module.execute_audit('compare',payload)
    assert error.value.code=='UNSUPPORTED_RANGE'


def test_kernel_tampering_fails_before_generation(tmp_path,monkeypatch):
    import sazu.source_audit as module
    payload=request(tmp_path);Path(payload['kernel_path']).write_bytes(b'broken')
    def forbidden(*args):raise AssertionError('must reject before generation')
    monkeypatch.setattr(module,'generate_terms',forbidden)
    with pytest.raises(SazuError):module.execute_audit('compare',payload)


def test_http_does_not_publish_new_admin_commands():
    text=(ROOT/'src/sazu/http_service.py').read_text()
    assert 'source_audit' not in text and 'audit-terms' not in text
