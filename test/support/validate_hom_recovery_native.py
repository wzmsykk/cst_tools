"""Real small-grid mesh round trip and scanner probe/confirm recovery.

Test-only open boundary causes actual solver rejection, never fake a result.
"""
import argparse
from pathlib import Path
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.configuration import write_json_atomic,read_json
from csttool.acceptance_session import exclusive_probe,cst_processes
from csttool.cst_preprocessor import CstProjectPreprocessor
from csttool.application_service import ApplicationService
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.hom_scan import (ScanPolicy,AdaptiveHomScanner,ScanCheckpointStore,TaskModeResults,
                             ModeResult,RecoverableSolveError,ScanInterrupted)
from test.managed_hom_ten_modes_fault_resume_integration_test import _config
from test.support.validate_public_faults import digest,cleanup_case


class FixturePreprocessor(CstProjectPreprocessor):
    def render_macro(self,*args,**kwargs):
        macro=super().render_macro(*args,**kwargs)
        anchor='    WriteStage "rebuild"'
        assert macro.count(anchor)==1
        # Same deconfounding geometry settings as the dated V05 calibration.
        # Test fixture only: production geometry-density settings stay intact.
        body=('    If Not AddToHistory("test fixture: isolate wavelength density", '
              '"With MeshSettings" & vbCrLf & ".SetMeshType ""Tet""" & vbCrLf & '
              '".Set ""StepsPerBoxNear"", ""2""" & vbCrLf & '
              '".Set ""StepsPerBoxFar"", ""1""" & vbCrLf & "End With") Then Err.Raise 2993\n')
        return macro.replace(anchor,body+anchor)


class MeshWorker(ManagedCSTWorker):
    reject=False
    def _build_macro(self):
        super()._build_macro()
        macro=self.macro_path.read_text(encoding='ascii')
        declaration='    Dim solverReturn As Long'
        assert macro.count(declaration)==1
        macro=macro.replace(declaration,declaration+'\n    Dim CSTToolsMeshFile As Integer')
        anchor='            CustomPostProcess'
        assert macro.count(anchor)==1
        macro=macro.replace(anchor,'            CSTToolsMeshFile=FreeFile\n'
            '            Open outFullDir & "mesh-cells.txt" For Output As #CSTToolsMeshFile\n'
            '            Print #CSTToolsMeshFile, CStr(Mesh.GetNumberOfMeshCells)\n'
            '            Print #CSTToolsMeshFile, RestoreParameterExpression("cell")\n            Close #CSTToolsMeshFile\n'+anchor)
        if self.reject:
            anchor='            stage = "solver-config"';assert macro.count(anchor)==1
            macro=macro.replace(anchor,anchor+'\n'
                '            If Not AddToHistory("recovery fault", "Boundary.Xmax ""open""") Then Err.Raise 2991\n'
                '            If Boundary.GetXmax <> "open" Then Err.Raise 2992\n')
        self.macro_path.write_text(macro,encoding='ascii')
        self.batch_script_path.write_text(macro,encoding='ascii')


def config(root,exe,source):
    value=_config(root,'0',exe,source)
    value['paramList'].append(dict(name='cell',type='double'))
    value['postProcess']=[dict(method='Frequency',resultName='frequency',params=dict(iModeNumber=1)),
        dict(method='R_over_Q',resultName='rq',params=dict(iModeNumber=1,axis='z',xoffset=0,yoffset=0,zoffset=0))]
    return value


def stop(worker,*,failed=False):
    try:worker.stop()
    except Exception:
        if not failed or not worker.retire_failed_session():raise


