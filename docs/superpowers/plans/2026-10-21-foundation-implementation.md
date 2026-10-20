# S1 Foundation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Execute test-first in an isolated branch; record deviations and actual verification.

**Goal:** Deliver a runnable, offline research foundation for Korean date conversion, local-time normalization, solar-term records and validation.

**Architecture:** A Python package with small immutable contracts, state-isolated third-party adapters and a JSON stdin CLI. Acquiring sources is an explicit batch operation. Candidate datasets cannot authorize themselves for production.

**Tech Stack:** Python 3.13.5; korean-lunar-calendar 0.3.1; tzdata 2026.2; python-dateutil 2.9.0.post0; pytest 9.0.2. Optional Skyfield/JPL integration is separately tested when artifacts exist.

**Spec:** ../specs/2026-10-21-self-hosted-foundation-design.md

## Global Constraints

- No commercial fortune API, SDK, comparison call or fallback.
- Normalized Gregorian computational target: 1920-01-01 through 2050-12-31; solar-term guard years 1919–2051. This is not a verified production range.
- Preserve unknown leap flags, ambiguous times and input precision; never insert noon or current UTC+9.
- Preserve historical research, never rewrite its expected values to make tests pass.
- Do not publish raw restricted sources, kernels, credentials or personal inputs.
- Do not merge main or deploy. Work is delivered in a PR.
- Scientific accuracy, internal consistency, independent official comparison and production approval are separate.

## Review Focus

1. Upstream accepts nonexistent leap months: verify returned flags and reverse conversion.
2. JSON bool/float/overflow/duplicate keys must not become valid dates or provenance.
3. Time intervals spanning gaps/folds/skipped days require exact transitions, not hourly sampling.
4. Truncated, corrupt or redirected source files must never replace a valid artifact.
5. Empty/missing/self-derived evidence must not become independent validation or release approval.

## Task 1 — Contracts, serialization and errors

Files: `src/sazu/{errors,contracts,serde}.py`, `tests/test_core.py`.
Interfaces: `SourceManifest`, `UtcInterval`, `canonical_json`, `digest`, `parse_request`, `SazuError`.
- [ ] Write failures for malformed metadata, ambiguous JSON, invalid interval boundaries and sanitized errors.
- [ ] Run failing tests before implementation.
- [ ] Implement strict immutable contracts and canonical JSON.
- [ ] Run the focused suite and all tests; preserve command outputs.

## Task 2 — Korean calendar adapter

Files: `src/sazu/calendar.py`, `tests/test_calendar.py`.
Interfaces: `CalendarInput`, `CalendarDate`, `convert_calendar` -> `CalendarResult`.
- [ ] Test invalid dates, bool/float coercion, nonexistent/unknown leap month, stale-state isolation, boundary dates and concurrent calls.
- [ ] Observe failures, implement with fresh upstream instance and explicit setter success/identity checks.
- [ ] Run regression and finite-date round trips; label as self-consistency, not official certification.

## Task 3 — Pinned local-time normalization

Files: `src/sazu/{tzif,temporal}.py`, `tests/test_temporal.py`.
Interfaces: `load_zone`, `TimeInput`, `normalize_time` -> UTC interval union with tzdata/resource hashes.
- [ ] Test Korean historical offsets, gaps/folds, 23/25/24.5-hour dates, skipped dates, minute cells and range limits.
- [ ] Load package TZif bytes directly; ZoneInfo interprets offsets; parse structural transitions and expand supported POSIX tails.
- [ ] Assert unsupported rules fail closed. Do not claim global historic timezone accuracy.

## Task 4 — Source integrity and explicit acquisition

Files: `src/sazu/sources.py`, `tests/test_sources.py`.
Interfaces: `verify_file(path, manifest)`, `acquire_source(url, target, manifest, policy, transport)`.
- [ ] Fail tests for hash/size mismatch, missing files, symlinks, URL credentials/query, redirects off allowlist, partial reads and retry exhaustion.
- [ ] Implement no-follow bounded file reads, capped HTTPS batch acquisition and atomic no-overwrite publication.
- [ ] Run simulated transport tests without live network. Missing credentials do not authorize alternative providers.

## Task 5 — Solar-term records and optional astronomy

Files: `src/sazu/solar_terms.py`, `tests/test_solar_terms.py`, `tests/integration/test_skyfield_local.py`.
Interfaces: explicit 24-term mapping, `normalize_reference_record`, `compare_reference`, `validate_annual_terms`, `generate_terms`.
- [ ] Test KASI-index/longitude mapping, 24:00, fixed UTC+9, rounded-minute bounds and unknown precision.
- [ ] Implement record normalization and structural validation. Six-field record normalization is not a parser for the complete upstream TXT.
- [ ] Add offline Skyfield adapter with verified local BSP, builtin timescale identity, TT/UTC and exact coverage checks.
- [ ] Run numerical integration only with required packages/kernel; otherwise report skipped/blocked.

## Task 6 — Candidate validation and release denial

Files: `src/sazu/{validation,datasets}.py`, `tests/test_validation.py`.
Interfaces: calendar row comparison, artifact manifests, dataset candidate, blockers, production guard.
- [ ] Test missing/duplicate/different date rows, shared lineage, empty evidence, traversal, corrupt artifacts and forged approval flags.
- [ ] Implement candidate integrity with explicit evidence classifications.
- [ ] Keep production authorization unavailable until a trusted activation service is implemented; return a stable error.

## Task 7 — CLI, packaging, CI and handoff

Files: `src/sazu/{cli,__main__}.py`, `tests/test_cli.py`, `pyproject.toml`, requirements pins, `tools/check_calendar_range.py`, `.github/workflows/foundation.yml`, implementation report.
- [ ] Test real subprocess stdin/stdout, unknown fields, size bounds, sanitized errors and no saved input files.
- [ ] Run all tests freshly, compile, build wheel, wheel smoke and available finite-date checks.
- [ ] Record dependency versions, actual hashes, unsupported branches, official verification blocks and CI status separately.
- [ ] Upload tested bytes; verify Git blob IDs; create PR without merging.

## Execution record and deviations

The execution workspace was reset during delivery. The first eight source files were recovered byte-for-byte from Git tree `7a13f9f27554f6e617f87853c0b2437626f5d93f`. Unpublished files and tests were reconstructed and reverified. Final reported counts refer only to the retained final suite, not earlier ephemeral logs.

The installed Korean calendar library is 0.3.1, not the historical study's 0.4.0. The wrapper checks silent leap coercion explicitly. No official-range validation is inferred from this version change. Full wheel-hash dependency locking, Hypothesis and an independent reviewer remain outside the locally verified evidence. Exact version pins are not equivalent to an artifact hash lock.
