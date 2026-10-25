"""Research-only missing-frame checks; synthetic EOP rows are not observations."""
import math
from pathlib import Path

import erfa
import numpy as np
import pytest

from tools import iers_legacy_frame_audit as a
from tools import horizons_frame_reconciliation as old

ROOT = Path(__file__).resolve().parents[1]


def row(mjd, flag='I', dpsi=40., deps=-7.):
    year, month, day, _ = erfa.jd2cal(2400000.5, float(mjd))
    fields = list(' ' * 187)
    def put(start, end, value):
        fields[start-1:end] = list(value.rjust(end-start+1))
    put(1, 2, str(year % 100)); put(3, 4, str(month)); put(5, 6, str(day))
    put(8, 15, f'{mjd:.2f}'); put(96, 96, ' ' if dpsi is None and deps is None else flag)
    if dpsi is not None:
        put(98, 106, f'{dpsi:.3f}'); put(107, 115, '0.500')
    if deps is not None:
        put(117, 125, f'{deps:.3f}'); put(126, 134, '0.300')
    return ''.join(fields)


def test_fixed_width_legacy_units_and_missing_are_not_zero():
    records = a.parse_finals(row(60635, 'P', 40., -7.)+'\n'+row(60636, dpsi=None, deps=None))
    assert records[0].dpsi_mas == 40.
    assert records[0].flag == 'P'
    assert records[1].dpsi_mas is None
    assert records[1].deps_mas is None


@pytest.mark.parametrize('text', [
    row(60635)+'\n'+row(60635), row(60635)+'\n'+row(60637),
    row(60635, flag='X'), row(60635, dpsi=math.nan),
    row(60635).replace('241121', '241122', 1),
    row(60635, dpsi=None, deps=0.),
])
def test_malformed_or_mixed_source_fails(text):
    with pytest.raises(a.AuditError):
        a.parse_finals(text)


def test_snapshot_verification_rejects_caller_chosen_hash(tmp_path):
    import hashlib
    p = tmp_path/'finals.all'; p.write_text(row(60635)+'\n'+row(60636))
    with pytest.raises(a.AuditError):
        a.load_source(p, hashlib.sha256(p.read_bytes()).hexdigest())


def test_tt_to_utc_mjd_does_not_use_tai_or_ut1():
    utc1, utc2 = erfa.dtf2d('UTC', 2024, 11, 21, 12, 0, 0.)
    tai1, tai2 = erfa.utctai(utc1, utc2)
    tt1, tt2 = erfa.taitt(tai1, tai2)
    sample = a.sample(a.parse_finals(row(60635, 'P', 40., -7.)+'\n'+row(60636, 'I', 42., -3.)), float(tt1+tt2))
    assert sample['mjd_utc'] == pytest.approx(60635.5, abs=1e-9)
    assert sample['dpsi_mas'] == pytest.approx(41., abs=1e-8)
    assert sample['deps_mas'] == pytest.approx(-5., abs=1e-8)
    assert sample['nutation_flags'] == ['P', 'I']
    assert sample['prediction_in_bracket'] is True
    assert sample['endpoint_offsets_mas'] == [[40., -7.], [42., -3.]]


def test_no_extrapolation_or_missing_field_fill():
    records = a.parse_finals(row(60635)+'\n'+row(60636, dpsi=None, deps=None))
    for tt in [2437729.5625434765, 2460636.3317007776]:
        result = a.sample(records, tt)
        assert result['status'] == 'unavailable'
        assert 'dpsi_mas' not in result


def test_zero_offset_reproduces_pr12_and_corrected_rotation_is_proper():
    for tt in [2437729.5625434765, 2451545., 2460636.3317007776]:
        base = a.matrix(tt, 0., 0.)
        assert np.allclose(base, old.iau1976_1980_ecliptic_matrix(tt), rtol=0, atol=4e-16)
        rot = a.matrix(tt, 123., -42.)
        assert np.allclose(rot@rot.T, np.eye(3), rtol=0, atol=1e-14)
        assert np.linalg.det(rot) == pytest.approx(1., abs=1e-14)


def test_analytic_longitude_response_and_deps_cancellation():
    # ERFA numat rotation order independently implies +dPsi, not dX/sin(eps).
    tt = 2460636.3317007776
    for v in [[1., 0., 0.], [0., -1., .2], [1., 1., 1.]]:
        base = old.ecliptic_longitude_deg(a.matrix(tt, 0., 0.), v)
        for dpsi, deps in [(40., -7.), (-113., 300.), (0., 10000.)]:
            angle = old.ecliptic_longitude_deg(a.matrix(tt, dpsi, deps), v)
            assert old.wrap_degrees(angle, base)*3_600_000 == pytest.approx(dpsi, abs=4e-7)


@pytest.mark.parametrize('values', [(math.nan, 0.), (0., math.inf), (True, 0.)])
def test_nonfinite_offsets_rejected(values):
    with pytest.raises(a.AuditError):
        a.matrix(2460636.3317007776, *values)


def test_frozen_twenty_cases_and_release_gate_are_preserved():
    rows = a.load_cases(ROOT/'data/verification/horizons_20_central_observations_20261023.json',
                        ROOT/'data/verification/modern_20_naoj_cases_20261023.json')
    assert len(rows) == 20
    report = a.audit(rows, a.parse_finals(row(60635)+'\n'+row(60636)),
                     {'source_sha256': a.SOURCE_SHA256})
    assert report['production_authorized'] is False
    assert report['release_approval'] == 'BLOCKED'
    assert report['horizons_frame_reproduced'] is False
    assert report['newly_resolved_case_count'] == 0
    assert report['unavailable_count'] == 19
    assert all(s['production_authorized'] is False for s in report['samples'])
