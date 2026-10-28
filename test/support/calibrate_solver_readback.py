"""V01/V02/V04 bounded database-key calibration in serial copies.

Default: no solve. --solve requires one explicitly selected coarse single-mode
case. --stale-source reopens a closed acceptance copy with its results, changes
settings and rebuilds without recomputing.

Key leaf names and objdata/EigenmodeParameter originate from installed binary
strings, not an official key schema. Hierarchy variants are hypotheses until
controlled value changes and immutable-snapshot reopen corroborate them.
"""
import argparse
import json
from pathlib import Path
import shutil
from uuid import uuid4

import calibrate_cst_settings as probe


def cases():
    result = []
    for name, method, commands in [
        ('V01-default', 'Default', []),
        ('V01-general', 'General (Lossy)', []),
        ('V01-default-again', 'Default', []),
        ('V02-zero', 'Default', ['EigenmodeSolver.SetFrequencyTarget True, 0']),
        ('V02-480', 'Default', ['EigenmodeSolver.SetFrequencyTarget True, 480']),
        ('V02-disabled', 'Default', ['EigenmodeSolver.SetFrequencyTarget False, 480']),
        ('V02-expression', 'Default', ['EigenmodeSolver.SetFrequencyTarget True, "fmin*1.2"']),
        ('V02-precision', 'Default', ['EigenmodeSolver.SetFrequencyTarget True, "fmin*1.23456789"']),
        ('V04-false', 'Default', ['EigenmodeSolver.SetMeshAdaptationTet False']),
        ('V04-true', 'Default', ['EigenmodeSolver.SetMeshAdaptationTet True']),
        ('V04-false-again', 'Default', ['EigenmodeSolver.SetMeshAdaptationTet False']),
    ]:
        result.append(dict(name=name, mesh='Tet', method=method, count=1, commands=commands))
    return result


def keys():
    leaves = ['SolverTypeTet', 'FrequencyTargetActive', 'FrequencyTargetValue',
              'AdaptionActiveTet', 'MeshType', 'Modes']
    return (['EigenmodeSolverType', 'EigenmodeSolverMeshType', 'FrequencyTarget']
            + [prefix + leaf for prefix in ['', 'EigenmodeParameter\\',
                'objdata\\EigenmodeParameter\\'] for leaf in leaves]
            + ['CSTToolsCalibrationMissingKey'])


def render(directory, selected, *, reopen=False, solve=False):
    if solve:
        if reopen or len(selected) != 1:
            raise ValueError('solve probe requires one explicit fresh case')
        common = ['MeshSettings.SetMeshType "Tet"', 'MeshSettings.Set "Version", 1',
                  'MeshSettings.Set "StepsPerWaveNear", "4"',
                  'MeshSettings.Set "StepsPerWaveFar", "4"',
                  'MeshSettings.Set "CellsPerWavelengthPolicy", "cellsperwavelength"',
                  'MeshSettings.Set "StepsPerBoxNear", "2"',
                  'MeshSettings.Set "StepsPerBoxFar", "1"',
                  'EigenmodeSolver.SetMaxNumberOfThreads 2',
                  'EigenmodeSolver.SetRemoteCalculation False',
                  'EigenmodeSolver.SetCalculateExternalQFactor False',
                  'EigenmodeSolver.SetCalculateThermalLosses False',
                  'MeshAdaption3D.SetType "HighFrequencyTet"',
                  'MeshAdaption3D.MinPasses 2', 'MeshAdaption3D.MaxPasses 2']
        selected = [dict(selected[0], commands=common + selected[0]['commands'])]
    macro = probe.render(directory, selected, reopen=reopen)
    for case in selected:
        line = f'    DumpState "{case["name"]}"'
        queries = '\n'.join(f'    DumpDb "{case["name"]}", "{probe.vb(key)}"' for key in keys())
        macro = macro.replace(line, line + '\n' + queries)
    if solve:
        queries = '\n'.join(f'    DumpDb "post-solver", "{probe.vb(key)}"' for key in keys())
        pre = '\n'.join(f'    DumpDb "post-save", "{probe.vb(key)}"' for key in keys())
        block = f'''    Stage "pre-solver-save"
    Save
{pre}
    Stage "solver-start"
    Dim sr As Long, nc As Long, sf As Integer
    sr = EigenmodeSolver.Start
    Stage "solver-return"
    nc = EigenmodeSolver.GetNumberOfModesCalculated
    sf = FreeFile
    Open "{probe.vb(directory / 'solver.tsv')}" For Output As #sf
    Print #sf, CStr(sr) & Chr(9) & CStr(nc)
    If nc > 0 Then Print #sf, CStr(EigenmodeSolver.GetModeFrequencyInHz(1))
    Close #sf
{queries}
'''
        macro = macro.replace('    DumpExpressions "after"', block + '    DumpExpressions "after"')
    return macro + f'''
Sub DumpDb(label As String, key As String)
    Dim p As Object, value As String, f As Integer
    On Error GoTo Failed
    Set p = GetOwnProject
    value = "OK:" & p.GetDataBaseValue(key)
    GoTo Publish
Failed:
    value = "ERROR:" & CStr(Err.Number) & ":" & Err.Description
Publish:
    On Error GoTo 0
    value = Replace(Replace(Replace(value, Chr(13), " "), Chr(10), " "), Chr(9), " ")
    f = FreeFile
    Open "{probe.vb(directory / 'database.tsv')}" For Append As #f
    Print #f, label & Chr(9) & key & Chr(9) & value
    Close #f
End Sub
'''


