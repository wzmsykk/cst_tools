"""W0/W1: serial owned CST2022 copies, no solver or original engineering file.

W0 checks line samples then executes Call/ByRef and history replay. W1 constructs
the current emitted definition, followed by the existing saved/reopened G03.
Initialization-capable object/class modules are outside this Sub-only profile.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.acceptance_session import exclusive_probe, cst_processes
from csttool.configuration import write_json_atomic
from csttool.definition_editing import render_history, render_edit_macro
from csttool.definition_verifier import NativeDefinitionVerifier
from csttool.native_definition_builder import run_new_definition
from csttool.saved_project_source import read_saved_source
from csttool.winwrap_emitter import Variable, assign_string, String
from test.support.calibrate_cst_macrocheck import cases as core_cases, render, evaluate


def definition():
    return dict(parameters={
        'R':dict(expression='2',quantity='length',description='半径 "R"'),
        'L':dict(expression='2 * R',quantity='length',description='length expression')},
        components=['cavity'],cylinder=dict(object_id='pillbox',component_id='cavity',axis='z',
            center=['0']*3,axial_range=['-L/2','L/2'],outer_radius='R',inner_radius='0',material='Vacuum',segments=0),
        background=dict(material='PEC',padding_mm=[0]*6),boundaries=dict(faces=['electric']*6,symmetry=['none']*3),
        simulation=dict(solver='eigenmode',method='default',mesh=dict(type='tet',cells_per_wavelength=4,adaptive=False),
            frequency_range_mhz=dict(min=500,max=2000),frequency_lower_target_mhz=500,requested_modes=1,losses='postprocess_only'),
        postprocess=[dict(metric_id='frequency',method_id='Frequency',settings={'mode':dict(selection='one',index=1)}),
            dict(metric_id='rq',method_id='R_over_Q',settings={'mode':dict(selection='one',index=1),
                'integration_line':dict(axis='z',offset_mm=[0]*3,beta=1,range='full')})])


def samples(directory):
    rows=core_cases(directory)
    for length in (511,799,1023,2047,4095):
        body='Dim sampleText As String\nsampleText = "'+'x'*length+'"'
        rows.append(('literal-'+str(length),'\'#Language "WWB-COM"\nOption Explicit\nSub Main\n'+body+'\nEnd Sub\n',None))
    for count in (1,10,24,50):
        body='Dim sampleNumber As Double\nsampleNumber = 1'+(' + _\n1'*count)
        rows.append(('continuations-'+str(count),'\'#Language "WWB-COM"\nOption Explicit\nSub Main\n'+body+'\nEnd Sub\n',None))
    return rows


def driver(directory, rows, nonce):
    q=lambda value:String(str(value)).render()
    history=render_history(definition())[0]
    original=next(line for line in history.splitlines() if line.startswith(' .Zrange '))
    call=' Call .Zrange(((-RestoreDoubleParameter("L"))/2), (RestoreDoubleParameter("L")/2))'
    history=history.replace(original,call)
    setup='\n'.join(assign_string(Variable('w0code'),history))
    actual=f'''
    ReportStage "call-execution"
    w0scalar = 1
    w0names(0) = "before"
    Call W0Mutate(w0names, w0scalar)
    If w0names(0) <> "after" Or w0scalar <> 3 Then Err.Raise vbObjectError + 2920, "W0", "ByRef not preserved"
{setup}
    If Not AddToHistory("W0 Call cylinder", w0code) Then Err.Raise vbObjectError + 2921, "W0", "Call history failed"
    ReportStage "rebuild"
    StoreParameter "W0Base", "3"
    If Not Rebuild Then Err.Raise vbObjectError + 2922, "W0", "Call history replay failed"
    Boundary.GetStructureBox w0a, w0b, w0c, w0d, w0e, w0g
    If Abs(w0e + 3) > 0.00001 Or Abs(w0g - 3) > 0.00001 Then Err.Raise vbObjectError + 2923, "W0", "replayed dimensions differ"
    w0f = FreeFile
    Open {q(directory/'execution.tsv')} For Output As #w0f
    Print #w0f, "byref-array" & vbTab & w0names(0)
    Print #w0f, "byref-scalar" & vbTab & CStr(w0scalar)
    Print #w0f, "zmin" & vbTab & CStr(w0e)
    Print #w0f, "zmax" & vbTab & CStr(w0g)
    Close #w0f
    ReportStage "save"
'''
    macro=render(directory,rows,nonce)
    macro=macro.replace('    On Error GoTo Failed\n',
        '    Dim w0names(0 To 0) As String, w0scalar As Double\n'
        '    Dim w0a As Double, w0b As Double, w0c As Double, w0d As Double, w0e As Double, w0g As Double\n'
        '    On Error GoTo Failed\n',1)
    anchor='    w0f = FreeFile\n    Open '+q(directory/'parameter-after.txt')
    assert macro.count(anchor)==1
    macro=macro.replace(anchor,actual+anchor,1)
    macro+=f'''
Private Sub W0Mutate(ByRef items() As String, ByRef scalar As Double)
 items(0) = "after"
 scalar = scalar + 2
End Sub
Private Sub ReportStage(ByVal stage As String)
 Dim stream As Integer
 stream = FreeFile
 Open {q(directory/'stage.txt')} For Output As #stream
 Print #stream, stage
 Close #stream
End Sub
'''
    return macro,history


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-cst',action='store_true')
    parser.add_argument('--cst-exe',type=Path,default=Path('D:/Program Files (x86)/CST Studio Suite 2022/CST DESIGN ENVIRONMENT.exe'))
    args=parser.parse_args()
    if not args.run_cst:parser.error('--run-cst required')
    with exclusive_probe(ROOT):
        root=ROOT/'artifacts'/('winwrap-w01-'+uuid4().hex[:8]);root.mkdir()
        print('PROBE_ROOT='+str(root),flush=True)
        w0=root/'w0';w0.mkdir();nonce=uuid4().hex;rows=samples(w0)
        for name,code,_ in rows:(w0/(name+'.bas')).write_text(code,encoding='utf-8')
        macro,history=driver(w0,rows,nonce)
        (w0/'call-history.vb').write_text(history,encoding='ascii')
        closure=run_new_definition(args.cst_exe,w0/'definition.cst',w0,macro)
        result=evaluate(w0,rows,closure,nonce)
        actual=(w0/'execution.tsv').read_text(encoding='ascii') if (w0/'execution.tsv').exists() else None
        result['execution']=actual
        saved=read_saved_source(w0/'definition.cst',scope='root')
        result['call_saved_in_history']='Call .Zrange' in (saved.text('Model/3D/Model.mod') or '')
        result['acceptance_passed'] = result['acceptance_passed'] and actual is not None and result['call_saved_in_history']
        write_json_atomic(w0/'acceptance.json',result)
        if not result['acceptance_passed']:raise RuntimeError('W0 failed; inspect '+str(w0))
        print('W0_CONFIRMED',flush=True)
        w1=root/'project'/'documents'/'candidate';w1.mkdir(parents=True);nonce=uuid4().hex;spec=definition()
        expected=render_history(spec)[1];macro=render_edit_macro(w1,spec,nonce)
        closure=run_new_definition(args.cst_exe,w1/'definition.cst',w1,macro)
        if not closure['exit_confirmed'] or closure['exit_code']!=0 or (w1/'completed.txt').read_text().strip()!=nonce or (w1/'failed.txt').exists():
            raise RuntimeError('W1 construction failed; inspect '+str(w1))
        proof=NativeDefinitionVerifier()(w1/'definition.cst',expected,args.cst_exe)
        report=dict(w0=result,w1=dict(closure=closure,proof=proof),solver_start_calls=0,
            acceptance_passed=proof['status']=='verified',after_cst=cst_processes(),
            emitter_sha256=hashlib.sha256((ROOT/'csttool/winwrap_emitter.py').read_bytes()).hexdigest())
        write_json_atomic(root/'acceptance.json',report)
        print(json.dumps(dict(root=str(root),acceptance_passed=report['acceptance_passed'],checks=len(rows),solver_start_calls=0)),flush=True)


if __name__=='__main__':main()
