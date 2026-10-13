"""No-solver direct setter/history/parameter persistence comparison in a copy."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.acceptance_session import exclusive_probe, wait_probe
from csttool.configuration import write_json_atomic
from csttool.cst_process_env import cst_process_environment
from csttool.result_reconciliation import file_hash


def validate_states(rows):
    labels = ['baseline', 'direct', 'direct-full-rebuild', 'history-added',
              'history-full-rebuild', 'history-partial-update',
              'history-full-update', 'restored']
    if [row[0] for row in rows] != labels or any(len(row) != 7 for row in rows):
        raise ValueError('missing or malformed persistence stage')
    original = rows[0][1]
    expected = [original, 'open', original, 'open', 'open', 'open', 'open', original]
    if [row[1] for row in rows] != expected:
        raise ValueError('boundary persistence differs from tested expectation')
    for index, row in enumerate(rows):
        gap = 140 if 1 <= index <= 4 else 150
        if float(row[2]) != gap or float(row[4]) != (260-gap)/2:
            raise ValueError('parameter value or dependency did not survive update')
        if row[3] != rows[0][3]:
            raise ValueError('parameter expression was replaced')
        if index and (row[5] != 'kept' or row[6] != '1'):
            raise ValueError('independent storage was reset')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True)
    args = parser.parse_args()
    with exclusive_probe(ROOT):
        root = ROOT / 'artifacts' / ('history-persistence-' + uuid4().hex[:8])
        root.mkdir(parents=True)
        source = ROOT / 'artifacts/hom-mesh-baseline-de2d6b90/cell-30/prepared.cst'
        before = file_hash(source)
        project = root / 'input.cst'
        shutil.copy2(source, project)
        script = root / 'input/Model/3D/Model.run'
        script.parent.mkdir(parents=True)
        macro = f'''\n'#Language "WWB-COM"
Option Explicit
Sub Main
    Dim originalBoundary As String, f As Integer, message As String
    On Error GoTo Failed
    originalBoundary = Boundary.GetXmax
    SetGlobalData "cst_tools_persistence_probe", "initial"
    DumpState "baseline"
    StoreParameter "Gap", "140"
    StoreParameter "probe_boundary", "1"
    SetGlobalData "cst_tools_persistence_probe", "kept"
    Boundary.Xmax "open"
    DumpState "direct"
    If Not Rebuild Then Err.Raise vbObjectError+1, "probe", "Direct rebuild failed"
    DumpState "direct-full-rebuild"
    If Not AddToHistory("CSTTools: persistence probe", "Boundary.Xmax ""open""") Then Err.Raise vbObjectError+2, "probe", "AddToHistory failed"
    DumpState "history-added"
    If Not Rebuild Then Err.Raise vbObjectError+3, "probe", "History rebuild failed"
    DumpState "history-full-rebuild"
    StoreParameter "Gap", "150"
    If Not RebuildOnParametricChange(False, False) Then Err.Raise vbObjectError+4, "probe", "Partial update failed"
    DumpState "history-partial-update"
    If Not RebuildOnParametricChange(True, False) Then Err.Raise vbObjectError+5, "probe", "Full update failed"
    DumpState "history-full-update"
    If Not AddToHistory("CSTTools: persistence probe", "Boundary.Xmax """ & originalBoundary & """") Then Err.Raise vbObjectError+6, "probe", "Restore history failed"
    If Not Rebuild Then Err.Raise vbObjectError+7, "probe", "Restore rebuild failed"
    DumpState "restored"
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

Sub DumpState(label As String)
    Dim f As Integer, probeValue As String
    probeValue="absent"
    If DoesParameterExist("probe_boundary") Then probeValue=CStr(RestoreDoubleParameter("probe_boundary"))
    f=FreeFile
    Open "{root/'states.tsv'}" For Append As #f
    Print #f,label & Chr(9) & Boundary.GetXmax & Chr(9) & CStr(RestoreDoubleParameter("Gap")) & Chr(9) & RestoreParameterExpression("concaveL") & Chr(9) & CStr(RestoreDoubleParameter("concaveL")) & Chr(9) & GetGlobalData("cst_tools_persistence_probe") & Chr(9) & probeValue
    Close #f
End Sub
'''
        script.write_text(macro.lstrip(), encoding='ascii')
        print(f'ACCEPTANCE_ROOT={root}', flush=True)
        report = {}
        try:
            with (root / 'cst.log').open('wb') as log:
                process = subprocess.Popen([args.cst_exe, '-m', '-b', str(project)],
                    stdout=log, stderr=subprocess.STDOUT, env=cst_process_environment())
                report['session'] = wait_probe(process, root)
            report['exit_code'] = process.returncode
            report['completed'] = (root / 'completed.txt').exists()
            report['rows'] = [line.split('\t') for line in (root / 'states.tsv').read_text().splitlines()]
            validate_states(report['rows'])
            report['persistence_checks_passed'] = True
        finally:
            report['source_unchanged'] = file_hash(source) == before
            write_json_atomic(root / 'report.json', report)
        assert report['completed'] and report['exit_code'] == 0 and report['source_unchanged'], report
        assert report['session']['exit_confirmed'], report
        print(report['rows'], flush=True)


if __name__ == '__main__':
    main()
