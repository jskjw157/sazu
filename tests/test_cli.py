import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]


def invoke(command,payload,cwd=None):
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'src')
    p=subprocess.run([sys.executable,'-m','sazu',command],input=payload,capture_output=True,
                     cwd=cwd or ROOT,env=env,timeout=15)
    return p, json.loads(p.stdout)


def test_cli_calendar():
    p,r=invoke('calendar',b'{"kind":"korean_lunar","year":2017,"month":5,"day":1,"leap":"unknown"}')
    assert p.returncode==0 and p.stderr==b'' and r['production_authorized'] is False
    assert len(r['result']['candidates'])==2


def test_cli_fold(tmp_path):
    p,r=invoke('normalize-time',b'{"local_date":"2026-11-01","zone":"America/New_York","precision":"instant","local_time":"01:30"}',tmp_path)
    assert p.returncode==0 and len(r['result']['intervals'])==2
    assert list(tmp_path.iterdir())==[]

@pytest.mark.parametrize('payload',[b'null',b'[]',b'{bad',b'{"x":1,"x":2}',b'{"x":NaN}',
 b'{"x":1e999}',b'\xff',b'{"kind":"gregorian","year":true,"month":1,"day":1}',
 b'{"kind":"gregorian","year":2026,"month":1,"day":1,"secret":"PRIVATE-MARKER"}'])
def test_cli_invalid(payload):
    p,r=invoke('calendar',payload)
    assert p.returncode==2 and p.stderr==b'' and not r['ok']
    assert b'PRIVATE-MARKER' not in p.stdout


def test_cli_too_large():
    p,r=invoke('calendar',b' '*65537)
    assert p.returncode==2 and r['error']['code']=='REQUEST_TOO_LARGE'


def test_cli_unknown_command():
    p,r=invoke('private-token',b'{}')
    assert p.returncode==2 and b'private-token' not in p.stdout


def test_environment_actual_versions():
    p,r=invoke('environment',b'{}')
    assert p.returncode==0 and r['result']['calendar_version']=='0.3.1'
    assert r['result']['tzdata_version']=='2026.2'


def test_missing_solar_data():
    p,r=invoke('generate-terms',b'{"path":"private-user-file"}')
    assert p.returncode==2 and b'private-user-file' not in p.stdout
