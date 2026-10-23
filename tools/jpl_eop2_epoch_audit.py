"""Research-only JPL EOP2 evidence at the exact archived solar-term TT events.

JPL EOP2 dX/dY are celestial pole offsets in milliarcseconds relative
to IAU 2006/2000A, NOT corrections to the Horizons IAU76/80 ecliptic
longitude. Do not retrofit these to a production saju calculation.

The EOP2 file explicitly labels its Julian epochs MJD(TAI). Sampling an
ephemeris TT event therefore uses MJD(TAI) = JD(TT) - 2400000.5 -
32.184/86400. We do not substitute UTC, UT1 or calendar-day lookups.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

SHA_FROZEN_OCT22 = "ec0077f51f1cc7705265940f9dea7426996d38c06fd13f811e459eecb31d4525"
ARCHIVED_TT_PROBE_SHA256 = "5c33bcb86f9ad8aa59a128994860fa52f32883d490c8bce1da1c2a7fdfe1025f"
MAX_BYTES = 6_710_886
TT_MINUS_TAI_SECONDS = 32.184
_FRAME = "IAU 2006/2000A"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class EopEvidenceError(ValueError):
    """Unreviewed, mixed-frame, malformed, or incomplete research source."""


@dataclass(frozen=True)
class EopRow:
    mjd_tai: float
    pmx_mas: float
    pmy_mas: float
    tai_minus_ut1_ms: float
    dx_mas: float
    dy_mas: float
    dx_sigma_mas: float
    dy_sigma_mas: float
    calendar_label: str


def parse_eop2(text: str) -> tuple[tuple[EopRow, ...], dict]:
    """Read the full long EOP2 record; fail on gaps, duplicates or format drift."""
    if type(text) is not str or not 0 < len(text) <= MAX_BYTES:
        raise EopEvidenceError("Unexpected source text size/type")
    if ("EOP2PNM='IAU 2006/2000A'" not in text
        or "EOP2UT1='UT1'" not in text
        or "$ MJD" not in text and "$   MJD" not in text):
        raise EopEvidenceError("EOP2 frame or time convention not established")
    lines = text.splitlines()
    starts = [i for i, s in enumerate(lines) if s.strip() == "EOP2="]
    ends = [i for i, s in enumerate(lines) if s.strip() == "$END"]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise EopEvidenceError("EOP2 bounds missing or duplicated")
    if any(s.strip() for s in lines[ends[0] + 1:]):
        raise EopEvidenceError("Trailing unaccounted EOP2 content")
    records = []
    prev_mjd = None
    for line in lines[starts[0] + 1: ends[0]]:
        if not line.strip() or line.lstrip().startswith("$"):
            raise EopEvidenceError("Unexpected EOP2 row/comment")
        columns, symbol, annotation = line.partition("$")
        if not symbol or not columns.rstrip().endswith(","):
            raise EopEvidenceError("EOP2 row lacks verifiable calendar label")
        values = [item.strip() for item in columns.split(",")]
        if values[-1] != "":
            raise EopEvidenceError("Malformed EOP2 row termination")
        values.pop()
        if len(values) != 15:
            raise EopEvidenceError("EOP2 column count changed")
        try:
            cols = [float(value) for value in values]
        except ValueError as exc:
            raise EopEvidenceError("Non-numeric EOP2 field") from exc
        if not all(math.isfinite(x) for x in cols):
            raise EopEvidenceError("Nonfinite EOP2 field")
        mjd = cols[0]
        date_text = annotation.strip()
        if (not mjd.is_integer() or not 35000 <= mjd <= 70000
            or not _DATE.fullmatch(date_text)):
            raise EopEvidenceError("Unexpected EOP2 day index/date")
        try:
            datetime.fromisoformat(date_text)
        except ValueError as exc:
            raise EopEvidenceError("Invalid EOP2 calendar label") from exc
        if prev_mjd is not None and mjd != prev_mjd + 1:
            raise EopEvidenceError("EOP2 missing or duplicate MJD(TAI) date")
        prev_mjd = mjd
        records.append(EopRow(
            mjd_tai=mjd, pmx_mas=cols[1], pmy_mas=cols[2],
            tai_minus_ut1_ms=cols[3], dx_mas=cols[10], dy_mas=cols[11],
            dx_sigma_mas=cols[12], dy_sigma_mas=cols[13],
            calendar_label=date_text
        ))
        if len(records) > 30000:
            raise EopEvidenceError("Too many rows in EOP2 dataset")
    if len(records) < 2:
        raise EopEvidenceError("Incomplete EOP2 range")
    return tuple(records), {
        "schema_version": 1, "source": "JPL EOP2",
        "frame": _FRAME, "dxdy_model": "IAU2006/2000A_CIP_offsets",
        "time_argument": "MJD(TAI)", "dxdy_unit": "milliarcsecond",
        "row_count": len(records), "first_mjd_tai": records[0].mjd_tai,
        "last_mjd_tai": records[-1].mjd_tai,
        "source_sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
        "production_authorized": False
    }


def load_verified_source(path: Path, *, expected_sha256: str) -> tuple[tuple[EopRow, ...], dict]:
    """Never trust a path based on its file extension; verify bytes before parsing."""
    if not isinstance(path, Path) or type(expected_sha256) is not str or not _DIGEST.fullmatch(expected_sha256):
        raise EopEvidenceError("Missing pinned source identity")
    fd = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            fd = None
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
                raise EopEvidenceError("Not a bounded regular EOP2 file")
            data = handle.read(MAX_BYTES + 1)
            if len(data) != info.st_size:
                raise EopEvidenceError("EOP2 file size changed during read")
    except OSError as exc:
        raise EopEvidenceError("EOP2 file unavailable or unsafe") from exc
    finally:
        if fd is not None:
            os.close(fd)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise EopEvidenceError("EOP2 snapshot digest mismatch")
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise EopEvidenceError("EOP2 text encoding is not ASCII") from exc
    rows, identity = parse_eop2(text)
    if identity["source_sha256"] != actual:
        raise EopEvidenceError("Inconsistent source bytes")
    return rows, identity


def project_dxdy(rows: tuple[EopRow, ...], tt_jd: float) -> dict:
    """Linear research sample in TAI, never the Horizons EOP interpolation claim."""
    if (type(tt_jd) is not float or not math.isfinite(tt_jd)
        or not 2400000 < tt_jd < 2500000
        or not isinstance(rows, tuple) or len(rows) < 2):
        raise EopEvidenceError("Invalid epoch or source series")
    mjd_tai = tt_jd - 2400000.5 - TT_MINUS_TAI_SECONDS / 86400.0
    indices = [r.mjd_tai for r in rows]
    idx = bisect_right(indices, mjd_tai) - 1
    if idx < 0 or idx >= len(rows) - 1 or not indices[idx] <= mjd_tai < indices[idx + 1]:
        raise EopEvidenceError("TT epoch outside EOP source support")
    current, after = rows[idx], rows[idx+1]
    span = after.mjd_tai - current.mjd_tai
    if span != 1:
        raise EopEvidenceError("EOP2 series is not consecutive")
    frac = (mjd_tai - current.mjd_tai) / span

    def lerp(field: str) -> float:
        return (1 - frac) * getattr(current, field) + frac * getattr(after, field)

    return {
        "mjd_tai": mjd_tai, "source_bracket_mjd_tai": [current.mjd_tai, after.mjd_tai],
        "dx_mas": lerp("dx_mas"), "dy_mas": lerp("dy_mas"),
        "dx_sigma_mas": lerp("dx_sigma_mas"), "dy_sigma_mas": lerp("dy_sigma_mas"),
        "pmx_mas": lerp("pmx_mas"), "pmy_mas": lerp("pmy_mas"),
        "tai_minus_ut1_ms": lerp("tai_minus_ut1_ms"),
        "interpolation": "linear_MJD_TAI", "interpolation_horizons_matched": False,
        "offset_reference": "IAU2006/2000A_CIP_offsets",
        "usable_as_iau76_80_correction": False, "production_authorized": False
    }


def _read_small_json(path: Path) -> dict:
    try:
        if path.is_symlink() or path.stat().st_size > 131072:
            raise EopEvidenceError("Research JSON is symlink or oversized")
        result = json.loads(path.read_text("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(EopEvidenceError("Nonfinite JSON value")))
    except (OSError, ValueError) as exc:
        raise EopEvidenceError("Cannot read research JSON") from exc
    if type(result) is not dict:
        raise EopEvidenceError("Expected a research JSON object")
    return result


def load_20_epochs(epoch_path: Path, reference_path: Path) -> list[dict]:
    epochs, reference = _read_small_json(epoch_path), _read_small_json(reference_path)
    if (epochs.get("research_only") is not True or epochs.get("production_authorized") is not False
        or epochs.get("base_probe_sha256") != ARCHIVED_TT_PROBE_SHA256
        or reference.get("production_authorized") is not False
        or reference.get("release_approval") != "BLOCKED"
        or reference.get("research_only") is not True):
        raise EopEvidenceError("Research identity/policy mismatch")
    series, published = epochs.get("epochs"), reference.get("cases")
    if type(series) is not list or type(published) is not list or len(series) != 20 or len(published) != 20:
        raise EopEvidenceError("Expected all 20 research cases")
    keys, prior = set(), float("-inf")
    result = []
    for event in series:
        y, k, jd = event.get("year"), event.get("kasi_term_id"), event.get("tt_jd")
        if (type(y) is not int or not 1960 <= y <= 2025
            or type(k) is not int or not 1 <= k <= 24
            or type(jd) is not float or not math.isfinite(jd)
            or jd <= prior or (y, k) in keys):
            raise EopEvidenceError("TT epochs malformed or unordered")
        result.append({"year": y, "kasi_term_id": k, "tt_jd": jd})
        prior, keys = jd, keys | {(y, k)}
    published_keys = {(r["year"], r["kasi_term_id"]) for r in published}
    if len(published_keys) != 20 or keys != published_keys or not all(r.get("production_authorized") is False for r in published):
        raise EopEvidenceError("Published comparison case identities differ")
    return result


def summarize_projection(epochs: list[dict], projected: list[dict], source: dict) -> dict:
    if (not epochs or len(epochs) != len(projected)
        or source.get("frame") != _FRAME or source.get("production_authorized") is not False):
        raise EopEvidenceError("Research model mismatch")
    samples = []
    for item, value in zip(epochs, projected):
        if (value.get("production_authorized") is not False
            or value.get("usable_as_iau76_80_correction") is not False
            or value.get("interpolation") != "linear_MJD_TAI"):
            raise EopEvidenceError("Unsafe EOP projection")
        samples.append({**item, **value})
    return {
        "schema_version": 1, "status": "research_only",
        "research_only": True, "production_authorized": False,
        "release_approval": "BLOCKED",
        "source": source, "epoch_count": len(samples),
        "coordinate_frame_equivalence_proved": False,
        "corrected_horizons_longitudes": [],
        "method": "linear dX/dY sample from explicit MJD(TAI), not JPL interpolation or IAU76/80 frame transform",
        "zero_dxdy_epoch_count": sum(float(r["dx_mas"]) == 0. and float(r["dy_mas"]) == 0. for r in samples),
        "max_abs_dx_mas": max(abs(float(r["dx_mas"])) for r in samples),
        "max_abs_dy_mas": max(abs(float(r["dy_mas"])) for r in samples),
        "epochs": samples
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eop", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--epochs", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        records, source = load_verified_source(args.eop, expected_sha256=args.source_sha256)
        event_rows = load_20_epochs(args.epochs, args.cases)
        projected = [project_dxdy(records, e["tt_jd"]) for e in event_rows]
        source["snapshot_verification"] = "hash_verified_before_parse"
        report = summarize_projection(event_rows, projected, source)
        report["research_executed_at_utc"] = datetime.now(UTC).isoformat()
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "epoch_count": len(projected),
                          "zero_dxdy_epoch_count": report["zero_dxdy_epoch_count"],
                          "max_abs_dx_mas": report["max_abs_dx_mas"],
                          "max_abs_dy_mas": report["max_abs_dy_mas"],
                          "production_authorized": False}))
        return 0
    except (EopEvidenceError, KeyError, TypeError, ValueError, OSError) as error:
        args.output.write_text(json.dumps({"status": "blocked", "production_authorized": False,
                                           "error": type(error).__name__})+"\n", encoding="utf-8")
        print(json.dumps({"status": "blocked", "production_authorized": False,
                          "error": type(error).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