def run(exe,source,root):
    report=dict(passed=False,source_sha256=digest(source),attempts=[])
    prepared=root/'processed.cst'
    try:
        FixturePreprocessor(exe,ROOT/'data/preprocess_hom_parameters_v1.vb').preprocess(
            source,prepared,root/'params.json',root/'prepare',mesh_cells_per_wavelength=4)
        baseline=digest(prepared)
        # Exercise the migrated G03 batch launcher without changing the model.
        service=ApplicationService(root/'g03','mesh-recovery',installations={'local':exe})
        # HOM preprocessing history is not automatically the public A1 profile.
        definition=service.stage_definition('pillbox',source,'local')
        service.verify_definition('pillbox',definition['definition_revision'])
        worker=MeshWorker('0',config(root/'roundtrip',exe,prepared))
        meshes=[]
        try:
            for cell in [4,6,4]:
                result=dict(worker.run_task('cell-'+str(cell),params=dict(nmodes=1,fmin=500,fmax=2000,cell=cell)))
                assert result['TaskStatus']=='Success',result
                metrics=Path(result['ResultDirectory'])/'mesh-cells.txt'
                lines=metrics.read_text(encoding='utf-8-sig').splitlines()
                assert len(lines)==2 and float(lines[1])==cell
                meshes.append(dict(cell=cell,cell_expression=lines[1],actual_cells=int(lines[0]),task_id=result['TaskID']))
        finally:stop(worker)
        report['mesh_roundtrip']=meshes
        assert meshes[1]['actual_cells']>meshes[0]['actual_cells']
        assert abs(meshes[2]['actual_cells']/meshes[0]['actual_cells']-1)<=.05
        policy=ScanPolicy(1000,1050,1150,window_width=50,failure_recovery=True,base_mesh_cells=4,max_solver_calls=20)
        checkpoint=ScanCheckpointStore(root/'scan.json')
        from csttool.run_store import RunStore
        from csttool.checkpoint_adoption import mark_adopted
        adoption=RunStore(root,root/'scan-store');receipts={}
        paused=set();report['pauses']=[]
        def save(state,pending):
            checkpoint.save(policy,{'source_sha256':baseline},state,pending)
            for task in state.adopted_task_ids:
                mark_adopted(receipts[task],adoption,task,checkpoint=str(checkpoint.path))
            recovery=next(iter(state.recovery_states.values()),None)
            label=('before-'+recovery['phase']) if recovery else ('after-confirm' if state.modes else None)
            if label and label not in paused:
                paused.add(label);report['pauses'].append(label)
                # Test-only interruption after durable write, before next effect.
                raise ScanInterrupted(state,pending)
        def solve(request):
            number=len(report['attempts']);directory=root/('attempt-'+str(number))
            MeshWorker.reject=request.recovery_phase in ('normal','mesh') and request.interval.lo==1000
            worker=MeshWorker('0',config(directory,exe,prepared));result=None
            try:
                result=dict(worker.run_task('recovery-'+request.recovery_phase,params=dict(nmodes=1,
                    fmin=request.solve_lo,fmax=request.solve_hi,cell=request.mesh_cells or 4)))
                report['attempts'].append(dict(phase=request.recovery_phase,lo=request.solve_lo,hi=request.solve_hi,
                    cell=request.mesh_cells,result=result))
            finally:stop(worker,failed=result is not None and result['TaskStatus']=='Failure')
            if result['TaskStatus']!='Success':
                assert str(result['FailureReport']).startswith('SOLVER_FAILED:'),result
                raise RecoverableSolveError(result['FailureReport'])
            metrics={row['resultName']:float(row['value']) for row in result['PostProcessResult']}
            receipts[result['TaskID']]=Path(result['ReceiptPath'])
            return TaskModeResults([ModeResult(1,metrics['frequency'],metrics,task_id=result['TaskID'])],task_id=result['TaskID'])
        restored=None;pending=None;report['resumes']=[]
        expected=[None]
        def resume(request):
            if expected[0] is not None:
                label=expected[0];expected[0]=None
                report['resumes'].append(dict(pause=label,first_phase=request.recovery_phase))
                if label.startswith('before-'):assert request.recovery_phase==label[7:]
            return solve(request)
        while True:
            try:
                final=AdaptiveHomScanner(policy).run(resume,report=restored,pending=pending,checkpoint=save)
                break
            except ScanInterrupted:
                restored,pending=checkpoint.load(policy,{'source_sha256':baseline})
                expected[0]=report['pauses'][-1]
        assert set(paused)=={'before-mesh','before-probe','before-confirm','after-confirm'}
        report['resume_first_phase']=next(x['first_phase'] for x in report['resumes'] if x['pause']=='before-confirm')
        report['modes']=[dict(frequency=m.frequency,values=m.values) for m in final.modes]
        assert final.modes and all('rq' in m.values and m.values['rq']>0 for m in final.modes)
        assert digest(prepared)==baseline and digest(source)==report['source_sha256']
        report['passed']=True
    except BaseException as error:
        report['error']=f'{type(error).__name__}: {error}';raise
    finally:
        report['remaining_cst']=cst_processes();write_json_atomic(root/'report.json',report)
    report['cleaned_companions']=cleanup_case(root,source)
    write_json_atomic(root/'report.json',report)
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cst-exe',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--run-cst',action='store_true')
    args=parser.parse_args()
    if not args.run_cst:parser.error('explicit --run-cst required')
    with exclusive_probe(ROOT):
        root=ROOT/'artifacts'/('hom-recovery-native-'+uuid4().hex[:8]);root.mkdir()
        print('HOM_RECOVERY_ROOT='+str(root),flush=True)
        run(args.cst_exe.resolve(),args.source.resolve(),root)


if __name__=='__main__':main()
