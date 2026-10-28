"""V05: independent Pillbox copies, native mesh generation, no eigensolve."""
import argparse
import json
from pathlib import Path
import shutil
from uuid import uuid4

import calibrate_cst_settings as probe
from tet_options_evidence import decode_options


def modern(near, far):
    return ['MeshSettings.SetMeshType "Tet"',
            f'MeshSettings.Set "StepsPerWaveNear", "{near}"',
            f'MeshSettings.Set "StepsPerWaveFar", "{far}"',
            'MeshSettings.Set "CellsPerWavelengthPolicy", "cellsperwavelength"']


def cases():
    return {
        'legacy4': ['Mesh.StepsPerWavelengthTet 4'],
        'legacy8': ['Mesh.StepsPerWavelengthTet 8'],
        'modern4-4': modern(4, 4),
        'modern8-8': modern(8, 8),
        'modern8-4': modern(8, 4),
        'modern4-8': modern(4, 8),
        'new4-then-legacy8': modern(4, 4) + ['Mesh.StepsPerWavelengthTet 8'],
        'legacy8-then-new4': ['Mesh.StepsPerWavelengthTet 8'] + modern(4, 4),
        # Exploratory version selector; acceptance does not assert its semantics.
        'v0-legacy4': ['MeshSettings.SetMeshType "Tet"',
                       'MeshSettings.Set "Version", 0', 'Mesh.StepsPerWavelengthTet 4'],
        'v0-legacy8': ['MeshSettings.SetMeshType "Tet"',
                       'MeshSettings.Set "Version", 0', 'Mesh.StepsPerWavelengthTet 8'],
    }


def render(directory, name, commands):
    # Hold geometry refinement coarse and identical to expose wavelength effects.
    common = ['MeshSettings.SetMeshType "Tet"',
              'MeshSettings.Set "StepsPerBoxNear", "2"',
              'MeshSettings.Set "StepsPerBoxFar", "1"']
    case = dict(name=name, mesh='Tet', method='Default', count=1,
                commands=common + commands)
    macro = probe.render(directory, [case])
    block = f'''    Stage "mesh-generate"
    Mesh.Update
    Mesh.CalculateMatrices
    Stage "mesh-measure"
    Dim mf As Integer
    mf = FreeFile
    Open "{probe.vb(directory / 'mesh.tsv')}" For Output As #mf
    Print #mf, CStr(Mesh.GetNumberOfMeshCells) & Chr(9) & CStr(Mesh.GetMinimumEdgeLength) & Chr(9) & CStr(Mesh.GetMaximumEdgeLength) & Chr(9) & ReadMeshCandidate("Version")
    Close #mf
'''
    return macro.replace('    DumpExpressions "after"', block + '    DumpExpressions "after"')


def collect_mesh_evidence(directory, project, report):
    values = (directory / 'mesh.tsv').read_text().strip().split('\t')
    report['mesh'] = dict(cells=int(values[0]), min_edge=float(values[1]),
                          max_edge=float(values[2]))
    if len(values) > 3:
        report['settings_version'] = values[3]
    native = project.with_suffix('') / 'Result'
    options = native / 'Mesh_Input.Options.tet'
    shutil.copy2(native / 'output.txt', directory / 'native-output.txt')
    output = (directory / 'native-output.txt').read_text(errors='replace')
    report['mesh_success'] = (report['mesh']['cells'] > 0 and options.is_file()
                              and 'Meshing successful' in output)
    probe.write_json_atomic(directory / 'report.json', report)
    if not report['mesh_success']:
        raise RuntimeError('native mesh generation failed; see ' + str(directory / 'native-output.txt'))
    decoded = decode_options(options.read_bytes())
    shutil.copy2(options, directory / 'mesher-options.cbor')
    probe.write_json_atomic(directory / 'mesher-options.json', decoded)
    report['mesher_input'] = {k: v for k, v in decoded['Attributes'].items()
        if k in ('d/step_near_model', 'd/step_far_from_model',
                 'd/Global/StepsPerBoxNear', 'd/Global/StepsPerBoxFar')}
    report['mesh_file_sha256'] = probe.digest(native / '3d.slim')
    probe.write_json_atomic(directory / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', type=Path, required=True)
    parser.add_argument('--case', action='append', choices=list(cases()))
    args = parser.parse_args()
    selected = {name: commands for name, commands in cases().items()
                if (name in args.case if args.case else not name.startswith('v0-'))}
    source = probe.ROOT / 'model/Pillbox.cst'
    original = probe.digest(source)
    with probe.exclusive_probe(probe.ROOT):
        root = probe.ROOT / 'artifacts' / ('tet-mesh-calibration-' + uuid4().hex[:8])
        root.mkdir()
        print('MESH_CALIBRATION_ROOT=' + str(root), flush=True)
        probe.write_json_atomic(root / 'plan.json', dict(source=str(source),
            source_sha256=original, cases=selected, solver_start_calls=0,
            geometry_refinement=dict(near=2, far=1)))
        try:
            for name, commands in selected.items():
                directory = root / name
                directory.mkdir()
                project = directory / 'input.cst'
                shutil.copy2(source, project)
                report = probe.run(args.cst_exe, project, directory,
                    render(directory, name, commands), unbounded_stages=('mesh-generate',))
                report = collect_mesh_evidence(directory, project, report)
                print(json.dumps(dict(case=name, mesh=report['mesh'],
                    rows=report['rows'], expressions_preserved=report['expressions_preserved'])), flush=True)
        finally:
            after = probe.digest(source)
            probe.write_json_atomic(root / 'source-check.json',
                dict(before=original, after=after, unchanged=original == after))
            if after != original:
                raise RuntimeError('original project changed')


if __name__ == '__main__':
    main()
