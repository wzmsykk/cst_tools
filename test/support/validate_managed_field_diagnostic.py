"""Explicit M5 real solver/optional artifact/Ack lifecycle acceptance."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.configuration import read_json,write_json_atomic
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.result_reconciliation import file_hash
from csttool.acceptance_session import exclusive_probe
from test.managed_hom_ten_modes_fault_resume_integration_test import _config


def main():
    with exclusive_probe(ROOT):
        return run_validation()


def run_validation():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cst-exe',required=True)
    parser.add_argument('--tasks',type=int,choices=(1,2),default=1)
    args=parser.parse_args()
    destination=ROOT/'artifacts'/('managed-field-diagnostic-'+uuid4().hex[:8])
    destination.mkdir(parents=True)
    ref=read_json(ROOT/'artifacts/cross-mesh-fields-b8ab3d42/cell-30/export-result.json')
    ref['PostProcessResult']=[p for p in ref['PostProcessResult'] if p['resultName'] in ('E_1_12','E_2_12')]
    write_json_atomic(destination/'reference.json',ref)
    source=ROOT/'artifacts/hom-mesh-baseline-de2d6b90/cell-30/prepared.cst'
    before=file_hash(source)
    config=_config(destination,'0',Path(args.cst_exe),source)
    config['fieldReferenceResult']=str(destination/'reference.json')
    config['fieldMatchPolicy']={'minimum_mac':0.9,'minimum_margin':0.05,'minimum_subspace_overlap':0.99}
    config['postProcess']=list(config['postProcess'])+[{
        'method':'ExportModeField','resultName':f'E_{mode}',
        'params':{'iModeNumber':mode,'field_kind':'E','sampling':{
            'bounds_m':[-.01,.01,-.01,.01,-.05,.05],'counts':[12,12,12],'scope':'roi-probe'}}}
        for mode in (1,2)]
    # An intentionally invalid ROI verifies optional export failure does not fail the solve.
    config['postProcess'].append({'method':'ExportModeField','resultName':'invalid-support',
        'params':{'iModeNumber':1,'sampling':{'bounds_m':[100,101,100,101,100,101],
                                              'counts':[1,1,1],'scope':'roi-probe'}}})
    print(f'MANAGED_ROOT={destination}',flush=True)
    worker=ManagedCSTWorker('0',config)
    report={}
    try:
        report['results']=[]
        for index in range(args.tasks):
            result=dict(worker.run_task(f'field-diagnostic-acceptance-{index+1}',params={
                'nmodes':2,'fmin':513.492631838138,'fmax':713.492631838138}))
            report['result']=result
            report['results'].append(result)
            # Invalid optional export is deliberately included: diagnostic incomplete, solve Success.
            assert result['TaskStatus']=='Success',result
            assert result['FieldDiagnostic']['status']=='incomplete',result
            field_records=result.get('FieldArtifacts',result['PostProcessResult'])
            exports=[p['value'] for p in field_records if p['value'] and isinstance(p['value'],dict) and p['value'].get('kind')=='field-artifact']
            assert [v['status'] for v in exports]==['available','available','unavailable'],exports
            # Recover only analysis from valid artifacts: no extra Solver invocation.
            valid=[p for p in field_records if p['resultName']!='invalid-support' and isinstance(p['value'],dict)]
            diagnostic=worker._run_optional_field_diagnostic(type('TaskRef',(),{'task_id':result['TaskID']})(),Path(result['ResultDirectory']),valid)
            report['recovered_diagnostic']=diagnostic
            assert diagnostic['status']=='complete',diagnostic
            report['recovery_solver_replayed']=False
            print(f'TASK_COMPLETE index={index+1} id={result["TaskID"]}',flush=True)
    finally:
        report['stop_returned']=worker.stop()
        report['stop_ack']=worker.protocol.read_stop_ack(worker.session_id) is not None
        report['exit_code']=worker._process.poll()
        report['source_unchanged']=file_hash(source)==before
        log = worker.root/'cst.log'
        text = log.read_text(errors='replace') if log.exists() else ''
        report['shutdown_errors'] = [token for token in (
            'Unable to close sheet while a batch job is running',
            'Expecting an existing scalar var.', 'EvaluateInternal CDbl(concaveL)') if token in text]
        report['shutdown_clean'] = not report['shutdown_errors']
        write_json_atomic(destination/'report.json',report)
    assert report['stop_returned'] and report['stop_ack'], report
    assert report['exit_code'] == 0 and report['source_unchanged'], report
    assert report['shutdown_clean'], report['shutdown_errors']
    print({k:report[k] for k in ('stop_returned','stop_ack','exit_code','source_unchanged')},flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
