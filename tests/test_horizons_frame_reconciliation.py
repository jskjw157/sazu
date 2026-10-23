"""Uncorrected IAU76/80 model is not Horizons' EOP-corrected frame."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from tools import horizons_frame_reconciliation as f

BASE = Path(__file__).resolve().parents[1]
FIXTURE = BASE / 'data/verification/horizons_20_central_observations_20261023.json'
CASES = BASE / 'data/verification/modern_20_naoj_cases_20261023.json'


def test_report_fixture_has_all_20_immutable_research_cases():
    cases = f.load_cases(FIXTURE, CASES)
    assert len(cases) == 20
    assert len({(c['year'], c['kasi_term_id']) for c in cases}) == 20
    assert all(c['horizons_obs_ecliptic_lon_deg'] != c['skyfield_2000b_ecliptic_lon_deg']
               for c in cases)


def test_modified_or_incomplete_evidence_fails_closed(tmp_path):
    doc = json.loads(FIXTURE.read_text())
    for item in ({**doc, 'production_authorized': True},
                 {**doc, 'source_report_sha256': '0' * 64},
                 {**doc, 'rows': doc['rows'][:-1]},
                 {**doc, 'rows': doc['rows'][:-1] + [doc['rows'][0]]},
                 {**doc, 'rows': [{**doc['rows'][0], 'tt_jd': float('nan')}] + doc['rows'][1:]}):
        path = tmp_path / 'research.json'
        path.write_text(json.dumps(item))
        with pytest.raises(f.EvidenceError):
            f.load_cases(path, CASES)


def test_rejects_reference_case_substitution(tmp_path):
    refs = json.loads(CASES.read_text())
    refs['cases'][0]['year'] = 1991
    altered = tmp_path / 'references.json'
    altered.write_text(json.dumps(refs))
    with pytest.raises(f.EvidenceError):
        f.load_cases(FIXTURE, altered)


def test_erfa_1980_rotation_is_a_real_orthogonal_matrix():
    m = f.iau1976_1980_ecliptic_matrix(2451545.0)
    assert m.shape == (3, 3)
    assert np.allclose(m @ m.T, np.eye(3), rtol=0, atol=1e-13)
    assert abs(np.linalg.det(m) - 1) < 1e-13
    assert np.isclose(np.linalg.norm(m @ [1., 0., 0.]), 1.)


def test_julian_epoch_and_vector_validation_prevent_false_matches():
    for tt in (True, float('nan'), 1., float('inf'), '2451545'):
        with pytest.raises(f.EvidenceError):
            f.iau1976_1980_ecliptic_matrix(tt)
    for vec in ([0, 0, 0], [float('nan'), 0, 1], [1, 1], 'invalid'):
        with pytest.raises(f.EvidenceError):
            f.ecliptic_longitude_deg(np.eye(3), vec)


def test_ecliptic_zero_and_quadrant_normalization():
    m = np.eye(3)
    assert f.ecliptic_longitude_deg(m, [1, 0, 0]) == pytest.approx(0)
    assert f.ecliptic_longitude_deg(m, [0, -1, 0]) == pytest.approx(270)
    assert f.wrap_degrees(359.9999, 0.0001) == pytest.approx(-0.0002)


def test_erfa_vs_skyfield_same_photon_vector_uses_different_frames():
    from skyfield.api import load
    from skyfield.framelib import ecliptic_frame
    from skyfield.nutationlib import iau2000b_radians
    ts = load.timescale(builtin=True)
    t = ts.tt_jd(2460636.3317007776)
    t._nutation_angles_radians = iau2000b_radians(t)
    sf = ecliptic_frame.rotation_at(t)
    unit_icrf = sf.T @ np.array([-0.5, -math.sqrt(3) / 2, 0.])
    lon_old = f.ecliptic_longitude_deg(f.iau1976_1980_ecliptic_matrix(t.tt),
                                       unit_icrf)
    lon_new = f.ecliptic_longitude_deg(sf, unit_icrf)
    assert abs(f.wrap_degrees(lon_old, lon_new) * 3600) > .025


def test_release_stays_blocked_after_synthetic_diagnostics():
    rows = [{'year': 2024, 'kasi_term_id': 20, 'tt_jd': 2460636.3317007776,
             'horizons_obs_ecliptic_lon_deg': 239.9999873,
             'skyfield_2000b_ecliptic_lon_deg': 240.0000000029}]
    measured = [{'year': 2024, 'kasi_term_id': 20, 'skyfield_2000b_deg': 240.,
                 'skyfield_2000a_deg': 240.0000001,
                 'erfa_uncorrected_1976_1980_deg': 240.00001}]
    report = f.summarize(rows, measured, {'kernel_sha256': 'a' * 64})
    assert report['status'] == 'diagnostic_only'
    assert report['production_authorized'] is False
    assert report['horizons_frame_includes_eop'] is True
    assert report['erfa_1976_1980_is_horizons_matched'] is False
    assert report['samples'][0]['horizons_minus_raw_1976_1980_arcsec'] == pytest.approx(-.08172, abs=1e-5)
