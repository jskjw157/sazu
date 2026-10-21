# ADR-0002 — Express main API, Python calculation authority

Date: 2026-10-21. User selected this hybrid architecture and requested implementation.

Express + TypeScript owns the external service boundary and future accounts, consent, payments, AI orchestration and PostgreSQL persistence. Python remains the sole numerical/calendar/timezone authority. A persistent private HTTP process wraps the existing Python package; no per-request process spawning and no duplicated TypeScript calculator.

The private adapter uses FastAPI only as transport, not as a second public application backend. Source acquisition and heavy ephemeris generation stay separate offline commands, not remotely callable endpoints. Python receives neither PostgreSQL credentials nor public access credentials.

This increment provides research-only calendar/time endpoints, readiness connectivity to PostgreSQL, bounded/authenticated transport, a local Compose stack and tests. It does not implement user login, personal storage, approved data activation, pillars/daeun/compatibility, LLM or production deployment. `production_authorized` remains false; runtime configuration cannot turn it on.

Prior suggestions to make the whole main API FastAPI or to port the calculator to TypeScript are superseded. Historical research and numerical evidence are preserved.
