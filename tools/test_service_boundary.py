"""Real process integration; synthetic dates only. No commercial API or persisted births."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def request(base, path, payload=None, token=None):
    headers = {}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = None
    if payload is not None:
        data = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
        headers['Content-Type'] = 'application/json'
    try:
        response = urlopen(Request(base+path, data=data, headers=headers), timeout=5)
    except HTTPError as e:
        response = e
    with response:
        return response.status, json.load(response)


def wait_ready(url, process):
    for _ in range(150):
        if process.poll() is not None:
            raise RuntimeError('Integration process exited before liveness')
        try:
            if request(url, '/health/live')[0] == 200:
                return
        except (URLError, ConnectionError):
            pass
        time.sleep(.05)
    raise RuntimeError('Integration process did not become live')


class BoundaryIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.processes = []
        cls.logs = tempfile.TemporaryDirectory(prefix='sazu-integration-')
        cls.files = []
        cls.token = secrets.token_hex(32)
        cls.internal = secrets.token_hex(32)
        cls.external = os.environ.get('SAZU_TEST_BASE_URL')
        if cls.external:
            cls.base = cls.external
            cls.token = os.environ['RESEARCH_API_TOKEN']
            return
        if not (ROOT/'apps/api/dist/server.js').exists():
            raise AssertionError('Express process entrypoint is not implemented')
        cls.python_port, cls.api_port = free_port(), free_port()
        cls.python_url = f'http://127.0.0.1:{cls.python_port}'
        cls.base = f'http://127.0.0.1:{cls.api_port}'
        env = {**os.environ, 'SAZU_MODE':'research', 'CALCULATOR_TOKEN':cls.internal,
            'RESEARCH_API_TOKEN':cls.token, 'PYTHON_BASE_URL':cls.python_url,
            'DATABASE_URL':'postgresql://unavailable:synthetic@127.0.0.1:1/sazu',
            'PORT':str(cls.api_port), 'HOST':'127.0.0.1', 'PYTHON_TIMEOUT_MS':'1000',
            'PYTHONPATH':str(ROOT/'src')}
        try:
            for name, command in [
                ('calculator',[sys.executable,'-m','uvicorn','sazu.http_service:create_app_from_env',
                  '--factory','--host','127.0.0.1','--port',str(cls.python_port),'--no-access-log']),
                ('gateway',['node',str(ROOT/'apps/api/dist/server.js')])]:
                log = open(Path(cls.logs.name)/(name+'.log'),'wb')
                cls.files.append(log)
                process = subprocess.Popen(command, cwd=ROOT, env=env,stdout=log,stderr=log)
                cls.processes.append(process)
                wait_ready(cls.python_url if name=='calculator' else cls.base,process)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        for process in reversed(cls.processes):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()
        for f in cls.files: f.close()
        cls.logs.cleanup()

    def test_01_unknown_leap_preserves_both_candidates(self):
        status, body = request(self.base, '/v1/research/calendar',
            {'kind':'korean_lunar','year':2017,'month':5,'day':1,'leap':'unknown'}, self.token)
        self.assertEqual(status,200)
        self.assertEqual([r['solar'] for r in body['result']['candidates']], ['2017-05-26','2017-06-24'])
        self.assertIs(body['production_authorized'],False)

    def test_02_dst_fold_candidates_survive(self):
        status, body = request(self.base, '/v1/research/normalize-time',
          {'local_date':'2024-11-03','local_time':'01:30','zone':'America/New_York','precision':'instant'},self.token)
        self.assertEqual(status,200)
        self.assertEqual([r['start'] for r in body['result']['intervals']],
                         ['2024-11-03T05:30:00Z','2024-11-03T06:30:00Z'])

    def test_03_unknown_time_not_assumed_noon(self):
        status, body = request(self.base, '/v1/research/normalize-time',
          {'local_date':'2024-02-10','zone':'Asia/Seoul','precision':'unknown'},self.token)
        self.assertEqual(status,200)
        row=body['result']['intervals'][0]
        self.assertEqual(row['start'],'2024-02-09T15:00:00Z')
        self.assertEqual(row['end'],'2024-02-10T15:00:00Z')

    def test_04_strict_python_json_semantics_survive_gateway(self):
        for raw in ['{"kind":"gregorian","year":2024,"year":2024,"month":2,"day":10}',
                    '{"kind":"gregorian","year":2024.0,"month":2,"day":10}']:
            status,body=request(self.base,'/v1/research/calendar',raw,self.token)
            self.assertEqual(status,422)
            self.assertEqual(body['error']['code'],'INVALID_INPUT')

    def test_05_reject_auth_and_unimplemented_pillars(self):
        self.assertEqual(request(self.base,'/v1/research/calendar',{},'wrong')[0],401)
        self.assertEqual(request(self.base,'/v1/pillars',{},self.token)[0],404)

    def test_06_database_readiness_is_explicit(self):
        status,_=request(self.base,'/health/ready',token=self.token)
        self.assertEqual(status,200 if self.external else 503)

    def test_07_bad_calendar_never_returns_previous_success(self):
        status,body=request(self.base,'/v1/research/calendar',
                            {'kind':'gregorian','year':2024,'month':2,'day':30},self.token)
        self.assertEqual(status,422)
        self.assertNotIn('result',body)

    def test_99_stopped_python_is_not_fallback_success(self):
        if self.external:
            self.skipTest('Process ownership is external; outage test is in local runner')
        self.processes[0].terminate();self.processes[0].wait(timeout=5)
        status,body=request(self.base,'/v1/research/calendar',
                            {'kind':'gregorian','year':2024,'month':2,'day':10},self.token)
        self.assertEqual(status,503)
        self.assertEqual(body['error']['code'],'CALCULATOR_UNAVAILABLE')


if __name__=='__main__':
    unittest.main(verbosity=2)
