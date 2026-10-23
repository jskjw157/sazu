"""Research fixture guards. Published minute agreement is not physical TT proof."""
from datetime import datetime, timedelta
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "data/verification/modern_20_naoj_cases_20261023.json"


def test_all_20_official_published_minute_crosschecks_are_accounted_for():
    d=json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases=d["cases"]
    assert d["research_only"] is True
    assert d["production_authorized"] is False
    assert d["release_approval"] == "BLOCKED"
    assert len(cases) == 20
    assert len({(c["year"],c["kasi_term_id"]) for c in cases}) == 20
    assert sum(c["reference_agreement"]=="naoj_equals_kasi" for c in cases) == 12
    assert sum(c["reference_agreement"]=="naoj_equals_skyfield_display" for c in cases) == 8
    for c in cases:
        assert c["production_authorized"] is False
        assert c["naoj_official_url"].startswith("https://eco.mtk.nao.ac.jp/koyomi/yoko/")
        assert c["reference_agreement"] == (
            "naoj_equals_kasi" if c["naoj_published_minute"] == c["kasi_long_txt_minute"]
            else "naoj_equals_skyfield_display")
        assert c["naoj_published_minute"] in {
            c["kasi_long_txt_minute"],c["skyfield_replay_rounded_minute"]}
        assert 0 < c["gap_past_rounding_boundary_seconds"] < 2
        m=datetime.fromisoformat(c["date_kst"]+" "+c["skyfield_replay_rounded_minute"])
        k=datetime.fromisoformat(c["date_kst"]+" "+c["kasi_long_txt_minute"])
        assert k-m==timedelta(minutes=1)


def test_fixed_case_identities_and_known_conflicting_naoj_examples():
    d=json.loads(FIXTURE.read_text(encoding="utf-8"))
    index={(c["year"],c["kasi_term_id"]):c for c in d["cases"]}
    assert set(index)=={
        (1962,3),(1972,12),(1972,13),(1975,23),(1976,20),
        (1980,3),(1981,19),(1988,23),(1989,2),(1990,16),
        (1996,24),(1999,16),(2001,3),(2007,17),(2009,11),
        (2010,19),(2013,17),(2014,2),(2018,20),(2024,20)}
    assert index[(2018,20)]["reference_agreement"]=="naoj_equals_kasi"
    assert index[(2024,20)]["reference_agreement"]=="naoj_equals_skyfield_display"
    assert index[(1972,12)]["naoj_published_minute"]=="03:03"
    assert index[(1999,16)]["naoj_published_minute"]=="20:31"
