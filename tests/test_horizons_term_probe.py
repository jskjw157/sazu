"""Tests for an explicit research-only JPL Horizons diagnostic (no live network)."""
import json
from pathlib import Path

import pytest

from tools import horizons_term_probe as hp

ROOT = Path(__file__).resolve().parents[1]


def test_exact_20_tt_epochs_are_present_and_not_production_approved():
    epochs=hp.load_epochs(ROOT/'data/verification/modern_20_tt_epochs_20261023.json',
                          ROOT/'data/verification/modern_20_naoj_cases_20261023.json')
    assert len(epochs)==20
    assert epochs[0].year==1962 and epochs[0].term_id==3
    assert epochs[-1].year==2024 and epochs[-1].term_id==20
    assert len({(e.year,e.term_id) for e in epochs})==20
    assert all(e.tt_jd>2400000 for e in epochs)


def test_epochs_reject_missing_changed_and_unverified_case_manifest(tmp_path):
    source=json.loads((ROOT/'data/verification/modern_20_tt_epochs_20261023.json').read_text())
    cases=ROOT/'data/verification/modern_20_naoj_cases_20261023.json'
    for changes in ({'production_authorized': True},
                    {'base_probe_sha256':'0'*64},
                    {'epochs':source['epochs'][:-1]},
                    {'epochs':source['epochs'][:-1]+[source['epochs'][0]]},
                    {'epochs':[{**r,'tt_jd':float('nan')} if i==0 else r for i,r in enumerate(source['epochs'])]}):
        path=tmp_path/'tampered.json'
        path.write_text(json.dumps({**source,**changes}))
        with pytest.raises(hp.ProbeError):
            hp.load_epochs(path,cases)


def test_api_queries_use_explicit_scales_centres_and_distinct_frame_contracts():
    observer=hp.make_query('observer',[2460636.0,2460636.0001])
    vector=hp.make_query('vector',[2460636.0,2460636.0001])
    assert observer['EPHEM_TYPE']=='OBSERVER'
    assert observer['TIME_TYPE']=='TT'
    assert observer['TLIST_TYPE']=='JD'
    assert observer['QUANTITIES']=='31'
    assert observer['CENTER']=='500@399'
    assert observer['COMMAND']=='10'
    assert observer['APPARENT']=='AIRLESS'
    assert observer['TLIST']=="'2460636.0000000000','2460636.0001000000'"
    assert vector['EPHEM_TYPE']=='VECTORS'
    assert vector['TIME_TYPE']=='TDB'
    assert vector['VEC_CORR']=='NONE'
    assert vector['REF_PLANE']=='FRAME'
    assert vector['REF_SYSTEM']=='ICRF'
    assert vector['OUT_UNITS']=='AU-D'
    assert vector['VEC_TABLE']=='1'
    assert 'QUANTITIES' not in vector
    assert 'START_TIME' not in observer and 'STOP_TIME' not in vector


def test_jpl_observer_output_accepts_only_explicit_jd_lon_lat_rows():
    response="""Solar quantities: ObsEcLon ObsEcLat
$$SOE
2460636.331700780, , 239.999994882, -0.00001,
2460636.331800780, , 240.002100001, -0.00002,
$$EOE
"""
    rows=hp.parse_observer(response,[2460636.33170078,2460636.33180078])
    assert rows==pytest.approx([239.999994882,240.002100001])
    with pytest.raises(hp.ProbeError):
        hp.parse_observer(response,[2460636.33170078])
    with pytest.raises(hp.ProbeError):
        hp.parse_observer(response.replace('239.999994882','not-a-number'),[2460636.33170078,2460636.33180078])
    with pytest.raises(hp.ProbeError):
        hp.parse_observer(response.replace('2460636.331800780','2460636.441800780'),[2460636.33170078,2460636.33180078])
    with pytest.raises(hp.ProbeError):
        hp.parse_observer('INVALID DATA', [2460636.33170078])


def test_jpl_vectors_require_jd_and_three_au_components():
    response="""Coordinate system: ICRF
$$SOE
2460636.331701234 = A.D. 2024-Nov-22 (TDB)
 X = 3.14000000000E-01 Y = -2.7100000000000E-01 Z = 5.00000000000E-03
2460636.331801234 = A.D. 2024-Nov-22 (TDB)
 X = 3.14020000000E-01 Y = -2.7110000000000E-01 Z = 5.10000000000E-03
$$EOE
"""
    rows=hp.parse_vectors(response,[2460636.331701234,2460636.331801234])
    assert rows==[(.314,-.271,.005),(.31402,-.2711,.0051)]
    with pytest.raises(hp.ProbeError):
        hp.parse_vectors(response.replace('Z = 5.00000000000E-03','Q = 5.00000000000E-03'),
                         [2460636.331701234,2460636.331801234])
    with pytest.raises(hp.ProbeError):
        hp.parse_vectors(response,[2460636.331701234])


