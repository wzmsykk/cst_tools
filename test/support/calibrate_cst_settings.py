"""Serial, no-solver CST settings calibration in disposable project copies.

This is an acceptance probe, not a production settings reader. Optional
MeshSettings.Get is deliberately late-bound and reported as an undocumented
candidate; failures remain observations rather than silently using requests.
"""
import argparse
import hashlib
import json
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


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cases():
    result = []
    for mesh, method in [('Tet', 'Default'), ('Tet', 'General (Lossy)'), ('Hex', 'AKS')]:
        for count in (1, 2):
            result.append(dict(name=f'V03-{mesh}-{method.replace(" ", "")}-{count}',
                               mesh=mesh, method=method, count=count, commands=[]))
    for name, commands in [
        ('V05-legacy4', ['Mesh.StepsPerWavelengthTet 4']),
        ('V05-legacy6', ['Mesh.StepsPerWavelengthTet 6']),
        ('V05-near8-far3', ['MeshSettings.SetMeshType "Tet"',
                            'MeshSettings.Set "StepsPerWaveNear", "8"',
                            'MeshSettings.Set "StepsPerWaveFar", "3"',
                            'MeshSettings.Set "CellsPerWavelengthPolicy", "cellsperwavelength"']),
        ('V05-new-then-legacy6', ['MeshSettings.SetMeshType "Tet"',
                                 'MeshSettings.Set "StepsPerWaveNear", "8"',
                                 'MeshSettings.Set "StepsPerWaveFar", "3"',
                                 'MeshSettings.Set "CellsPerWavelengthPolicy", "cellsperwavelength"',
                                 'Mesh.StepsPerWavelengthTet 6']),
        ('V05-legacy6-then-new', ['Mesh.StepsPerWavelengthTet 6',
                                 'MeshSettings.SetMeshType "Tet"',
                                 'MeshSettings.Set "StepsPerWaveNear", "8"',
                                 'MeshSettings.Set "StepsPerWaveFar", "3"',
                                 'MeshSettings.Set "CellsPerWavelengthPolicy", "cellsperwavelength"']),
        ('V02-target-zero', ['EigenmodeSolver.SetFrequencyTarget True, 0']),
        ('V02-target-480', ['EigenmodeSolver.SetFrequencyTarget True, 480']),
        ('V02-target-disabled', ['EigenmodeSolver.SetFrequencyTarget False, 480']),
        ('V04-adaptive-true', ['EigenmodeSolver.SetMeshAdaptationTet True']),
        ('V04-adaptive-false', ['EigenmodeSolver.SetMeshAdaptationTet False']),
        ('V06-expression', ['EigenmodeSolver.SetNumberOfModes "nmodes+1"',
                            'EigenmodeSolver.SetFrequencyTarget True, "fmin*1.2"']),
        ('V06-reset', ['EigenmodeSolver.Reset']),
    ]:
        result.append(dict(name=name, mesh='Tet', method='Default', count=1, commands=commands))
    return result


def vb(value):
    return str(value).replace('"', '""')


def render(directory, selected, *, reopen=False):
    blocks = []
    for case in selected:
        label = case['name']
        if not reopen:
            kind = 'Tetrahedral Mesh' if case['mesh'] == 'Tet' else 'Hexahedral Mesh'
            commands = [f'EigenmodeSolver.SetMethodType "{case["method"]}", "{case["mesh"]}"',
                        f'EigenmodeSolver.SetMeshType "{kind}"',
                        'EigenmodeSolver.SetMeshAdaptationTet False',
                        f'EigenmodeSolver.SetNumberOfModes {case["count"]}'] + case['commands']
            # Unique captions: do not exploit adjacent-caption replacement.
            history = ' & vbCrLf & '.join('"' + vb(c) + '"' for c in commands)
            blocks += [f'    Stage "apply:{label}"', f'    history = {history}',
                       f'    If Not AddToHistory("CSTTools calibration {label}", history) Then Err.Raise vbObjectError + 2701, "calibration", "history rejected"']
            if label == 'V06-expression':
                blocks += ['    Stage "rebuild:expression"',
                           '    If Not Rebuild Then Err.Raise vbObjectError + 2702, "calibration", "rebuild rejected"']
        blocks += [f'    Stage "query:{label}"', f'    DumpState "{label}"']
        if not reopen:
            blocks += [f'    Stage "backup:{label}"', f'    Backup "{vb(directory / (label + ".cst"))}"']
    return ''''#Language "WWB-COM"
Option Explicit
Sub Main
    Dim history As String, message As String, f As Integer
    On Error GoTo Failed
    Stage "started"
    DumpExpressions "before"
''' + '\n'.join(blocks) + f'''
    DumpExpressions "after"
    Stage "save"
    Save
    f = FreeFile
    Open "{vb(directory / 'completed.txt')}" For Output As #f
    Print #f, "SUCCESS"
    Close #f
    Stage "batch-return"
    Exit Sub
Failed:
    message = CStr(Err.Number) & " " & Err.Description
    On Error Resume Next
    f = FreeFile
    Open "{vb(directory / 'failed.txt')}" For Output As #f
    Print #f, message
    Close #f
    Stage "failed-return"
End Sub

Sub Stage(value As String)
    Dim f As Integer
    f = FreeFile
    Open "{vb(directory / 'stage.txt')}" For Output As #f
    Print #f, value
    Close #f
End Sub

Sub DumpExpressions(label As String)
    Dim f As Integer, i As Long
    f = FreeFile
    Open "{vb(directory / 'expressions.tsv')}" For Append As #f
    For i = 0 To GetNumberOfParameters - 1
        Print #f, label & Chr(9) & GetParameterName(i) & Chr(9) & GetParameterSValue(i)
    Next i
    Close #f
End Sub

Function ReadAks() As String
    On Error GoTo Failed
    ReadAks = "OK:" & CStr(Solver.AKSGetNumberOfModes)
    Exit Function
Failed:
    ReadAks = "ERROR:" & CStr(Err.Number) & ":" & Err.Description
End Function

Function ReadMeshCandidate(key As String) As String
    Dim projectObject As Object, settingsObject As Object, value As Variant
    On Error GoTo Failed
    Set projectObject = GetOwnProject
    Set settingsObject = projectObject.MeshSettings
    settingsObject.SetMeshType "Tet"
    value = settingsObject.Get(key)
    ReadMeshCandidate = "OK:" & CStr(value)
    Exit Function
Failed:
    ReadMeshCandidate = "ERROR:" & CStr(Err.Number) & ":" & Err.Description
End Function

Sub DumpState(label As String)
    Dim f As Integer, aks As String, near As String, far As String, policy As String
    aks = ReadAks()
    near = ReadMeshCandidate("StepsPerWaveNear")
    far = ReadMeshCandidate("StepsPerWaveFar")
    policy = ReadMeshCandidate("CellsPerWavelengthPolicy")
    f = FreeFile
    Open "{vb(directory / 'states.tsv')}" For Append As #f
    Print #f, label & Chr(9) & GetSolverType() & Chr(9) & Mesh.GetMeshType & Chr(9) & aks & Chr(9) & near & Chr(9) & far & Chr(9) & policy & Chr(9) & CStr(Solver.GetFmin) & Chr(9) & CStr(Solver.GetFmax)
    Close #f
End Sub
'''


