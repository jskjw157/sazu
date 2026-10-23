"""Run old and corrected projections against identical TT roots and unchanged KASI cells.

The pre-1960 legacy display is retained as evidence, NOT rebranded as valid UTC.
Any remaining mismatch or undefined-clock key prevents an overall success.
"""
import argparse
from datetime import UTC, datetime
from pathlib import Path

from sazu.cli import _manifest
from sazu.clock_projection import projection_identity
from sazu.errors import require
from sazu.kasi_reference import parse_kasi_document, reference_events
from sazu.serde import canonical_json, digest
from sazu.solar_terms import compare_reference, generate_terms
from sazu.source_audit import read_reference_bytes
from sazu.term_audit import compare_term_range
from tools.audit_official_terms import build_request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kasi',type=Path,required=True)
    parser.add_argument('--kernel',type=Path,required=True)
    args=parser.parse_args()
    request=build_request(args.kasi,args.kernel,datetime.now(UTC),1920,2050)
    manifest=_manifest(request['reference_manifest'])
    document=parse_kasi_document(read_reference_bytes(args.kasi,manifest),manifest)
    references={(e.event_year,e.kasi_id):e for e in reference_events(document,1920,2050)}
    legacy=[]; corrected=[]
    for year in range(1920,2051):
        legacy.extend(generate_terms(year,args.kernel,_manifest(request['kernel_manifest']),
                                     clock_policy='legacy-skyfield-v1'))
        corrected.extend(generate_terms(year,args.kernel,_manifest(request['kernel_manifest'])))
    legacy_tt=digest([(e.event_year,e.kasi_id,e.tt_jd) for e in legacy])
    corrected_tt=digest([(e.event_year,e.kasi_id,e.tt_jd) for e in corrected])
    require(legacy_tt==corrected_tt,'DATA_INTEGRITY_FAILED')
    old_bad=[]; old_good=0; fixed=[]; remaining=[]; periods={}
    for old,new in zip(legacy,corrected):
        key=(old.event_year,old.kasi_id)
        require(key==(new.event_year,new.kasi_id),'DATA_INTEGRITY_FAILED')
        ref=references[key]
        before=compare_reference(ref,old.instant_utc)=='match'
        after=None if new.instant_utc is None else compare_reference(ref,new.instant_utc)=='match'
        label=('pre_1960_clock_unresolved' if key[0]<1960 else
               '1960_1971_utc_drift' if key[0]<1972 else
               '1972_2026_announced_utc' if key[0]<=2026 else '2027_2050_conditional_utc')
        bucket=periods.setdefault(label,{'total':0,'legacy_matched':0,'corrected_matched':0,
                                        'corrected_mismatched':0,'clock_unresolved':0})
        bucket['total']+=1;bucket['legacy_matched']+=before
        bucket['corrected_matched']+=after is True
        bucket['corrected_mismatched']+=after is False
        bucket['clock_unresolved']+=after is None
        old_good+=before
        if not before:
            old_bad.append(list(key))
            (fixed if after is True else remaining).append(list(key))
    comparison=compare_term_range(corrected,document,1920,2050)
    report={'schema_version':1,'status':comparison['status'],'production_authorized':False,
            'reference_unchanged':True,'rounding_cell_unchanged':True,
            'tt_roots_unchanged':True,'tt_roots_sha256':corrected_tt,
            'legacy':{'label':'reproduction_only_not_valid_historical_utc',
                      'matched':old_good,'mismatched':len(old_bad),'total':len(legacy)},
            'corrected':comparison,'projection_identity':projection_identity(),
            'resolved_original_mismatch_keys':fixed,
            'not_resolved_original_mismatch_keys':remaining,'periods':periods,
            'notes':['Undefined UTC is not a passing comparison.',
                     'UT1 hypotheses and alternate celestial frames were not adopted.',
                     'No fitted offsets, source-value edits, or tolerance changes.']}
    report['artifact_sha256']=digest(report)
    print(canonical_json(report))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