def test_wrapped_angular_differences_and_local_crossing_offset():
    assert hp.delta_degrees(0.0001,359.9999)==pytest.approx(.0002)
    assert hp.delta_degrees(359.9999,.0001)==pytest.approx(-.0002)
    slope = .9856 / 86400
    target=315.
    offset_seconds=7.
    centre=target + slope*offset_seconds
    a=hp.estimate_crossing(target,centre-slope*120,centre,centre+slope*120)
    assert a['interpolated_tt_offset_seconds']==pytest.approx(-7,abs=.001)
    assert a['bracketed'] is True
    far=hp.estimate_crossing(target,target-.01,target-.01,target-.01)
    assert far['bracketed'] is False
    assert far['interpolated_tt_offset_seconds'] is None


def test_diagnostic_never_becomes_authorized_and_rejects_missing_samples():
    from types import SimpleNamespace
    epochs=[SimpleNamespace(year=2024,term_id=20,tt_jd=2460636.3317007776)]
    local=[{'tt_jd':2460636.3317007776,'skyfield_true_date_lon':240.0,
            'skyfield_geometric_vector':[1,0,0], 'tdb_jd':2460636.3317008}]
    angle=240.0
    slope=.9856 / 86400
    summary=hp.make_report(epochs,local,[[angle-slope*120,angle,angle+slope*120]],[(1,0,0)],
                           {'observer_sha256':'a'*64,'vector_sha256':'b'*64,'observer_header':'DE441','vector_header':'DE441'})
    assert summary['status']=='diagnostic_only'
    assert summary['production_authorized'] is False
    assert summary['comparison']['longitude_frames_directly_interchangeable'] is False
    assert summary['rows'][0]['vector_icrf_difference_au']==pytest.approx(0)
    assert summary['rows'][0]['horizons_iau76_80_tt_offset_s']==pytest.approx(0,abs=.1)
    assert summary['rows'][0]['proves_physical_tt_error'] is False
    with pytest.raises(hp.ProbeError):
        hp.make_report(epochs,local,[],[],{})


def test_no_network_get_in_tests_and_reject_non_horizons_url():
    with pytest.raises(hp.ProbeError):
        hp.validate_url('https://example.com/api/horizons.api')
    assert hp.validate_url('https://ssd.jpl.nasa.gov/api/horizons.api') is None


def test_chunked_horizons_queries_preserve_all_60_tt_samples(monkeypatch):
    jds=[2460000.0+i/1000.0 for i in range(60)]
    batches=[]
    def fake_fetch(query):
        values=[float(v.strip("\"'")) for v in query['TLIST'].split(',')]
        assert len(values)<=9
        assert query['TIME_TYPE']=='TT'
        batches.append(values)
        header='Observer quantity #31 ObsEcLon ObsEcLat\n$$SOE\n'
        rows=''.join(f'{jd:.9f}, , 240.00000000, 0.00,\n' for jd in values)
        return header+rows+'$$EOE\n','a'*64
    monkeypatch.setattr(hp,'fetch_horizons',fake_fetch)
    values,evidence=hp.fetch_and_parse_batched('observer',jds)
    assert len(values)==len(jds)==60
    assert len(evidence)==7
    assert sum(d['count'] for d in evidence)==60
    assert [v for batch in batches for v in batch]==pytest.approx(jds,abs=1e-8)


def test_chunked_vector_query_rejects_missing_row_and_preserves_tdb(monkeypatch):
    jds=[2460000.0+i/1000.0 for i in range(20)]
    def fake_fetch(query):
        vals=[float(v.strip("\"'")) for v in query['TLIST'].split(',')]
        assert query['TIME_TYPE']=='TDB'
        text='ICRF frame\n$$SOE\n'
        for j in vals:
            text+=f'{j:.9f} = A.D. 2023-Jan-01 (TDB)\n X = 1.0E+00 Y = 0.0E+00 Z = 0.0E+00\n'
        return text+'$$EOE\n','b'*64
    monkeypatch.setattr(hp,'fetch_horizons',fake_fetch)
    values,evidence=hp.fetch_and_parse_batched('vector',jds)
    assert len(values)==20 and len(evidence)==3
    assert all(v==(1.,0.,0.) for v in values)
    def missing(_):return 'ICRF frame\n$$SOE\n$$EOE\n','b'*64
    monkeypatch.setattr(hp,'fetch_horizons',missing)
    with pytest.raises(hp.ProbeError):
        hp.fetch_and_parse_batched('vector',jds)
