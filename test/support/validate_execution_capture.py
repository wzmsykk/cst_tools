"""B4 serial coarse Pillbox copy acceptance through common RunStore/capture code."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil
from uuid import uuid4

import calibrate_cst_settings as probe
from csttool.execution_snapshot import ExecutionConfig
from csttool.native_execution_capture import render_capture_runtime
from csttool.run_store import RunStore


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cst-exe',required=True,type=Path)
    parser.add_argument('--case',required=True,choices=['normal','solver-failure','preexisting'])
    parser.add_argument('--previous',type=Path)
    parser.add_argument('--run-cst',action='store_true')
    args=parser.parse_args()
    if not args.run_cst:
        parser.error('real CST requires --run-cst')
    if (args.case=='preexisting') != bool(args.previous):
        parser.error('preexisting requires only a closed --previous input.cst')
    with probe.exclusive_probe(probe.ROOT):
        root=probe.ROOT/'artifacts'/('execution-capture-'+args.case+'-'+uuid4().hex[:8])
        root.mkdir(); model=root/'input.cst'
        source=(args.previous or (probe.ROOT/'model/Pillbox.cst')).resolve()
        if args.previous and not source.is_relative_to((probe.ROOT/'artifacts').resolve()):
            raise ValueError('previous source must be a closed acceptance copy')
        original=probe.digest(source)
        shutil.copy2(source,model)
        if args.previous:
            shutil.copytree(source.with_suffix(''),model.with_suffix(''))
        enabled=args.case!='solver-failure'
        config=ExecutionConfig('Default','Tet',enabled,'480',False,1)
        commands=[
            'ChangeSolverType "HF Eigenmode"',
            'Solver.FrequencyRange "fmin", "fmax"',
            'Mesh.MeshType "Tetrahedral"', 'MeshSettings.SetMeshType "Tet"',
            'MeshSettings.Set "Version", 1','MeshSettings.Set "StepsPerWaveNear", 4',
            'MeshSettings.Set "StepsPerWaveFar", 4','MeshSettings.Set "StepsPerBoxNear", 2',
            'MeshSettings.Set "StepsPerBoxFar", 1',
            'MeshSettings.Set "CellsPerWavelengthPolicy", "cellsperwavelength"',
            'EigenmodeSolver.SetMethodType "Default", "Tet"',
            'EigenmodeSolver.SetMeshType "Tetrahedral Mesh"',
            'EigenmodeSolver.SetNumberOfModes 1',
            'EigenmodeSolver.SetMeshAdaptationTet False',
            f'EigenmodeSolver.SetFrequencyTarget {str(enabled)}, "fmin*1.2"',
            'EigenmodeSolver.SetMaxNumberOfThreads 2','EigenmodeSolver.SetRemoteCalculation False',
            'EigenmodeSolver.SetCalculateExternalQFactor False',
            'EigenmodeSolver.SetCalculateThermalLosses False',
        ]
        implicit=['EigenmodeSolver.SetMethodType "Default", "Tet"',
                  'EigenmodeSolver.SetMeshType "Tetrahedral Mesh"',
                  'EigenmodeSolver.SetMeshAdaptationTet False','EigenmodeSolver.SetNumberOfModes 1']
        approved=[] if args.previous else implicit+commands
        store=RunStore(root,root/'logs/run',run_id='b4-'+args.case)
        intent=store.prepare_execution_attempt('task-'+args.case,definition_path=source,model_path=model,
                                               config=config,setup_history=approved,project_id='b4-pillbox',
                                               executable=args.cst_exe)
        macro=probe.render(root,[dict(name='B4-'+args.case,method='Default',mesh='Tet',count=1,commands=commands)],
                           reopen=bool(args.previous))
        macro=macro.replace('Dim history As String, message As String, f As Integer',
                            'Dim history As String, message As String, f As Integer\n    Dim nativeSolverReturn As Long')
        block=''
        if not args.previous:
            block+='    Stage "rebuild"\n    If Not Rebuild Then Err.Raise vbObjectError + 2920, "B4", "rebuild failed"\n    Save\n'
        block+='''    CaptureBeforeSolver
    Stage "solver-start"
    nativeSolverReturn = EigenmodeSolver.Start
    Stage "solver-return"
    CaptureAfterSolver nativeSolverReturn
'''
        macro=macro.replace('    DumpExpressions "after"',block+'    DumpExpressions "after"')
        macro+=render_capture_runtime(intent,root)
        print('EXECUTION_CAPTURE_ROOT='+str(root),flush=True)
        failure=None
        try:
            probe.run(args.cst_exe,model,root,macro,unbounded_stages=('solver-start',))
        except RuntimeError as exc:
            failure=str(exc)
        finally:
            after=probe.digest(source)
            probe.write_json_atomic(root/'source-check.json',dict(before=original,after=after,unchanged=original==after))
            if original!=after:raise RuntimeError('original source changed')
        closure=json.loads((root/'session-status.json').read_text())
        observed_report=json.loads((root/'report.json').read_text()) if (root/'report.json').exists() else {}
        closure['exit_code']=observed_report.get('exit_code')
        if not closure['exit_confirmed']:
            raise RuntimeError('owned exit unconfirmed; stop acceptance and preserve copies')
        if args.case=='preexisting':
            passed=(not (root/'native-started.tsv').exists() and not (root/'native-post.tsv').exists()
                    and (root/'native-pre.tsv').exists() and (root/'failed.txt').exists()
                    and 'preexisting or unverified execution database' in (root/'failed.txt').read_text())
            result=dict(case=args.case,guard_passed=passed,solver_start_calls=0,exit_confirmed=True,
                        failure=failure,publish_ready=False)
            probe.write_json_atomic(root/'acceptance.json',result)
            if not passed:raise RuntimeError('preexisting database guard failed')
        else:
            result=store.finalize_execution_attempt('task-'+args.case,observations=root,closure=closure)
            again=store.finalize_execution_attempt('task-'+args.case,observations=root,closure=closure)
            if result!=again:raise RuntimeError('reconciliation not idempotent')
            result={**result,'case':args.case,'reconcile_idempotent':True,'probe_failure':failure,
                    'expressions_preserved':observed_report.get('expressions_preserved')}
            probe.write_json_atomic(root/'acceptance.json',result)
            if (result['status']!='execution-snapshot-match' or
                    result['result_success'] is not (args.case=='normal') or
                    not result['expressions_preserved']):
                raise RuntimeError('B4 expected actual outcome or expression check failed')
        print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
