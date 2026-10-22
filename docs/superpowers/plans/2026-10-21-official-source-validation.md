# Official source validation — S1 continuation

> **For agentic workers:** Use superpowers:executing-plans; implement each task with an observed RED → GREEN cycle.

**Goal:** Parse the complete official KASI solar-term document and compare the S1 candidate model over the declared 1920–2050 interval without publishing upstream data or authorizing production.

**Architecture:** Extend the existing offline Python `sources`/`solar_terms`/`validation` boundary. Express remains unchanged; no acquisition, filesystem path, or batch computation is added to HTTP. Reference parsing and numerical comparison are separate from release authorization.

**Tech Stack:** Existing Python 3.13, pytest, Skyfield 1.55/JPL DE440s; existing Express/TypeScript regression suite. No commercial API and no new product dependency.

**Spec:** `docs/superpowers/specs/2026-10-21-self-hosted-foundation-design.md`, sections 6, 9, 12 (G1/G3). Preserve `docs/decisions/0002-express-python-boundary.md`.

## Global constraints
- Source TXT has 1920–2100 coverage; parsing it does NOT extend runtime calendar/solar-term support.
- Full upstream document and kernel must not enter Git or public CI artifacts.
- Check bytes, header/column semantics, mapping, complete key set, chronology, rollover and source clock before comparison.
- Numeric agreement, independently published reference, unknown ephemeris ancestry, rights review, and production authorization are different statuses.
- No fabricated official fixtures, no overwriting old research, no hidden widening of numerical tolerance.
- Stacked PR from PR #3 head `7f36c59`; no main merge or deployment.

## Review focus
1. A missing row outside the selected comparison window still invalidates the claimed complete source document (Task 1).
2. A re-labelled/mismatched candidate year or source version must not produce a green overlap-only report (Task 2).
3. Unknown rounding or a model reused as reference cannot establish an official comparison (Task 2).
4. Symlinks, truncated files, malformed/duplicate request keys and extra keys fail without leaking local paths (Task 3).
5. CI collection or comparison failures retain status/evidence and never become a production permit (Task 4).

### Task 1 — Complete document parser
**Files:** `src/sazu/kasi_reference.py`, `tests/test_kasi_reference.py`.
**Consumes:** `SourceManifest`, `normalize_reference_record`.
**Produces:** `KasiDocument`, `parse_kasi_document(raw: bytes, manifest: SourceManifest) -> KasiDocument`; `reference_events(document, start_year, end_year)`.
- [x] Write synthetic complete-year fixtures (clearly non-official) and fail tests for UTF-8/CP949, header mapping, counts, duplicates, chronology, invalid dates, 24:00 and out-of-window corruption.
- [x] Observe missing parser failure with `python -m pytest -q tests/test_kasi_reference.py`.
- [x] Implement strict parsing and full-document validation; do not change existing runtime supported years.
- [x] Run new and whole Python suites; commit.

### Task 2 — Evidence-aware range comparison
**Files:** `src/sazu/term_audit.py`, `tests/test_term_audit.py`.
**Consumes:** Parsed `KasiDocument`, computed `SolarTermEvent` sequence.
**Produces:** `compare_term_range(candidate, document, start_year, end_year) -> dict` with coverage, input identities, all mismatch keys/deltas, explicit ancestry and authorization status.
- [x] Write failures for missing/extra/duplicate entries, mixed source/model, non-computed candidates, strict minute-cell edges, mismatch order and deterministic report hashing.
- [x] Observe RED, implement deterministic reports and separate numeric outcome from production approval.
- [x] Run new and whole suites; commit.

### Task 3 — Offline batch CLI
**Files:** `src/sazu/source_audit.py`, `tests/test_source_audit.py`.
**Consumes:** stdin JSON plus local verified source/kernel paths and manifests.
**Produces:** `python -m sazu.source_audit inspect|compare`; structured JSON; exits 0 passed, 1 numeric mismatch, 2 invalid/missing/blocked, 3 unexpected failure.
- [x] Write failing real CLI subprocess tests for inspection, malformed requests, bounded reads, checksum/size/symlink failures; batch unit tests for comparison exit codes.
- [x] Read bounded reference bytes from one no-follow descriptor, parse those exact bytes, reuse local `generate_terms` with no network access.
- [x] Keep all paths and raw input out of error messages; inspect output contains metadata only, not raw dataset rows.
- [x] Run suites, Node build/tests and real service integration; commit.

### Task 4 — Full reference experiment and CI
**Files:** `tools/audit_official_terms.py`, `.github/workflows/official-validation.yml`, docs/implementation evidence.
**Consumes:** Explicit downloaded local files; fixed SHA-256 assertions and current source header.
**Produces:** 1920–2050 numerical audit summary, boundary-year structural checks, package/clock/model provenance. Only generated evidence summaries are uploaded.
- [x] Test runner arguments, expected source identities, missing files and output permissions before implementation.
- [x] Acquire upstream files separately in CI with fixed official URLs, limits and hash checks. No keys or commercial sources.
- [x] Run full comparison and preserve every mismatch; do not rewrite expectations or silently accept changed source files.
- [x] Record real results, independent-reference limitations and remaining KASI lunar/API/rights blockers; commit, push stacked Draft PR and inspect CI.

## Rulings
This continues the already approved S1 source-validation scope rather than silently choosing S2 day-boundary/daeun conventions. The user requested implementation in this turn; execution is inline because no native subagent is available. Source material was inspected read-only first. Original Python core tests: 221 passed, 1 existing kernel-dependent skip. The runtime cannot clone GitHub directly (DNS failure), so a read-only GitHub Actions source archive and pinned public wheels were used in a fresh isolated local repository. No user's workstation state was modified.

## Follow-up diagnostic, prompted by observed numeric failures
The first full official experiment (code `5902127`, CI `39561466679`) produced 2,830 minute-cell matches and 314 mismatches. All mismatches are negative relative to the displayed reference; 283 occur before 1972. This is evidence, not permission to change the model. Add `tools/diagnose_term_clocks.py` with ten failing-first tests to compare the unchanged UTC result against a separately labelled UT1-display hypothesis using the same TT events and built-in time model. It cannot mark a release approved or change the original audit's failed gate. Improved fit would NOT prove that the reference uses UT1. Record the outcome and source clock ambiguity without fitting a correction.

## Execution outcome
Implementation/tests and both full official-source experiments were executed. Numeric agreement gate FAILED: 2830 matching cells /3144, 314 mismatches. This is not a completed production approval. See `../../implementation/official-source-validation.md` and `../../implementation/official-validation-20261021.json`. Diagnostic RED10 → GREEN10, whole Python suite323 passed/1 existing kernel skip; no operational model changed. New independent reviewer unavailable/not run.
