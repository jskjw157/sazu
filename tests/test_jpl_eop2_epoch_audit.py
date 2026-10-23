"""JPL EOP2 must stay a provenance-checked research source, not an ephemeris fix."""
from pathlib import Path
import math
import pytest

from tools import jpl_eop2_epoch_audit as a

HEADER = """ $ JPL Earth Orientation Parameter 2 (EOP2) File
 EOP2PNM='IAU 2006/2000A'
 EOP2UT1='UT1'
 $ MJD(TAI),PMX(mas),PMY(mas),TAI-UT1(ms),...,DX(mas),DY(mas)
 EOP2=
"""
def row(mjd, dx, dy, day):
    values = [float(mjd),10.,11.,37000.,1.,1.,1.,0.,0.,0.,
              float(dx),float(dy),.05,.06,0.]
    return " " + ", ".join(str(v) for v in values) + f", $ {day}\n"

SAMPLE = HEADER + row(60000, .1, -.2, '2023-02-25') + \
         row(60001, .3, .1, '2023-02-26') + \
         row(60002, .5, .2, '2023-02-27') + " $END\n"


def test_source_models_are_not_mislabeled_as_old_iau76_80():
    records, identity = a.parse_eop2(SAMPLE)
    assert len(records) == 3
    assert identity["frame"] == "IAU 2006/2000A"
    assert identity["dxdy_model"] == "IAU2006/2000A_CIP_offsets"
    assert identity["production_authorized"] is False
    assert records[0].mjd_tai == pytest.approx(60000.)
    assert records[0].dx_mas == pytest.approx(.1)
    assert records[0].dy_mas == pytest.approx(-.2)


def test_tai_mjd_conversion_and_interpolation_are_not_utc_or_ut1():
    records, _ = a.parse_eop2(SAMPLE)
    # The source time is explicitly MJD(TAI); TT exceeds TAI by 32.184 seconds.
    tt_jd = 2400000.5 + 60000.5 + 32.184/86400
    projected = a.project_dxdy(records, tt_jd)
    assert projected["mjd_tai"] == pytest.approx(60000.5, abs=1e-8)
    assert projected["dx_mas"] == pytest.approx(.2)
    assert projected["dy_mas"] == pytest.approx(-.05)
    assert projected["interpolation"] == "linear_MJD_TAI"
    assert projected["usable_as_iau76_80_correction"] is False
    assert projected["production_authorized"] is False


@pytest.mark.parametrize("bad",[
    SAMPLE.replace("IAU 2006/2000A","IAU 1976/1980"),
    SAMPLE.replace("60001.0", "60000.0"),
    SAMPLE.replace("60001.0", "60003.0"),
    SAMPLE.replace("0.3, 0.1", "NaN, 0.1"),
    SAMPLE.replace("$END", ""),
])
def test_malformed_or_gapped_source_fails_closed(bad):
    with pytest.raises(a.EopEvidenceError):
        a.parse_eop2(bad)


def test_tt_input_validation_refuses_nonfinite_or_outside_coverage():
    records,_=a.parse_eop2(SAMPLE)
    for jd in (None, True, "2460000.5", float("nan"),
               2400000.5 + 59999 +32.184/86400,
               2400000.5 + 60002.5 +32.184/86400):
        with pytest.raises(a.EopEvidenceError):
            a.project_dxdy(records, jd)


def test_load_research_fixtures_joins_exact_twenty_and_production_remains_blocked():
    root = Path(__file__).resolve().parents[1]
    rows = a.load_20_epochs(root / 'data/verification/modern_20_tt_epochs_20261023.json',
                            root / 'data/verification/modern_20_naoj_cases_20261023.json')
    assert len(rows)==20
    assert len({(r["year"],r["kasi_term_id"]) for r in rows})==20
    assert rows[0]["year"]==1962 and rows[-1]["year"]==2024
    report = a.summarize_projection(rows[:1],
              [{"mjd_tai":float(rows[0]["tt_jd"]-2400000.5-32.184/86400),
                "dx_mas":0.,"dy_mas":0., "interpolation":"linear_MJD_TAI",
                "usable_as_iau76_80_correction":False,"production_authorized":False}],
              {"source_sha256":"a"*64,"frame":"IAU 2006/2000A",
               "production_authorized":False})
    assert report["status"]=="research_only"
    assert report["production_authorized"] is False
    assert report["coordinate_frame_equivalence_proved"] is False
    assert report["corrected_horizons_longitudes"] == []
    assert report["epochs"][0]["year"]==1962


def test_secure_local_source_rejects_wrong_sha_and_symlink(tmp_path):
    file = tmp_path / 'eop2.long'
    file.write_text(SAMPLE)
    with pytest.raises(a.EopEvidenceError):
        a.load_verified_source(file, expected_sha256="0"*64)
    alias = tmp_path / 'eop2-symlink'
    alias.symlink_to(file)
    with pytest.raises(a.EopEvidenceError):
        a.load_verified_source(alias, expected_sha256="0"*64)