def render_staleness(directory):
    macro = render(directory, [dict(name='reopen-with-results')], reopen=True)
    commands = ['EigenmodeSolver.SetMethodType "General (Lossy)", "Tet"',
                'EigenmodeSolver.SetFrequencyTarget False, 600',
                'EigenmodeSolver.SetMeshAdaptationTet True',
                'EigenmodeSolver.SetNumberOfModes 2']
    history = ' & vbCrLf & '.join('"' + probe.vb(c) + '"' for c in commands)
    block = f'''    Stage "mutate-settings"
    history = {history}
    If Not AddToHistory("CSTTools stale database contrast", history) Then Err.Raise vbObjectError + 2703, "calibration", "history rejected"
'''
    for stage, action in [('after-mutation', ''), ('after-save', '    Save\n'),
                          ('after-rebuild', '    If Not Rebuild Then Err.Raise vbObjectError + 2704, "calibration", "rebuild rejected"\n')]:
        block += f'    Stage "{stage}"\n' + action + f'    DumpState "{stage}"\n'
        block += '\n'.join(f'    DumpDb "{stage}", "{probe.vb(k)}"' for k in keys()) + '\n'
    return macro.replace('    DumpExpressions "after"', block + '    DumpExpressions "after"')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True, type=Path)
    parser.add_argument('--case', action='append', choices=[c['name'] for c in cases()])
    parser.add_argument('--reopen', type=Path)
    parser.add_argument('--solve', action='store_true', help='Single coarse native solve for config evidence')
    parser.add_argument('--stale-source', type=Path, help='Closed acceptance input.cst, include its result directory')
    args = parser.parse_args()
    selected = [c for c in cases() if not args.case or c['name'] in args.case]
    if args.solve and (args.reopen or len(selected) != 1):
        parser.error('--solve requires one explicit --case and no --reopen')
    if args.stale_source and (args.solve or args.reopen or args.case):
        parser.error('--stale-source is a separate query/mutation/rebuild probe')
    with probe.exclusive_probe(probe.ROOT):
        if args.stale_source:
            source = args.stale_source.resolve()
            if not source.is_relative_to((probe.ROOT / 'artifacts').resolve()):
                raise ValueError('stale source must be a closed acceptance copy')
            identities = {source: probe.digest(source),
                          source.with_suffix('') / 'Result/Model.db':
                          probe.digest(source.with_suffix('') / 'Result/Model.db')}
            root = probe.ROOT / 'artifacts' / ('solver-readback-stale-' + uuid4().hex[:8])
            root.mkdir()
            shutil.copy2(source, root / 'input.cst')
            shutil.copytree(source.with_suffix(''), root / 'input')
            print('SOLVER_STALE_ROOT=' + str(root), flush=True)
            try:
                probe.run(args.cst_exe, root / 'input.cst', root, render_staleness(root))
            finally:
                checks = [dict(file=str(p), before=h, after=probe.digest(p),
                               unchanged=probe.digest(p) == h) for p, h in identities.items()]
                probe.write_json_atomic(root / 'source-check.json', checks)
                if not all(c['unchanged'] for c in checks):
                    raise RuntimeError('acceptance source changed')
        elif args.reopen:
            root = args.reopen.resolve()
            for case in selected:
                source = root / (case['name'] + '.cst')
                original = probe.digest(source)
                d = root / ('reopen-' + case['name'])
                d.mkdir()
                shutil.copy2(source, d / 'input.cst')
                try:
                    probe.run(args.cst_exe, d / 'input.cst', d, render(d, [case], reopen=True))
                finally:
                    after = probe.digest(source)
                    probe.write_json_atomic(d / 'source-check.json', dict(before=original, after=after,
                                                                         unchanged=original == after))
                    if after != original:
                        raise RuntimeError('snapshot source changed')
                print('REOPEN_COMPLETE=' + str(d), flush=True)
        else:
            root = probe.ROOT / 'artifacts' / ('solver-readback-calibration-' + uuid4().hex[:8])
            root.mkdir()
            source = probe.ROOT / 'model/Pillbox.cst'
            original = probe.digest(source)
            shutil.copy2(source, root / 'input.cst')
            probe.write_json_atomic(root / 'plan.json', dict(source=str(source), sha256=original,
                                   keys=keys(), cases=selected, solver_start_calls=int(args.solve)))
            print('SOLVER_READBACK_ROOT=' + str(root), flush=True)
            try:
                probe.run(args.cst_exe, root / 'input.cst', root,
                          render(root, selected, solve=args.solve),
                          unbounded_stages=('solver-start',) if args.solve else ())
            finally:
                after = probe.digest(source)
                probe.write_json_atomic(root / 'source-check.json', dict(before=original, after=after,
                                                                         unchanged=original == after))
                if after != original:
                    raise RuntimeError('original source changed')
            rows = (root / 'database.tsv').read_text().splitlines()
            print(json.dumps(dict(database_observations=len(rows),
                                  values=[row for row in rows if '\tOK:' in row])), flush=True)


if __name__ == '__main__':
    main()
