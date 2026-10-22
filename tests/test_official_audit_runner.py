from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sazu.errors import SazuError

ROOT=Path(__file__).resolve().parents[1]


def test_pinned_manifests_do_not_bless_observed_hash(tmp_path):
    from tools.audit_official_terms import build_request, KASI_SHA256, KERNEL_SHA256
    kasi=tmp_path/'kasi';kasi.write_bytes(b'not official')
    kernel=tmp_path/'kernel';kernel.write_bytes(b'not ephemeris')
    req=build_request(kasi,kernel,datetime(2026,10,21,tzinfo=UTC),1920,2050)
    assert req['reference_manifest']['sha256']==KASI_SHA256
    assert req['kernel_manifest']['sha256']==KERNEL_SHA256
    assert req['reference_manifest']['rights_status']=='unreviewed'
    assert req['kernel_manifest']['rights_status']=='unreviewed'
    assert req['reference_manifest']['coverage_start']=='1920-01-01'
    assert req['reference_manifest']['coverage_end']=='2100-12-31'


@pytest.mark.parametrize('stamp',[datetime(2026,10,21),None,'2026-10-21'])
def test_acquisition_timestamp_must_be_explicit_utc(tmp_path,stamp):
    from tools.audit_official_terms import build_request
    a=tmp_path/'a';a.write_bytes(b'a')
    with pytest.raises(SazuError):build_request(a,a,stamp,1920,2050)


def test_missing_file_real_cli_json_error(tmp_path):
    path=ROOT/'tools/audit_official_terms.py'
    assert path.is_file(), 'Official reference runner not implemented'
    command=[sys.executable,str(path),'--kasi',str(tmp_path/'MISSING_PRIVATE'),
        '--kernel',str(tmp_path/'NO_KERNEL'),'--acquired-at','2026-10-21T00:00:00Z']
    r=subprocess.run(command,capture_output=True,timeout=10,
                     env={**os.environ,'PYTHONPATH':str(ROOT/'src')})
    assert r.returncode==2
    assert json.loads(r.stdout)['status']=='blocked'
    assert 'MISSING_PRIVATE' not in r.stdout.decode() and r.stderr==b''


def test_source_identity_change_blocks_without_generating(tmp_path,monkeypatch):
    import tools.audit_official_terms as module
    a=tmp_path/'not-real';a.write_bytes(b'not-real')
    def forbidden(*args):raise AssertionError('cannot generate with corrupt source')
    monkeypatch.setattr(module,'generate_terms',forbidden)
    with pytest.raises(SazuError):
        module.run_audit(a,a,datetime(2026,10,21,tzinfo=UTC),1920,2050)


def test_workflow_publishes_evidence_not_sources():
    import yaml
    c=yaml.safe_load((ROOT/'.github/workflows/official-validation.yml').read_text())
    assert c['permissions']=={'contents':'read'}
    job=c['jobs'].get('reference-comparison')
    assert job, 'Full official comparison not configured'
    uploads=[s for s in job['steps'] if 'actions/upload-artifact@' in s.get('uses','')]
    assert len(uploads)==1
    assert uploads[0]['with']['path']=='${{ runner.temp }}/official-audit.json'
    text=str(job)
    assert 'continue-on-error' not in text
    assert 'secrets.' not in text
