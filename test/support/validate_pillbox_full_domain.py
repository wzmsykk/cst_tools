"""Ideal-cylinder CST doublet and whole-domain masked sampling acceptance."""
import argparse
from pathlib import Path
import shutil
import subprocess
import os
import sys
from uuid import uuid4
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.acceptance_session import exclusive_probe, wait_probe
from csttool.configuration import write_json_atomic
from csttool.cst_process_env import cst_process_environment
from csttool.field_artifacts import SamplingSpec, artifacts_from_result, read_field
from csttool.field_diagnostics import run_field_diagnostic
from csttool.geometry_support import render_material_support, load_material_support
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.mode_matching import MatchPolicy, weighted_overlap, compare_subspaces
from csttool.pillbox_reference import tm110_reference
from csttool.physical_domain import DomainSupport, cylinder_support, common_quadrature, sampling_convergence
from csttool.result_reconciliation import file_hash
from csttool.saved_field_export import export_saved_fields
from test.managed_hom_ten_modes_fault_resume_integration_test import _config

RADIUS=.229
LENGTH=.259
GEOMETRY='ideal-closed-PEC-pillbox-R229mm-L259mm-v1'


def batch_probe(executable, project, root, body, helpers=''):
    root.mkdir(parents=True)
    copy=root/'input.cst'
    shutil.copy2(project,copy)
    script=root/'input/Model/3D/Model.run'
    script.parent.mkdir(parents=True)
    macro=f'''\n'#Language "WWB-COM"
Option Explicit
Sub Main
    Dim f As Integer, index As Long, shape As String, history As String, message As String
    On Error GoTo Failed
{body}
    Save
    f=FreeFile
    Open "{root/'completed.txt'}" For Output As #f
    Print #f,"SUCCESS"
    Close #f
    Exit Sub
Failed:
    message=CStr(Err.Number) & " " & Err.Description
    On Error Resume Next
    f=FreeFile
    Open "{root/'failed.txt'}" For Output As #f
    Print #f,message
    Close #f
End Sub
{helpers}
'''
    script.write_text(macro.lstrip(),encoding='ascii')
    # Result copies are required for saved-result geometry probes.
    sibling=project.with_suffix('')
    if (sibling/'Result').is_dir():
        shutil.copytree(sibling/'Result',root/'input/Result')
    with exclusive_probe(ROOT):
        with (root/'cst.log').open('wb') as log:
            options={}
            if os.name=='nt':
                info=subprocess.STARTUPINFO()
                info.dwFlags|=subprocess.STARTF_USESHOWWINDOW
                info.wShowWindow=7
                options={'startupinfo':info,'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP}
            process=subprocess.Popen([str(executable),'-m','-b',str(copy)],stdout=log,
                stderr=subprocess.STDOUT,env=cst_process_environment(),**options)
            session=wait_probe(process,root)
    assert process.returncode==0 and (root/'completed.txt').exists() and not (root/'failed.txt').exists(), root
    assert session['exit_confirmed'] and not session['foreign_processes'],session
    return copy


def prepare_ideal(executable, source, root):
    # Constant benchmark geometry; task-controlled solver settings remain history-bound.
    commands=['With Units','.Geometry "mm"','.Frequency "MHz"','End With',
        'With Background','.Reset','.Type "pec"','End With',
        'With Boundary','.Xmin "electric"','.Xmax "electric"','.Ymin "electric"',
        '.Ymax "electric"','.Zmin "electric"','.Zmax "electric"',
        '.Xsymmetry "none"','.Ysymmetry "none"','.Zsymmetry "none"','End With',
        'With Cylinder','.Reset','.Name "ideal-cavity"','.Component "domain-benchmark"',
        '.Material "Vacuum"','.Axis "z"','.OuterRadius "229"','.InnerRadius "0"',
        '.Xcenter "0"','.Ycenter "0"','.Zrange "-129.5", "129.5"','.Create','End With',
        'Solver.FrequencyRange "fmin", "fmax"','With EigenmodeSolver',
        '.SetMeshType "Tetrahedral Mesh"','.SetMethodType "Default", "Tet"',
        '.SetFrequencyTarget True, RestoreDoubleParameter("fmin")',
        '.SetNumberOfModes CInt(RestoreDoubleParameter("nmodes"))',
        '.SetMeshAdaptationTet False','End With','With MeshSettings',
        '.SetMeshType "Tet"','.Set "StepsPerWaveNear", "cell"','End With']
    body='''    StoreParameter "fmin", "780"
    StoreParameter "fmax", "850"
    StoreParameter "nmodes", "2"
    StoreParameter "cell", "20"
    history=""
    For index=Solid.GetNumberOfShapes-1 To 0 Step -1
        shape=Solid.GetNameOfShapeFromIndex(index)
        If shape="" Then Err.Raise vbObjectError+1,"probe","Empty shape name"
        history=history & "Solid.Delete """ & shape & """" & vbCrLf
    Next index
'''
    for line in commands:
        body+='    history=history & "'+line.replace('"','""')+'" & vbCrLf\n'
    body+='    If Not AddToHistory("CSTTools: ideal full-cylinder benchmark",history) Then Err.Raise vbObjectError+2,"probe","History failed"\n'
    body+='    If Not Rebuild Then Err.Raise vbObjectError+3,"probe","Rebuild failed"\n'
    return batch_probe(executable,source,root,body)


def export_native_support(executable, snapshot, spec, root):
    nx,ny,nz=spec.counts
    bounds=spec.bounds_m
    body='    WriteSupport\n'
    helpers=f'''
Sub WriteSupport
    Dim f As Integer, i As Long,j As Long,k As Long, material As String
    Dim x As Double,y As Double,z As Double,factor As Double,shape As String,shapeMaterial As String
    If Solid.GetNumberOfShapes<>1 Then Err.Raise vbObjectError+4,"probe","Not a sole-cylinder geometry"
    shape=Solid.GetNameOfShapeFromIndex(0)
    If shape<>"domain-benchmark:ideal-cavity" Then Err.Raise vbObjectError+5,"probe","Unexpected shape"
    If Solid.GetMaterialNameForShape(shape)<>"Vacuum" Then Err.Raise vbObjectError+6,"probe","Unexpected material"
    shapeMaterial=Solid.GetMaterialNameForShape(shape)
    factor=Units.GetGeometryUnitToSI
    f=FreeFile
    Open "{root/'support.tsv'}" For Output As #f
    For i=0 To {nx-1}
        x=({bounds[0]}+(i+0.5)*({bounds[1]-bounds[0]})/{nx})/factor
        For j=0 To {ny-1}
            y=({bounds[2]}+(j+0.5)*({bounds[3]-bounds[2]})/{ny})/factor
            For k=0 To {nz-1}
                z=({bounds[4]}+(k+0.5)*({bounds[5]-bounds[4]})/{nz})/factor
                material="excluded"
                If Solid.IsPointInsideShape(x,y,z,shape) Then material=shapeMaterial
                Print #f,material
            Next k
        Next j
    Next i
    Close #f
End Sub
'''
    batch_probe(executable,snapshot,root,body,helpers)
    labels=tuple((root/'support.tsv').read_text().splitlines())
    support=DomainSupport(spec,labels,GEOMETRY,'CST-Solid.IsPointInsideShape-and-GetMaterialNameForShape',True)
    analytic=cylinder_support(spec,RADIUS,-LENGTH/2,LENGTH/2,geometry_id=GEOMETRY)
    assert support.material_labels==analytic.material_labels,'Native geometry mask differs from cylinder'
    return support


def validate_bridge(executable, run_root):
    from csttool.configuration import read_json
    run_root=Path(run_root).resolve()
    run_root.relative_to((ROOT/'artifacts').resolve())
    previous=read_json(run_root/'report.json')
    assert previous['geometry']==GEOMETRY and previous['gate_passed'],previous
    snapshot=Path(previous['solve']['ProjectSnapshot'])
    before=file_hash(snapshot)
    root=run_root/('generic-bridge-'+uuid4().hex[:8])
    spec=SamplingSpec((-RADIUS,RADIUS,-RADIUS,RADIUS,-LENGTH/2,LENGTH/2),(48,48,48),'specified-domain')
    helpers=render_material_support(spec,root/'support.tsv',shape_names=('domain-benchmark:ideal-cavity',))
    batch_probe(executable,snapshot,root,'    CSTDOM_WriteSupport\n',helpers)
    support=load_material_support(spec,root/'support.tsv',expected_sha256=file_hash(root/'support.tsv'),geometry_id=GEOMETRY)
    analytic=cylinder_support(spec,RADIUS,-LENGTH/2,LENGTH/2,geometry_id=GEOMETRY)
    assert support.material_labels==analytic.material_labels
    result={'source_unchanged':file_hash(snapshot)==before,'sampling_id':spec.identity,
            'point_count':len(support.material_labels),'quadrature':common_quadrature([support],['Vacuum']).to_mapping(),
            'native_mask_matches_analytic':True,'solver_run':False,'gate_passed':True}
    assert result['source_unchanged']
    write_json_atomic(root/'bridge-result.json',result)
    print(f'BRIDGE_PASSED={root}',flush=True)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cst-exe',required=True,type=Path)
    parser.add_argument('--mesh',type=int,default=20)
    parser.add_argument('--bridge-root',type=Path,help='Verify generic native bridge against a completed benchmark; no solve')
    args=parser.parse_args()
    if args.bridge_root:
        validate_bridge(args.cst_exe,args.bridge_root)
        return
    root=ROOT/'artifacts'/('pillbox-full-domain-'+uuid4().hex[:8])
    root.mkdir(parents=True)
    print(f'ACCEPTANCE_ROOT={root}',flush=True)
    source=ROOT/'test/data/Pillbox/Pillbox.cst'
    if shutil.disk_usage(ROOT).free < 8*1024**3:
        raise RuntimeError('Need at least 8 GiB free before real field acceptance')
    before=file_hash(source)
    report={'geometry':GEOMETRY,'source_sha256':before,'mesh':args.mesh}
    worker=None
    try:
        prepared=prepare_ideal(args.cst_exe,source,root/'prepare')
        config=_config(root/'solve','0',args.cst_exe,prepared)
        config['paramList'].append({'name':'cell','type':'double'})
        config['postProcess']=[{'method':'Frequency','resultName':f'frequency_{mode}',
                               'params':{'iModeNumber':mode}} for mode in (1,2)]
        with exclusive_probe(ROOT):
            try:
                worker=ManagedCSTWorker('0',config)
                result=dict(worker.run_task('ideal-TM110-doublet',params={
                    'nmodes':2,'fmin':780,'fmax':850,'cell':args.mesh}))
                report['solve']=result
                assert result['TaskStatus']=='Success',result
            finally:
                if worker is not None:
                    try:
                        report['stop_returned']=worker.stop()
                    except Exception as error:
                        report['stop_returned']=False
                        report['stop_error']=f'{type(error).__name__}: {error}'
                    report['stop_ack']=worker.protocol.read_stop_ack(worker.session_id) is not None
                    report['exit_code']=worker._process.poll()
        assert report['stop_returned'] and report['stop_ack'] and report['exit_code']==0,report
        snapshot=Path(result['ProjectSnapshot'])
        levels=[]
        exports=[]
        supports=[]
        for n in (48,64,96):
            spec=SamplingSpec((-RADIUS,RADIUS,-RADIUS,RADIUS,-LENGTH/2,LENGTH/2),(n,n,n),'specified-domain')
            support=export_native_support(args.cst_exe,snapshot,spec,root/f'support-{n}')
            supports.append(support)
            q=common_quadrature([support],['Vacuum'])
            settings=[{'method':'ExportModeField','resultName':f'E_{mode}',
                'params':{'iModeNumber':mode,'field_kind':'E','sampling':spec.to_mapping()}} for mode in (1,2)]
            export=export_saved_fields(args.cst_exe,snapshot,root/f'fields-{n}',settings)
            exports.append(export)
            assert export['status']=='complete',export
            fields=artifacts_from_result(export['result_directory'],export['PostProcessResult'])
            data=np.stack([read_field(f) for f in fields],axis=-1)
            flat=data.reshape(-1,2)
            w=np.repeat(q.weights_m3,3)
            gram=flat.conj().T@(w[:,None]*flat)
            norms=np.sqrt(gram.diagonal().real)
            normalized=np.abs(gram/np.outer(norms,norms))
            diagnostic=run_field_diagnostic(fields,fields,MatchPolicy(.9,.05,.99),
                root/f'diagnostic-{n}.json',quadrature=q)
            analytic=tm110_reference(spec.points(),RADIUS,(-LENGTH/2,LENGTH/2))
            comparison=compare_subspaces(weighted_overlap(analytic['fields'],data,q.weights_m3,
                scope=q.scope),MatchPolicy(.9,.05,.99))
            levels.append({'counts':list(spec.counts),'volume_m3':q.volume_m3,
                          'normalized_gram_abs':normalized.tolist(),'mode_l2_norms':norms.tolist(),
                          'quadrature':q.to_mapping(),'diagnostic':diagnostic,
                          'analytic_tm110_subspace':comparison})
            report['levels']=levels
            report['exports']=exports
            write_json_atomic(root/'report.json',report)
            print(f'SAMPLING_COMPLETE n={n} volume={q.volume_m3}',flush=True)
        report['sampling_convergence']=sampling_convergence(levels,tolerance=.01,
            expected_volume_m3=np.pi*RADIUS**2*LENGTH)
        frequencies=[float(p['value']) for p in result['PostProcessResult']]
        predicted=299792458*3.8317059702075125/(2*np.pi*RADIUS)/1e6
        report['doublet']={'frequencies_mhz':frequencies,'analytic_tm110_mhz':predicted,
                          'relative_frequency_error':max(abs(f-predicted)/predicted for f in frequencies),
                          'relative_split':abs(frequencies[1]-frequencies[0])/predicted}
        report['physical_identity_confirmed']=False
        report['gate_passed']=(report['sampling_convergence']['status']=='converged'
            and report['doublet']['relative_frequency_error']<.01
            and report['doublet']['relative_split']<.01
            and all(level['analytic_tm110_subspace']['status']=='matched' for level in levels))
        print(f'GATE_PASSED={report["gate_passed"]}',flush=True)
    except BaseException as error:
        report['failure']=f'{type(error).__name__}: {error}'
        raise
    finally:
        report['source_unchanged']=file_hash(source)==before
        write_json_atomic(root/'report.json',report)
    assert report['source_unchanged']


if __name__=='__main__':
    main()
