"""HTTP boundary regressions, using the real existing foundation core."""
import asyncio
import importlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sazu.cli import dispatch
from sazu.serde import canonical_json

TOKEN = 'a' * 64
CONTRACT = 'sazu.foundation.v1'
HEADERS = {'authorization': f'Bearer {TOKEN}', 'x-sazu-contract': CONTRACT}
CAL = {'kind': 'korean_lunar', 'year': 2017, 'month': 5, 'day': 1, 'leap': 'unknown'}
TIME = {'local_date': '2024-11-03', 'zone': 'America/New_York',
        'precision': 'instant', 'local_time': '01:30'}


def service(**kwargs):
    spec = importlib.util.find_spec('sazu.http_service')
    assert spec is not None, 'Internal HTTP adapter is not implemented'
    return importlib.import_module('sazu.http_service').create_app(TOKEN, **kwargs)


def client(**kwargs):
    return TestClient(service(**kwargs), raise_server_exceptions=False)


@pytest.mark.parametrize('operation,payload', [('calendar', CAL), ('normalize-time', TIME)])
def test_http_result_matches_existing_core(operation, payload):
    response = client().post(f'/internal/v1/{operation}', json=payload, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body['contract_version'] == CONTRACT and body['production_authorized'] is False
    assert body['result'] == json.loads(canonical_json(dispatch(operation, payload)))
    assert response.headers['cache-control'] == 'no-store'
    assert len(body['request_id']) == 36


@pytest.mark.parametrize('authorization', [None, 'Bearer wrong', f'Basic {TOKEN}',
                                            f'Bearer {TOKEN} ', f'bearer {TOKEN}'])
def test_internal_authentication_required(authorization):
    headers = {'x-sazu-contract': CONTRACT}
    if authorization is not None:
        headers['authorization'] = authorization
    r = client().post('/internal/v1/calendar', json=CAL, headers=headers)
    assert r.status_code == 401
    assert r.json()['error']['code'] == 'UNAUTHORIZED'
    assert TOKEN not in r.text


def test_duplicate_authorization_denied():
    r = client().post('/internal/v1/calendar', json=CAL, headers=[
        ('authorization', f'Bearer {TOKEN}'), ('authorization', f'Bearer {TOKEN}'),
        ('x-sazu-contract', CONTRACT)])
    assert r.status_code == 401


@pytest.mark.parametrize('raw', ['{"year":2017,"year":2017}', '{"year":NaN}',
                               '{"year":Infinity}', '[]', 'null', '{', '{"year":1e999}',
                               '{"kind":"gregorian","year":true,"month":1,"day":1}',
                               '{"kind":"gregorian","year":2024.0,"month":1,"day":1}'])
def test_invalid_json_never_returns_calculation(raw):
    r = client().post('/internal/v1/calendar', content=raw,
                      headers={**HEADERS, 'content-type': 'application/json'})
    assert r.status_code == 422 and r.json()['error']['code'] == 'INVALID_INPUT'
    assert 'input' not in r.json()['error']


@pytest.mark.parametrize('extra', [{'path': '/etc/passwd'}, {'url': 'https://example.com'},
                                    {'command': 'acquire-source'}, {'approved': True}])
def test_extra_privileged_fields_rejected(extra):
    r = client().post('/internal/v1/calendar', json={**CAL, **extra}, headers=HEADERS)
    assert r.status_code == 422


@pytest.mark.parametrize('route', ['acquire-source', 'verify-source', 'environment',
                                    'generate-terms', 'pillars'])
def test_admin_cli_functions_are_not_http_endpoints(route):
    r = client().post(f'/internal/v1/{route}', json={}, headers=HEADERS)
    assert r.status_code == 404


def test_liveness_is_not_production_readiness():
    r = client().get('/health/live')
    assert r.status_code == 200 and r.json()['status'] == 'alive'
    assert r.json()['production_authorized'] is False
    assert client().get('/health/ready').status_code == 401
    assert client().get('/health/ready', headers=HEADERS).status_code == 200


def test_wrong_contract_rejected():
    r = client().post('/internal/v1/calendar', json=CAL,
                      headers={**HEADERS, 'x-sazu-contract': 'future.v99'})
    assert r.status_code == 409


def test_media_encoding_and_size_limits():
    c = client()
    assert c.post('/internal/v1/calendar', content='{}', headers=HEADERS).status_code == 415
    assert c.post('/internal/v1/calendar', content='{}', headers={**HEADERS,
        'content-type': 'application/json', 'content-encoding': 'gzip'}).status_code == 415
    assert c.post('/internal/v1/calendar', content='x' * 16385,
        headers={**HEADERS, 'content-type': 'application/json'}).status_code == 413
    assert c.post('/internal/v1/calendar', content=b'\xff',
        headers={**HEADERS, 'content-type': 'application/json'}).status_code == 422


def test_docs_not_exposed_and_no_secret_echo():
    for path in ['/docs', '/redoc', '/openapi.json']:
        assert client().get(path, headers=HEADERS).status_code == 404


def test_correlated_id_is_validated():
    rid = '9de00466-f489-4841-90f5-259923c598a0'
    c = client()
    r = c.post('/internal/v1/calendar', json=CAL, headers={**HEADERS, 'x-request-id': rid})
    assert r.json()['request_id'] == rid
    r = c.post('/internal/v1/calendar', json=CAL,
               headers={**HEADERS, 'x-request-id': 'birth-date-private'})
    assert 'birth-date-private' not in r.text


def test_internal_exception_is_sanitized(caplog):
    def exploding(*args):
        raise RuntimeError('PRIVATE_BIRTH_DATA TOKEN_SHOULD_NOT_LEAK')
    r = client(engine=exploding).post('/internal/v1/calendar', json=CAL, headers=HEADERS)
    assert r.status_code == 500
    assert 'PRIVATE' not in r.text and 'PRIVATE' not in caplog.text


def test_authentication_is_checked_before_body_parsing():
    r = client().post('/internal/v1/calendar', content='x' * 20000)
    assert r.status_code == 401


@pytest.mark.parametrize('token', ['', 'short', 'z' * 64, 'a' * 63, 'a' * 65])
def test_invalid_token_configuration_rejected(token):
    module = importlib.import_module('sazu.http_service') if importlib.util.find_spec('sazu.http_service') else None
    assert module is not None, 'Internal HTTP adapter is not implemented'
    with pytest.raises(ValueError, match='configuration'):
        module.create_app(token)


def test_production_mode_is_not_silently_enabled():
    with pytest.raises(ValueError, match='configuration'):
        service(mode='production')


def test_concurrent_requests_preserve_separate_inputs():
    c = client()
    payloads = [{**CAL, 'day': d} for d in range(1, 9)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda x: c.post('/internal/v1/calendar', json=x, headers=HEADERS), payloads))
    assert all(r.status_code == 200 for r in results)
    assert [r.json()['result']['request']['day'] for r in results] == list(range(1, 9))


def test_request_body_read_deadline():
    import httpx
    async def slow():
        yield b'{'
        await asyncio.sleep(.2)
        yield b'}'
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service(body_timeout=.02)), base_url='http://test') as c:
            return await c.post('/internal/v1/calendar', content=slow(), headers={**HEADERS, 'content-type': 'application/json'})
    assert asyncio.run(scenario()).status_code == 408
