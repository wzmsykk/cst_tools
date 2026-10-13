"""Explicit M2-M4 saved-field ROI validation, not scan adoption."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.configuration import read_json,write_json_atomic
from csttool.saved_field_export import export_saved_fields
from csttool.field_artifacts import artifacts_from_result
from csttool.field_diagnostics import run_field_diagnostic
from csttool.mode_matching import MatchPolicy


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cst-exe',required=True)
    args=parser.parse_args()
    base=read_json(ROOT/'artifacts/hom-mesh-baseline-de2d6b90/report.json')
    destination=ROOT/'artifacts'/('cross-mesh-fields-'+uuid4().hex[:8])
    print(f'VALIDATION_ROOT={destination}',flush=True)
    exports={}
    for cell in (30,36):
        source=next(p['result']['ProjectSnapshot'] for p in base['points'] if p['cell']==cell)
        settings=[{'method':'ExportModeField','resultName':f'{kind}_{mode}_{n}',
                   'params':{'iModeNumber':mode,'field_kind':kind,
                     'sampling':{'bounds_m':[-0.01,0.01,-0.01,0.01,-0.05,0.05],
                                 'counts':[n,n,n],'scope':'roi-probe'}}}
                  for n in (12,24,48) for kind in ('E','H') for mode in (1,2)]
        exports[cell]=export_saved_fields(args.cst_exe,source,destination/f'cell-{cell}',settings)
        print(f'EXPORT cell={cell} status={exports[cell]["status"]} fields={[p["value"]["status"] for p in exports[cell]["PostProcessResult"]]}',flush=True)
    reports=[]
    for n in (12,24,48):
        for kind in ('E','H'):
            groups=[]
            for cell in (30,36):
                items=[p for p in exports[cell]['PostProcessResult'] if p['resultName'].startswith(kind+'_') and p['resultName'].endswith('_'+str(n))]
                groups.append(artifacts_from_result(exports[cell]['result_directory'],items))
            report=run_field_diagnostic(*groups,MatchPolicy(0.9,0.05,0.99),
                         destination/f'{kind}-{n}-diagnostic.json',context={'experiment':'cross-mesh-ROI'})
            reports.append(report)
            print(f'DIAGNOSTIC {kind} n={n} status={report["status"]} members={report.get("members")} group={report.get("group")}',flush=True)
    write_json_atomic(destination/'report.json',{'exports':exports,'diagnostics':reports,
        'physical_gate_passed':False,'reason':'ROI and thresholds not physically calibrated'})
    return 0


if __name__=='__main__':
    raise SystemExit(main())
