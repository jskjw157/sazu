"""Diagnostic-only IAU76/80 and IAU2006 comparisons, not an adopted model.

No constants are fitted to KASI. Formulas are public ERFA routines.
Output contains derived residuals, not a replacement reference dataset.
"""
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import warnings

import erfa
import numpy as np
from skyfield.api import load, load_file
from skyfield import almanac

from sazu.cli import _manifest
from sazu.kasi_reference import parse_kasi_document, reference_events
from sazu.solar_terms import FIXED_KST
from sazu.source_audit import read_reference_bytes
from tools.audit_official_terms import build_request


def main():
    root = Path(os.environ['RUNNER_TEMP'])
    request = build_request(root/'kasi.txt', root/'de440s.bsp', datetime.now(UTC), 1920, 2050)
    manifest = _manifest(request['reference_manifest'])
    refs = reference_events(parse_kasi_document(read_reference_bytes(root/'kasi.txt', manifest), manifest), 1920, 2050)
    ts = load.timescale(builtin=True)
    eph = load_file(str(root/'de440s.bsp'))
    earth, sun = eph['earth'], eph['sun']
    bias = erfa.bp00(2451545., 0.)[0]
    summaries, cases = {}, []
    try:
        for frame in ('iau76-80', 'iau76-80-with-bias', 'iau2006-2000a'):
            def term_at(t):
                vector = earth.at(t).observe(sun).apparent().position.au
                if frame == 'iau2006-2000a':
                    matrix = erfa.pnm06a(t.whole, t.tt_fraction)
                    eps = erfa.obl06(t.whole, t.tt_fraction)+erfa.nut06a(t.whole, t.tt_fraction)[1]
                else:
                    matrix = erfa.pnm80(t.whole, t.tt_fraction)
                    if frame == 'iau76-80-with-bias':
                        matrix = matrix @ bias
                    eps = erfa.obl80(t.whole, t.tt_fraction)+erfa.nut80(t.whole, t.tt_fraction)[1]
                rotation = erfa.rx(eps, matrix)
                rotated = np.matmul(rotation, np.moveaxis(vector, 0, -1)[...,None])[...,0]
                longitude = np.arctan2(rotated[...,1], rotated[...,0]) % (2*np.pi)
                return (longitude // (np.pi/12) % 24).astype(int)
            term_at.step_days = 14.0
            outputs = []
            for year in range(1920, 2051):
                start = ts.from_datetime(datetime(year, 1, 1, tzinfo=FIXED_KST))
                end = ts.from_datetime(datetime(year+1, 1, 1, tzinfo=FIXED_KST))
                times, indices = almanac.find_discrete(start, end, term_at, epsilon=1e-8)
                lookup = {((int(i)*15-315)%360)//15+1:t for i,t in zip(indices,times)}
                assert len(lookup) == 24
                for ref in refs[(year-1920)*24:(year-1919)*24]:
                    t = lookup[ref.kasi_id]
                    delta = (t.utc_datetime()-ref.instant_utc).total_seconds()
                    utc = delta
                    if 1960 <= year < 1972:
                        with warnings.catch_warnings():
                            warnings.simplefilter('ignore', erfa.ErfaWarning)
                            a,b = erfa.tttai(float(t.whole),float(t.tt_fraction))
                            a,b = erfa.taiutc(a,b)
                            y,m,d,hms = erfa.d2dtf('UTC',6,a,b)
                        utc = (datetime(int(y),int(m),int(d),int(hms['h']),int(hms['m']),int(hms['s']),int(hms['f']),tzinfo=UTC)-ref.instant_utc).total_seconds()
                    ut1 = delta+float(t.dut1)
                    outputs.append({'year':year,'term':ref.kasi_id,'utc':delta,'ut1':ut1,'historical_civil':ut1 if year<1960 else utc})
            summaries[frame] = {}
            for scale in ('utc','ut1','historical_civil'):
                summaries[frame][scale] = {}
                for label,lo,hi in [('all',1920,2050),('past',1920,1971),('modern',1972,2025),('future',2026,2050)]:
                    ds=[r[scale] for r in outputs if lo<=r['year']<=hi]
                    summaries[frame][scale][label]={'total':len(ds),'matched':sum(-30<=d<30 for d in ds),'minimum':min(ds),'maximum':max(ds),'mean':sum(ds)/len(ds)}
            cases.append({'frame':frame,'residuals':outputs})
    finally:
        eph.close()
    report={'adopted':False,'production_authorized':False,'summaries':summaries,'diagnostics':cases}
    (root/'frame-probe.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(summaries,indent=2))


if __name__ == '__main__':
    main()