def run(executable, project, directory, macro, *, unbounded_stages=()):
    script = project.with_suffix('') / 'Model/3D/Model.run'
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(macro, encoding='ascii')
    (directory / 'probe.bas').write_text(macro, encoding='ascii')
    with (directory / 'cst.log').open('wb') as log:
        process = subprocess.Popen([str(executable), '-m', '-b', str(project)],
                                   stdout=log, stderr=subprocess.STDOUT,
                                   env=cst_process_environment(), cwd=directory)
        session = wait_probe(process, directory, task_project=project,
                             unbounded_stages=unbounded_stages)
    result = dict(session=session, exit_code=process.returncode,
                  completed=(directory / 'completed.txt').is_file())
    if (directory / 'failed.txt').exists():
        result['macro_error'] = (directory / 'failed.txt').read_text(errors='replace')
    if (directory / 'states.tsv').exists():
        result['rows'] = [line.split('\t') for line in (directory / 'states.tsv').read_text().splitlines()]
    expressions = (directory / 'expressions.tsv').read_text().splitlines() if (directory / 'expressions.tsv').exists() else []
    before = [line.split('\t', 1)[1] for line in expressions if line.startswith('before\t')]
    after = [line.split('\t', 1)[1] for line in expressions if line.startswith('after\t')]
    result['expressions_preserved'] = bool(before) and before == after
    write_json_atomic(directory / 'report.json', result)
    if (not session['exit_confirmed'] or not result['completed']
            or process.returncode != 0 or not result['expressions_preserved']):
        raise RuntimeError(f'calibration did not complete normally: {directory}; {result}')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True, type=Path)
    parser.add_argument('--source', type=Path, default=ROOT / 'model/Pillbox.cst')
    parser.add_argument('--reopen', type=Path, help='Existing calibration root: verify each saved case serially')
    parser.add_argument('--case', action='append', help='Restrict cases by exact name')
    args = parser.parse_args()
    unknown = set(args.case or ()) - {c['name'] for c in cases()}
    if unknown:
        parser.error('unknown cases: ' + ', '.join(sorted(unknown)))
    selected = [c for c in cases() if not args.case or c['name'] in args.case]
    if not selected:
        raise ValueError('no selected calibration cases')
    with exclusive_probe(ROOT):
        if args.reopen:
            origin = args.reopen.resolve()
            for case in selected:
                source = origin / (case['name'] + '.cst')
                original = digest(source)
                directory = origin / ('reopen-' + case['name'])
                directory.mkdir(exist_ok=False)
                project = directory / 'input.cst'
                shutil.copy2(source, project)
                print('CALIBRATION_REOPEN=' + str(directory), flush=True)
                try:
                    report = run(args.cst_exe, project, directory, render(directory, [case], reopen=True))
                finally:
                    after = digest(source)
                    write_json_atomic(directory / 'source-check.json', dict(source=str(source),
                                      before=original, after=after, unchanged=original == after))
                    if after != original:
                        raise RuntimeError('saved source changed')
                print(json.dumps(report, ensure_ascii=False), flush=True)
        else:
            source = args.source.resolve()
            before = digest(source)
            directory = ROOT / 'artifacts' / ('settings-calibration-' + uuid4().hex[:8])
            directory.mkdir()
            project = directory / 'input.cst'
            shutil.copy2(source, project)
            write_json_atomic(directory / 'plan.json', dict(source=str(source), source_sha256=before,
                              cases=selected, solver_calls_expected=0))
            print('CALIBRATION_ROOT=' + str(directory), flush=True)
            try:
                report = run(args.cst_exe, project, directory, render(directory, selected))
                print(json.dumps(report, ensure_ascii=False), flush=True)
            finally:
                after = digest(source)
                write_json_atomic(directory / 'source-check.json', dict(source=str(source), before=before,
                                  after=after, unchanged=after == before))
                if after != before:
                    raise RuntimeError('original project changed; inspect source-check.json')


if __name__ == '__main__':
    main()
