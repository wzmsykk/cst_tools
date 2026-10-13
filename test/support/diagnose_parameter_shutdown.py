"""No-solver, source-preserving lifecycle isolation probes."""
import argparse
from pathlib import Path
import subprocess
import shutil
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.acceptance_session import exclusive_probe, wait_probe
from csttool.configuration import write_json_atomic
from csttool.cst_process_env import cst_process_environment
from csttool.result_reconciliation import file_hash


def validate_linked_values(path):
    rows=[line.split('\t') for line in Path(path).read_text().splitlines()]
    if [row[0] for row in rows] != ['before','changed','restored']:
        raise ValueError('incomplete dependency stages')
    expressions=(rows[0][1],rows[0][3])
    for row,expected in zip(rows,(55.0,60.0,55.0)):
        if (row[1],row[3]) != expressions:
            raise ValueError('parameter expression changed')
        if any(abs(float(row[column])-expected)>1e-9 for column in (2,4)):
            raise ValueError('dependent parameter value is stale')
    return {'expressions':expressions,'values':[float(row[2]) for row in rows]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cst-exe',required=True)
    parser.add_argument('--probe',choices=['all','save','parameters','rebuild','parametric','declared','scope','project-script','project-script-dependent'],default='all')
    args=parser.parse_args()
    source=ROOT/'artifacts/hom-mesh-baseline-de2d6b90/cell-30/prepared.cst'
    before=file_hash(source)
    destination=ROOT/'artifacts'/('parameter-shutdown-'+uuid4().hex[:8])
    print(f'PROBE_ROOT={destination}',flush=True)
    reports=[]
    with exclusive_probe(ROOT):
        for name in (('save','parameters','rebuild','parametric') if args.probe=='all' else (args.probe,)):
            directory=destination/name
            directory.mkdir(parents=True)
            steps=''
            if name!='save':
                steps+='    StoreParameter "fmin", "513.492631838138"\n    StoreParameter "fmax", "713.492631838138"\n    StoreParameter "nmodes", "2"\n'
            if name in ('rebuild','preloaded','project-script'):
                steps+='    If Not Rebuild Then Err.Raise vbObjectError+1, "probe", "Rebuild failed"\n'
            if name=='parametric':
                steps+='    If Not RebuildOnParametricChange(False,False) Then Err.Raise vbObjectError+1, "probe", "Parametric rebuild failed"\n'
            declarations=''
            helper=''
            if name in ('scope','ds-sync','project-script-dependent'):
                helper=f'''
Sub DumpScopes(label As String)
    Dim scopeFile As Integer, index As Long
    scopeFile=FreeFile
    Open "{directory/'scopes.tsv'}" For Append As #scopeFile
    For index=0 To GetNumberOfParameters()-1
        Print #scopeFile,label & Chr(9) & "3D" & Chr(9) & GetParameterName(index) & Chr(9) & GetParameterSValue(index) & Chr(9) & CStr(GetParameterNValue(index))
    Next index
    For index=0 To DS.GetNumberOfParameters()-1
        Print #scopeFile,label & Chr(9) & "DS" & Chr(9) & DS.GetParameterName(index) & Chr(9) & DS.GetParameterSValue(index) & Chr(9) & CStr(DS.GetParameterNValue(index))
    Next index
    Close #scopeFile
End Sub
'''
                declarations=''
                steps+='    DumpScopes "before"\n'
                if name=='ds-sync':
                    steps+='''    ReDim scopeNames(GetNumberOfParameters()-1), scopeExpressions(GetNumberOfParameters()-1)
    For scopeIndex=0 To GetNumberOfParameters()-1
        scopeNames(scopeIndex)=GetParameterName(scopeIndex)
        scopeExpressions(scopeIndex)=GetParameterSValue(scopeIndex)
    Next scopeIndex
    DS.StoreParameters scopeNames,scopeExpressions
'''
                steps+='    If Not Rebuild Then Err.Raise vbObjectError+1, "probe", "Rebuild failed"\n    DumpScopes "after"\n'
                if name=='project-script-dependent':
                    steps+='''    StoreParameter "Gap", "140"
    If Not Rebuild Then Err.Raise vbObjectError+1, "probe", "Dependency rebuild failed"
    DumpScopes "changed-gap"
    StoreParameter "Gap", "150"
    If Not Rebuild Then Err.Raise vbObjectError+1, "probe", "Restore rebuild failed"
    DumpScopes "restored-gap"
'''
            if name=='declared':
                declarations='Public concaveL As Double, concaveR As Double, Leq As Double, Gap As Double\n'
                steps+='    concaveL=Evaluate("concaveL")\n    concaveR=Evaluate("concaveR")\n    Leq=Evaluate("Leq")\n    Gap=Evaluate("Gap")\n'
                steps+='    If Not Rebuild Then Err.Raise vbObjectError+1, "probe", "Rebuild failed"\n'
            if name=='project-script-dependent':
                helper=''
                steps='''    f=FreeFile
    Open "'''+str(directory/'linked.tsv')+'''" For Output As #f
    Print #f,"before" & Chr(9) & RestoreParameterExpression("concaveL") & Chr(9) & CStr(RestoreDoubleParameter("concaveL")) & Chr(9) & RestoreParameterExpression("concaveR") & Chr(9) & CStr(RestoreDoubleParameter("concaveR"))
    StoreParameter "Gap", "140"
    If Not Rebuild Then Err.Raise vbObjectError+1, "probe", "Dependency rebuild failed"
    Print #f,"changed" & Chr(9) & RestoreParameterExpression("concaveL") & Chr(9) & CStr(RestoreDoubleParameter("concaveL")) & Chr(9) & RestoreParameterExpression("concaveR") & Chr(9) & CStr(RestoreDoubleParameter("concaveR"))
    Backup "'''+str(directory/'changed-gap.cst')+'''"
    StoreParameter "Gap", "150"
    If Not Rebuild Then Err.Raise vbObjectError+1, "probe", "Restore rebuild failed"
    Print #f,"restored" & Chr(9) & RestoreParameterExpression("concaveL") & Chr(9) & CStr(RestoreDoubleParameter("concaveL")) & Chr(9) & RestoreParameterExpression("concaveR") & Chr(9) & CStr(RestoreDoubleParameter("concaveR"))
    Close #f
'''
            macro=f'''\n'#Language "WWB-COM"
Option Explicit
{declarations}
Sub Main
    Dim f As Integer,message As String
    Dim scopeNames() As String, scopeExpressions() As String, scopeIndex As Long
    On Error GoTo Failed
    OpenFile "{source}"
    SaveAs "{directory/'copy.cst'}",True
{steps}    Save
    f=FreeFile
    Open "{directory/'completed.txt'}" For Output As #f
    Print #f,"SUCCESS"
    Close #f
    Exit Sub
Failed:
    message=CStr(Err.Number) & " " & Err.Description
    On Error Resume Next
    f=FreeFile
    Open "{directory/'failed.txt'}" For Output As #f
    Print #f,message
    Close #f
End Sub
{helper}
'''
            path=directory/'probe.bas'
            command=[args.cst_exe,'-m',str(path)]
            if name=='preloaded':
                input_copy=directory/'input.cst'
                shutil.copy2(source,input_copy)
                macro=macro.replace(f'    OpenFile "{source}"\n','')
                command=[args.cst_exe,'-m','--project-file',str(input_copy),str(path)]
            if name in ('project-script','project-script-dependent'):
                input_copy=directory/'input.cst'
                shutil.copy2(source,input_copy)
                macro=macro.replace(f'    OpenFile "{source}"\n','')
                path=directory/'input'/'Model'/'3D'/'Model.run'
                path.parent.mkdir(parents=True,exist_ok=True)
                command=[args.cst_exe,'-m','-b',str(input_copy)]
            path.write_text(macro.lstrip(),encoding='ascii')
            with (directory/'cst.log').open('wb') as log:
                process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,
                                         env=cst_process_environment())
                session=wait_probe(process,directory)
            text=(directory/'cst.log').read_text(errors='replace')
            report={'probe':name,'session':session,'exit_code':process.returncode,
                    'source_unchanged':file_hash(source)==before,
                    'completion':(directory/'completed.txt').exists(),
                    'scalar_error':'Expecting an existing scalar var.' in text,
                    'batch_close_error':'Unable to close sheet while a batch job is running' in text}
            if name=='project-script-dependent' and report['completion']:
                report['dependency_check']=validate_linked_values(directory/'linked.tsv')
            reports.append(report)
            write_json_atomic(destination/'report.json',reports)
            print({k:report[k] for k in ('probe','exit_code','completion','scalar_error','batch_close_error')},flush=True)
    return 0 if all(p['completion'] and p['source_unchanged'] and p['exit_code']==0 for p in reports) else 1


if __name__=='__main__':
    raise SystemExit(main())
