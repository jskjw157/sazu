# Express + Python service boundary implementation plan

> For agentic workers: use superpowers:executing-plans task-by-task with test-first verification. This plan records implementation decisions, not tests already passed.

**Goal:** Keep Python as the only calculation implementation and expose the existing S1 calendar/time functions through an Express + TypeScript gateway.
**Architecture:** Browser -> Express -> authenticated internal Python HTTP adapter -> existing sazu package. PostgreSQL is accessible only by Express; this increment checks connectivity but does not persist personal inputs or claim that S2 pillars exist.
**Tech stack:** Node.js/Express/TypeScript, FastAPI thin internal adapter, existing Python core, PostgreSQL, Docker Compose, pytest and Node test runner.
**Spec:** Existing `docs/superpowers/specs/2026-10-21-self-hosted-foundation-design.md`, `AGENTS.md`, plus the boundary design below. User selected Express main server + Python-only calculations and explicitly requested implementation in this conversation.

## Boundary design and global constraints

- Existing foundation base: f7d48b4443dafd30716ead04a23a68f0bd11f1a9 (PR #2). Do not merge or change that branch; deliver a stacked implementation PR.
- No commercial fortune API, no duplicated TypeScript astronomy/calendar rules, no per-request child_process spawning.
- Python HTTP permits only calendar conversion and time normalization. Never expose CLI dispatch commands for file reading, source downloads, environment inspection or arbitrary operations.
- API contract `sazu.foundation.v1`; responses always identify `production_authorized: false`. This is research access, not a production saju/pillars endpoint.
- Express uses a separate research-access bearer credential until real user auth is implemented. Python requires a distinct internal bearer credential. Credentials are injected, not committed, must be at least 32 bytes of hex entropy, and may not be equal.
- Fixed configured upstream, no redirects, bounded request/response bytes, bounded duration/concurrency, stable sanitized errors, no input/body/token logs or persistence.
- Preserve request bytes through Express so Python duplicate-key rejection is not bypassed by JSON serialization. Express validates shape; Python remains semantic authority.
- Public health/liveness contains no secrets. Readiness checks Python and (when configured) PostgreSQL, and is distinct from release approval.
- Compose binds only Express to host loopback. Python and PostgreSQL have no published ports; neither receives the other's unnecessary credentials. No deployment performed.
- Preserve all historical evidence and clearly distinguish integration tests from independent official-data validation.

## Review focus
1. Missing/duplicate/wrong auth and equal credentials must fail closed (Tasks 1/2).
2. Giant, invalid, duplicate-key, nonfinite JSON and unexpected fields must not leak inputs or invoke privileged CLI operations (Tasks 1/2).
3. Upstream hangs, disconnects, redirects, oversized or schema-invalid responses must not become successful calculations (Task 2).
4. Existing unknown leap/time and DST ambiguity must survive the HTTP boundary unchanged (Tasks 1/3).
5. Compose must not publish database/Python ports, and DB outages must affect readiness without storing birth data (Task 3).

## Tasks

### Task 1 — Thin authenticated Python adapter
Files: `src/sazu/http_service.py`, `tests/test_http_service.py`, `requirements-http.lock`.
Interface: `create_app(internal_token: str) -> FastAPI`; `POST /internal/v1/calendar`, `POST /internal/v1/normalize-time`, `GET /health/live`, authenticated `GET /health/ready`.
- [ ] Write tests for valid results matching core; missing/wrong credentials; invalid media/JSON/extra fields/oversized body; unknown routes; no production authorization; sanitized internal errors.
- [ ] Run pytest on these tests and record RED before implementation.
- [ ] Implement bounded HTTP adapter around existing dispatch's two whitelisted operations only; do not change numerical logic.
- [ ] Run new tests and existing full suite; record exact failures/skips and commit.

### Task 2 — Express gateway with bounded typed transport
Files: `apps/api/package.json`, lockfile, tsconfig, `src/{config,contracts,python-client,app,server}.ts`, Node tests.
Interfaces: `createApp(config, dependencies)`; fixed `PythonClient.call(operation, rawBody, signal)`; `/v1/research/calendar` and `/v1/research/normalize-time`.
- [ ] Write real HTTP tests against a local controlled upstream for credentials, raw byte preservation, schemas, timeout, oversized response, errors and correlation identifiers.
- [ ] Run Node tests/TypeScript compilation and record RED before implementation.
- [ ] Implement Express 5 gateway, schema validation, stable error envelope, distinct secrets, bounded request duration/concurrency, disconnect cancellation and safe shutdown.
- [ ] Run typecheck, full Node suite, npm audit; document blockers rather than weaken assertions; commit.

### Task 3 — Real integration and isolated local stack
Files: Dockerfiles, `compose.yaml`, `.env.example`, `tools/test_service_boundary.py`, `docs/implementation/express-python.md`, CI workflow.
- [ ] Write real-process E2E tests: Express forwards to Python, successful lunar/leap/time cases; wrong internal token; stopped Python; PostgreSQL readiness; forbidden routes/production flags.
- [ ] Run tests before wiring and record RED.
- [ ] Wire Python runtime and Node gateway, PostgreSQL readiness adapter and least-exposure Compose defaults. Provide no persistence/migration claim.
- [ ] Run unit suites, types/build, real process E2E; run Compose build/network isolation in CI where Docker is available.
- [ ] Record actual commands and outputs, environment limitations, dependency audit, existing engine approval blockers, PR URL and final head SHA.

## Execution notes
The current local container cannot resolve public GitHub/npm/PyPI DNS. GitHub connector access works. A temporary CI bootstrap may package only the public tracked repository and public npm dependencies for offline local development. No credential files, private documents, kernel files or environment contents are included. The bootstrap workflow will be replaced by normal service CI before final delivery. This is not deployment or autonomous background work; final claims require observed execution results.
