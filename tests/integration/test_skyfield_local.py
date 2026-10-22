"""Optional regression against prior model output, NOT fresh official validation."""
from datetime import UTC,date,datetime
import hashlib
import json
import os
from pathlib import Path
import pytest
from sazu.contracts import SourceManifest
from sazu.solar_terms import generate_terms


@pytest.mark.skipif(not os.environ.get('SAZU_KERNEL'),reason='Local JPL kernel not provisioned')
def test_local_skyfield_model_regression():
    pytest.importorskip('skyfield')
    kernel=Path(os.environ['SAZU_KERNEL'])
    expected_hash='c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2'
    assert hashlib.sha256(kernel.read_bytes()).hexdigest()==expected_hash
    m=SourceManifest('jpl-de440s','JPL','DE440s',
      'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp',
      expected_hash,kernel.stat().st_size,datetime(2026,10,21,tzinfo=UTC),date(1850,1,1),date(2149,1,1),
      'TDB','computed','unreviewed','https://naif.jpl.nasa.gov/naif/rules.html',('jpl-de440s',),'v1')
    root=Path(__file__).resolve().parents[2]
    prior=json.loads((root/'data/verification/saju_source_verification_20261020.json').read_text())
    rows=prior['solar_term_probe']['comparisons']
    expected={(r['year'],r['term']):datetime.fromisoformat(r['skyfield_kst']).astimezone(UTC) for r in rows}
    results=[]
    for year in (1993,2026):
        events=generate_terms(year,kernel,m);assert len(events)==24
        for event in events:
            assert abs((event.instant_utc-expected[year,event.kasi_id]).total_seconds())<1
            assert event.tt_jd and event.model_id and event.physical_uncertainty=='unknown'
        results.append(events)
    assert generate_terms(2026,kernel,m)==results[-1]


@pytest.mark.skipif(not os.environ.get('SAZU_KERNEL'),reason='Local JPL kernel not provisioned')
def test_reviewed_generator_and_cli_keep_clock_status(tmp_path):
    """Real kernel integration, not an independent KASI numeric match test."""
    import subprocess
    import sys
    from sazu.serde import canonical_json
    from sazu.term_clock import generate_reviewed_terms
    kernel=Path(os.environ['SAZU_KERNEL'])
    expected_hash='c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2'
    assert hashlib.sha256(kernel.read_bytes()).hexdigest()==expected_hash
    m=SourceManifest('jpl-de440s','JPL','DE440s',
      'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp',
      expected_hash,kernel.stat().st_size,datetime(2026,10,22,tzinfo=UTC),date(1850,1,1),date(2149,1,1),
      'TDB','computed','unreviewed','https://naif.jpl.nasa.gov/naif/rules.html',('jpl-de440s',),'v1')
    for year,status in ((1950,'historical_clock_unresolved'),(1960,'historical_utc'),
                        (1965,'historical_utc'),(2020,'modern_utc'),
                        (2026,'modern_utc'),(2040,'future_utc_assumption')):
        terms=generate_reviewed_terms(year,kernel,m)
        assert len(terms)==24 and {t.kasi_id for t in terms}==set(range(1,25))
        assert all(t.clock.status==status and not t.production_authorized for t in terms)
        assert all(t.clock.bulletin_id=='IERS-Bulletin-C-72' for t in terms)
        if year==1950:
            assert all(t.clock.instant_utc is None for t in terms)
        else:
            assert all(t.clock.instant_utc is not None for t in terms)
        assert generate_reviewed_terms(year,kernel,m)==terms
    root=Path(__file__).resolve().parents[2]
    env=os.environ.copy();env['PYTHONPATH']=str(root/'src')
    payload=canonical_json({'year':1965,'path':str(kernel),'manifest':m})
    process=subprocess.run([sys.executable,'-m','sazu','generate-terms'],input=payload,
                           text=True,capture_output=True,env=env,cwd=tmp_path,timeout=30)
    assert process.returncode==0 and process.stderr==''
    result=json.loads(process.stdout)
    assert result['ok'] and result['production_authorized'] is False
    assert len(result['result'])==24
    assert all(t['clock']['status']=='historical_utc' for t in result['result'])
