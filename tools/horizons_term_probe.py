"""Research-only geocentric solar-term diagnostic against JPL Horizons.

The geometry comparison uses ICRF Cartesian AU vectors at identical TDB events.
The seasonal longitude comparison is explicitly NOT frame-identical: Horizons
quantity #31 uses IAU76/80 apparent ecliptic-of-date while the Skyfield
almanac_east_asia solar terms routine uses IAU2000B true-of-date. The two
numerical columns are therefore explanatory diagnostics, not a pass/fail oracle.

External access is restricted to an explicit opt-in command-line research
run. No external dependency is added to the HTTP calculation path.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from datetime import UTC, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlencode, urlparse
from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler, Request

API_URL = 'https://ssd.jpl.nasa.gov/api/horizons.api'
JPL_DE440S_SHA256 = 'c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2'
ARCHIVED_PROBE_SHA256 = '5c33bcb86f9ad8aa59a128994860fa52f32883d490c8bce1da1c2a7fdfe1025f'
MAX_RESPONSE_BYTES = 1_048_576
HALF_WINDOW_SECONDS = 120.0
_NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
_FLOAT_RE = re.compile(rf'^{_NUMBER}$')
_VEC_RE = re.compile(rf'\bX\s*=\s*({_NUMBER})\s+Y\s*=\s*({_NUMBER})\s+Z\s*=\s*({_NUMBER})',re.S)


class ProbeError(ValueError):
    """Fail closed on incorrect evidence, response shape, or access."""


@dataclass(frozen=True)
class Epoch:
    year: int
    term_id: int
    tt_jd: float


def _json_file(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RESPONSE_BYTES:
        raise ProbeError('Unsafe or oversized research file')
    try:
        result = json.loads(path.read_text(encoding='utf-8'))
    except (UnicodeError, OSError, ValueError) as e:
        raise ProbeError('Invalid research JSON') from e
    if not isinstance(result, dict):
        raise ProbeError('Research JSON is not an object')
    return result


def load_epochs(epoch_path: Path, cases_path: Path) -> list[Epoch]:
    epochs = _json_file(epoch_path)
    cases = _json_file(cases_path)
    if (epochs.get('research_only') is not True or epochs.get('production_authorized') is not False
        or epochs.get('base_probe_sha256') != ARCHIVED_PROBE_SHA256
        or cases.get('research_only') is not True or cases.get('production_authorized') is not False
        or cases.get('release_approval') != 'BLOCKED'
        or cases.get('archived_probe_sha256') not in (None, ARCHIVED_PROBE_SHA256)):
        raise ProbeError('Research source identity/approval mismatch')
    rows = epochs.get('epochs')
    refs = cases.get('cases')
    if not isinstance(rows, list) or not isinstance(refs, list) or len(rows) != 20 or len(refs) != 20:
        raise ProbeError('Full 20-case research coverage required')
    seen = set()
    results = []
    for row in rows:
        if not isinstance(row, dict):
            raise ProbeError('Invalid epoch object')
        y, idx, tt = row.get('year'), row.get('kasi_term_id'), row.get('tt_jd')
        if (type(y) is not int or not 1960 <= y <= 2025 or type(idx) is not int
            or not 1 <= idx <= 24 or type(tt) is not float or not math.isfinite(tt)
            or not 2430000 < tt < 2470000 or (y, idx) in seen):
            raise ProbeError('Invalid or duplicate epoch')
        seen.add((y, idx))
        results.append(Epoch(y, idx, tt))
    refs_keys = []
    for r in refs:
        if (not isinstance(r, dict) or type(r.get('year')) is not int
            or type(r.get('kasi_term_id')) is not int
            or r.get('production_authorized') is not False):
            raise ProbeError('Invalid or non-research reference case')
        refs_keys.append((r['year'], r['kasi_term_id']))
    if len(set(refs_keys)) != 20 or set(refs_keys) != seen:
        raise ProbeError('Reference case identities differ from TT evidence')
    if results != sorted(results, key=lambda r: r.tt_jd):
        raise ProbeError('TT epochs must be chronological')
    return results


def _finite_jds(jds: list[float]) -> list[float]:
    if not isinstance(jds,list) or not 1 <= len(jds) <= 100:
        raise ProbeError('Invalid number of Horizons epochs')
    if any(type(j) is not float or not math.isfinite(j) or not 2430000 < j < 2470000 for j in jds):
        raise ProbeError('Invalid Horizons JD')
    if any(a >= b for a,b in zip(jds, jds[1:])):
        raise ProbeError('Horizons epochs must be strictly increasing')
    return jds


def make_query(kind: str, jds: list[float]) -> dict[str,str]:
    _finite_jds(jds)
    if kind not in ('observer','vector'):
        raise ProbeError('Unsupported query kind')
    query={
        'format':'json', 'COMMAND':'10', 'OBJ_DATA':'NO',
        'MAKE_EPHEM':'YES', 'EPHEM_TYPE':'OBSERVER' if kind=='observer' else 'VECTORS',
        'CENTER':'500@399', 'TLIST_TYPE':'JD',
        'TLIST':','.join("'" + format(Decimal(str(v)).quantize(Decimal('0.0000000001')), 'f') + "'" for v in jds),
        'REF_SYSTEM':'ICRF',
    }
    if kind=='observer':
        query.update({'QUANTITIES':'31','TIME_TYPE':'TT','CAL_FORMAT':'JD',
                      'ANG_FORMAT':'DEG','CSV_FORMAT':'YES', 'EXTRA_PREC':'YES',
                      'TIME_DIGITS':'FRACSEC','APPARENT':'AIRLESS'})
    else:
        query.update({'TIME_TYPE':'TDB','REF_PLANE':'FRAME','OUT_UNITS':'AU-D',
                      'VEC_CORR':'NONE','VEC_TABLE':'1'})
    return query


def validate_url(url: str) -> None:
    p = urlparse(url)
    if (p.scheme != 'https' or p.hostname != 'ssd.jpl.nasa.gov'
        or p.path != '/api/horizons.api' or p.username is not None
        or p.password is not None or p.port not in (None,443)
        or p.fragment):
        raise ProbeError('Only the official Horizons HTTPS API is allowed')


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProbeError('Horizons redirected outside its pinned endpoint')


def fetch_horizons(query: dict[str,str]) -> tuple[str,str]:
    url = API_URL + '?' + urlencode(query)
    validate_url(API_URL)
    opener=build_opener(HTTPSHandler(),_NoRedirect())
    try:
        with opener.open(Request(url,headers={'User-Agent':'SAZU-offline-research/1.0',
                                               'Accept':'application/json'}),timeout=45) as response:
            if response.status != 200:
                raise ProbeError(f'Horizons HTTP status {response.status}')
            payload=response.read(MAX_RESPONSE_BYTES+1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise ProbeError('Horizons response too large')
    except ProbeError:
        raise
    except (OSError, TimeoutError, ValueError) as e:
        raise ProbeError('Horizons API unavailable; no numerical result') from e
    try:
        value=json.loads(payload)
        if not isinstance(value,dict) or not isinstance(value.get('result'),str):
            raise ProbeError('Unexpected Horizons JSON shape')
        result=value['result']
        if len(result)>MAX_RESPONSE_BYTES:
            raise ProbeError('Horizons result too large')
    except (ValueError,UnicodeError) as e:
        raise ProbeError('Invalid Horizons JSON') from e
    return result, hashlib.sha256(payload).hexdigest()


def _body(raw: str) -> str:
    if not isinstance(raw,str) or raw.count('$$SOE')!=1 or raw.count('$$EOE')!=1:
        raise ProbeError('No complete Horizons ephemeris table')
    a=raw.find('$$SOE')+len('$$SOE'); b=raw.find('$$EOE')
    if b<=a:
        raise ProbeError('Inverted ephemeris delimiters')
    return raw[a:b]


def parse_observer(raw: str, expected: list[float]) -> list[float]:
    _finite_jds(expected)
    if 'ObsEcLon' not in raw and 'App_Lon_Sun' not in raw:
        raise ProbeError('Horizons quantity #31 was not emitted')
    lines=[v.strip() for v in _body(raw).splitlines() if v.strip()]
    if len(lines)!=len(expected):
        raise ProbeError('Horizons observer row count mismatch')
    lons=[]
    for line,jd in zip(lines,expected):
        # JD output may have additional blank columns for daylight/lunar flags.
        fields=[x.strip() for x in line.split(',')]
        numerics=[float(x) for x in fields if _FLOAT_RE.fullmatch(x)]
        if (len(numerics)!=3 or abs(numerics[0]-jd)>3e-6
            or not all(math.isfinite(v) for v in numerics)
            or not 0<=numerics[1]<360 or not -10 <= numerics[2] <= 10):
            raise ProbeError('Unexpected Horizons quantity #31 numeric layout')
        lons.append(numerics[1])
    return lons


def parse_vectors(raw: str, expected: list[float]) -> list[tuple[float,float,float]]:
    _finite_jds(expected)
    body=_body(raw)
    matches=list(re.finditer(r'(?m)^\s*(\d{7}\.\d+)\s*=',body))
    if len(matches)!=len(expected):
        raise ProbeError('Horizons vector row count mismatch')
    vectors=[]
    for n, match in enumerate(matches):
        if abs(float(match.group(1))-expected[n]) > 3e-6:
            raise ProbeError('Horizons vector epoch mismatch')
        piece=body[match.end():matches[n+1].start() if n+1<len(matches) else len(body)]
        vec=_VEC_RE.search(piece)
        if not vec:
            raise ProbeError('Incomplete ICRF vector')
        numbers=tuple(float(v) for v in vec.groups())
        if not all(math.isfinite(v) and abs(v) < 10 for v in numbers):
            raise ProbeError('Impossible ICRF vector')
        vectors.append(numbers)
    return vectors


def delta_degrees(a: float,b: float) -> float:
    return (a-b+180.0)%360.0-180.0


def estimate_crossing(target: float, before: float, center: float, after: float) -> dict:
    if not all(type(v) in (int,float) and math.isfinite(v) for v in (target,before,center,after)):
        raise ProbeError('Invalid crossing-angle data')
    slope=delta_degrees(after,before)/(2*HALF_WINDOW_SECONDS)
    if not 2e-6 < slope < 3e-5:
        return {'bracketed':False,'interpolated_tt_offset_seconds':None,
                'slope_deg_per_second':slope}
    delta=delta_degrees(center,target)
    offset=-delta/slope
    bracketed=bool(abs(offset) <= HALF_WINDOW_SECONDS)
    return {'bracketed':bracketed,
            'interpolated_tt_offset_seconds':round(offset,6) if bracketed else None,
            'slope_deg_per_second':slope}


def _load_verified_kernel(kernel_path: Path):
    try:
        info=kernel_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 67_108_864:
            raise ProbeError('Unsafe JPL kernel file')
        with kernel_path.open('rb') as f:
            sha=hashlib.file_digest(f,'sha256').hexdigest()
    except OSError as e:
        raise ProbeError('JPL kernel unavailable') from e
    if sha!=JPL_DE440S_SHA256:
        raise ProbeError('Unexpected JPL DE440s checksum')


def compute_skyfield(epochs: list[Epoch], kernel_path: Path) -> list[dict]:
    _load_verified_kernel(kernel_path)
    from skyfield.api import Loader, load_file
    from skyfield.nutationlib import iau2000b_radians
    ts=Loader(str(kernel_path.parent)).timescale(builtin=True)
    results=[]
    with closing(load_file(str(kernel_path))) as eph:
        earth=eph['earth'];sun=eph['sun']
        for e in epochs:
            t=ts.tt_jd(e.tt_jd)
            # EXACT convention used by skyfield.almanac_east_asia.solar_terms.
            t._nutation_angles_radians = iau2000b_radians(t)
            _,lon,_=earth.at(t).observe(sun).apparent().ecliptic_latlon('date')
            v=sun.at(t).position.au-earth.at(t).position.au
            results.append({'tt_jd':e.tt_jd,'tdb_jd':float(t.tdb),
                            'skyfield_true_date_lon':float(lon.degrees)%360,
                            'skyfield_geometric_vector':[float(x) for x in v]})
    return results


def make_report(epochs:list[Epoch],local:list[dict],observer:list[list[float]],
                vectors:list[tuple[float,float,float]],meta:dict)->dict:
    if not epochs or len(epochs)!=len(local) or len(local)!=len(observer) or len(vectors)!=len(local):
        raise ProbeError('Report requires all geometric and apparent samples')
    rows=[]
    for e,s,angles,other in zip(epochs,local,observer,vectors):
        if len(angles)!=3 or len(other)!=3 or len(s.get('skyfield_geometric_vector',[]))!=3:
            raise ProbeError('Incomplete local/horizons comparison')
        target=(315+15*(e.term_id-1))%360
        crossing=estimate_crossing(target,*angles)
        diff=delta_degrees(angles[1],s['skyfield_true_date_lon'])
        separation=math.dist(other,s['skyfield_geometric_vector'])
        rows.append({'year':e.year,'kasi_term_id':e.term_id,'tt_jd':e.tt_jd,
                     'term_target_longitude_deg':target,
                     'skyfield_iau2000b_true_date_longitude_deg':s['skyfield_true_date_lon'],
                     'horizons_iau76_80_obs_lon_deg':angles[1],
                     'horizons_minus_skyfield_longitude_arcsec':round(diff*3600,6),
                     'horizons_iau76_80_tt_offset_s':crossing['interpolated_tt_offset_seconds'],
                     'horizons_root_bracketed':crossing['bracketed'],
                     'horizons_lon_slope_deg_per_s':crossing['slope_deg_per_second'],
                     'vector_icrf_difference_au':separation,
                     'proves_physical_tt_error':False,
                     'production_authorized':False})
    return {'schema_version':1,'status':'diagnostic_only','production_authorized':False,
            'release_approval':'BLOCKED','research_only':True,
            'sample_count':len(rows),
            'comparison':{
                'geometric_vector_frame':'ICRF in AU, same TDB epoch (Horizons current ephemeris may differ from DE440s)',
                'longitude_frames_directly_interchangeable':False,
                'skyfield_apparent_frame':'IAU2000B true ecliptic of date as in almanac_east_asia',
                'horizons_apparent_frame':'IAU76/80 observer ecliptic-of-date (quantity 31)',
                'lon_offset_interpretation':'descriptive model/frame-dependent solar term boundary offset, NOT TT error proof',
                'other_sources':'KASI/NAOJ minute reports are not adjudicated by this comparison'},
            'source':meta,'rows':rows}


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs',type=Path,required=True)
    parser.add_argument('--cases',type=Path,required=True)
    parser.add_argument('--kernel',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        epochs=load_epochs(args.epochs,args.cases)
        local=compute_skyfield(epochs,args.kernel)
        obs_times=[e.tt_jd+offset/86400 for e in epochs for offset in
                   (-HALF_WINDOW_SECONDS,0.0,HALF_WINDOW_SECONDS)]
        vector_times=[p['tdb_jd'] for p in local]
        observer,obs_hash=fetch_horizons(make_query('observer',obs_times))
        vector,vec_hash=fetch_horizons(make_query('vector',vector_times))
        obs_lons=parse_observer(observer,obs_times)
        vec=parse_vectors(vector,vector_times)
        obs_groups=[obs_lons[i*3:(i+1)*3] for i in range(len(epochs))]
        meta={'horizons_api':API_URL,'obs_query':make_query('observer',obs_times),
              'vec_query':make_query('vector',vector_times),
              'observer_sha256':obs_hash,'vector_sha256':vec_hash,
              'observer_header':observer.split('$$SOE')[0][-2500:],
              'vector_header':vector.split('$$SOE')[0][-2500:],
              'base_probe_sha256':ARCHIVED_PROBE_SHA256,
              'local_kernel_sha256':JPL_DE440S_SHA256,
              'skyfield_version':'1.55',
              'retrieved_at_utc':datetime.now(UTC).isoformat()}
        report=make_report(epochs,local,obs_groups,vec,meta)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        print(json.dumps({'status':report['status'],'sample_count':len(report['rows']),
                          'production_authorized':False,'report':str(args.output)}))
        return 0
    except (ProbeError, ValueError, ImportError, OSError, KeyError) as e:
        report={'status':'blocked','production_authorized':False,'error_type':type(e).__name__,
                'error':'Numerical diagnostic could not be completed; no result is approved.'}
        args.output.write_text(json.dumps(report)+'\n')
        print(json.dumps(report),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
