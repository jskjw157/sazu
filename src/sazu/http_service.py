"""Private, research-only HTTP adapter. Numerical rules remain in the existing core.

Only calendar/time normalization are exposed. CLI file/network/admin operations
are deliberately unreachable. No incoming credentials or birth data are logged.
"""
import asyncio
import hashlib
import hmac
import os
import re
from collections.abc import Callable
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import Response

from .cli import dispatch
from .errors import SazuError
from .serde import canonical_json, parse_request

CONTRACT = 'sazu.foundation.v1'
MAX_BODY = 16384
HTTP_ERRORS = {
    'UNAUTHORIZED': (401, 'Authentication required.'),
    'CONTRACT_MISMATCH': (409, 'Unsupported protocol version.'),
    'UNSUPPORTED_MEDIA_TYPE': (415, 'Use uncompressed UTF-8 JSON.'),
    'REQUEST_TOO_LARGE': (413, 'Request exceeds the allowed size.'),
    'REQUEST_TIMEOUT': (408, 'Request body deadline exceeded.'),
    'BUSY': (503, 'Service is at capacity.'),
    'NOT_FOUND': (404, 'Endpoint not found.'),
    'METHOD_NOT_ALLOWED': (405, 'Method not allowed.'),
    'INTERNAL_ERROR': (500, 'The operation could not be completed.'),
}


def _request_id(request: Request) -> str:
    if hasattr(request.state, 'request_id'):
        return request.state.request_id
    values = request.headers.getlist('x-request-id')
    value = values[0] if len(values) == 1 else ''
    try:
        valid = len(value) == 36 and str(UUID(value)) == value
    except ValueError:
        valid = False
    request.state.request_id = value if valid else str(uuid4())
    return request.state.request_id


def _response(request: Request, http_status: int, **fields) -> Response:
    rid = _request_id(request)
    return Response(canonical_json({'contract_version': CONTRACT,
        'production_authorized': False, 'request_id': rid, **fields}),
        status_code=http_status, media_type='application/json',
        headers={'cache-control': 'no-store', 'x-content-type-options': 'nosniff',
                 'x-request-id': rid, 'x-sazu-contract': CONTRACT})


def _error(request: Request, code: str) -> Response:
    if code in HTTP_ERRORS:
        status, message = HTTP_ERRORS[code]
        error = {'code': code, 'message': message, 'retryable': code == 'BUSY'}
    else:
        error = SazuError(code).as_dict()
        status = 422 if code in {'INVALID_INPUT', 'UNSUPPORTED_RANGE',
            'NONEXISTENT_LOCAL_TIME', 'UNSUPPORTED_TIMEZONE_RULE'} else 503
    return _response(request, status, ok=False, error=error)


def create_app(internal_token: str, *, mode: str = 'research',
               body_timeout: float = 5.0, engine: Callable = dispatch) -> FastAPI:
    """Construct a private app; absence of production approval is not configurable."""
    if (type(internal_token) is not str or re.fullmatch('[0-9a-f]{64}', internal_token) is None
            or mode != 'research' or not 0 < body_timeout <= 30):
        raise ValueError('Invalid service configuration')
    expected = hashlib.sha256(f'Bearer {internal_token}'.encode()).digest()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.active = 0

    def authorize(request: Request) -> Response | None:
        values = request.headers.getlist('authorization')
        if len(values) != 1 or not hmac.compare_digest(
                hashlib.sha256(values[0].encode()).digest(), expected):
            return _error(request, 'UNAUTHORIZED')
        if request.headers.getlist('x-sazu-contract') != [CONTRACT]:
            return _error(request, 'CONTRACT_MISMATCH')
        return None

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return _error(request, 'METHOD_NOT_ALLOWED' if exc.status_code == 405 else 'NOT_FOUND')

    @app.get('/health/live')
    async def liveness(request: Request):
        return _response(request, 200, ok=True, status='alive')

    @app.get('/health/ready')
    async def readiness(request: Request):
        denied = authorize(request)
        if denied is not None:
            return denied
        try:
            # Local pinned resources only; metadata are not returned to the caller.
            await run_in_threadpool(dispatch, 'environment', {})
            return _response(request, 200, ok=True, status='ready')
        except Exception:
            return _error(request, 'SOURCE_NOT_AVAILABLE')

    async def execute(request: Request, operation: str):
        denied = authorize(request)
        if denied is not None:
            return denied
        content_types = request.headers.getlist('content-type')
        if (len(content_types) != 1 or
                re.fullmatch(r'application/json(?:\s*;\s*charset=utf-8)?',
                             content_types[0].lower()) is None or
                request.headers.get('content-encoding', 'identity') != 'identity'):
            return _error(request, 'UNSUPPORTED_MEDIA_TYPE')
        if app.state.active >= 16:
            return _error(request, 'BUSY')
        app.state.active += 1
        try:
            raw = bytearray()
            async with asyncio.timeout(body_timeout):
                async for chunk in request.stream():
                    if len(raw) + len(chunk) > MAX_BODY:
                        return _error(request, 'REQUEST_TOO_LARGE')
                    raw.extend(chunk)
            payload = parse_request(raw.decode('utf-8'))
            # No generic HTTP command dispatcher; operation is fixed by the route.
            result = await run_in_threadpool(engine, operation, payload)
            return _response(request, 200, ok=True, result=result)
        except TimeoutError:
            return _error(request, 'REQUEST_TIMEOUT')
        except SazuError as exc:
            return _error(request, exc.code)
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
            return _error(request, 'INVALID_INPUT')
        except Exception:
            return _error(request, 'INTERNAL_ERROR')
        finally:
            app.state.active -= 1

    @app.post('/internal/v1/calendar')
    async def calendar(request: Request):
        return await execute(request, 'calendar')

    @app.post('/internal/v1/normalize-time')
    async def normalize_time(request: Request):
        return await execute(request, 'normalize-time')

    return app


def create_app_from_env() -> FastAPI:
    return create_app(os.environ.get('CALCULATOR_TOKEN', ''),
                      mode=os.environ.get('SAZU_MODE', ''))
