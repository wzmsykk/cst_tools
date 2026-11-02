"""A1 complete synthetic history, not a CST-generated or executed acceptance model."""
import hashlib
import json
from pathlib import Path

import pytest

from csttool.saved_project_source import read_saved_source
from csttool.settings_projection import project_history, project_saved_settings, COMMAND_ARITIES
from test.saved_project_source_test import container

FIXTURE = Path(__file__).parent/'fixtures/a1-pillbox-history.vb'
HISTORY = FIXTURE.read_text(encoding='utf-8')
PARAMETERS = [dict(name=name, expr=value, value=value) for name, value in
              [('R','100'), ('L','120'), ('fmin','500'), ('fmax','1000'), ('nmodes','1'), ('cell','4')]]


def project(text=HISTORY, rows=None):
    return project_history(text, PARAMETERS if rows is None else rows, scope='root',
                           available_scopes=['root'], require_identity=True)


@pytest.mark.parametrize('axis', ['x', 'y', 'z'])
def test_complete_parameterized_history_all_axes(axis):
    text = HISTORY.replace('.Axis "z"', '.Axis "'+axis+'"').replace('.Zrange', '.'+axis.upper()+'range')
    result = project(text)
    assert result.status == 'resolved', result.reasons
    assert not result.missing_fields and not result.publish_ready and result.live_value is None
    expected = {'units.length':'mm', 'units.frequency':'MHz', 'solver.family':'HF Eigenmode',
                'geometry.cylinder.axis':axis, 'geometry.cylinder.outerradius':100,
                'geometry.cylinder.'+axis+'range':(-60,60), 'geometry.cylinder.material':'Vacuum',
                'solver.frequency_range.min_mhz':500, 'solver.frequency_range.max_mhz':1000,
                'solver.selected_method':'Default', 'solver.selected_mesh':'Tet', 'mesh.type':'Tetrahedral',
                'solver.requested_modes':1, 'solver.frequency_target.value_mhz':500,
                'solver.mesh_adaptation.tet':False, 'solver.losses_postprocess_only':True,
                'mesh.tet.near':4, 'mesh.tet.far':4, 'mesh.tet.version':1,
                'mesh.tet.policy':'cellsperwavelength'}
    for key, value in expected.items():
        assert result.fields[key] == value
        assert key in result.origins
    origin = result.origins['geometry.cylinder.outerradius']
    for part in ('property','create'):
        assert text.encode()[origin[part]['byte_start']:origin[part]['byte_end']]
    assert origin['property']['line_start'] < origin['create']['line_start']
    assert result.fields['expressions.geometry.cylinder.outerradius'] == 'RestoreDoubleParameter("R")'


def test_b1_full_history_scope_binding_and_repeated_read_no_mutation(tmp_path):
    path = tmp_path/'a1.cst'
    path.write_bytes(container([
        ('Model/3D/Model.mod', HISTORY.replace('"MHz"','"GHz"').encode()),
        ('Model/Parameters.json', json.dumps({'parameters':PARAMETERS}).encode()),
        ('SP/FME/Model/3D/Model.mod', HISTORY.encode()),
        ('SP/FME/Model/Parameters.json', json.dumps({'parameters':PARAMETERS}).encode())]))
    raw = path.read_bytes()
    source = read_saved_source(path, scope='SP/FME')
    for _ in range(2):
        result = project_saved_settings(source)
        assert result.status == 'resolved', result.reasons
        assert result.fields['units.frequency'] == 'MHz'
        assert result.origins['solver.family']['scope'] == 'SP/FME'
        assert result.source_hash == hashlib.sha256(raw).hexdigest()
    assert path.read_bytes() == raw
    assert project_saved_settings(read_saved_source(path, scope='root')).reasons == ('a1-unit-unsupported',)


@pytest.mark.parametrize('old,new,reason', [
    ('    .Frequency "MHz"', "'# frequency = MHz", 'history-identity-before-settings-required'),
    ('    .Geometry "mm"', "'# length = mm", 'length-unit-before-geometry-required'),
    ('ChangeSolverType "HF Eigenmode"', "' Last Solver Type=HF Eigenmode", 'history-identity-before-settings-required'),
    ('ChangeSolverType "HF Eigenmode"', 'ChangeSolverType "HF Frequency Domain"', 'a1-solver-family-unsupported'),
    ('    .Frequency "MHz"', '    .Frequency "GHz"', 'a1-unit-unsupported'),
    ('    .Geometry "mm"', '    .Geometry "cm"', 'a1-unit-unsupported'),
    ('    .Frequency "MHz"', '    .Frequency MHz', 'literal-string-required'),
    ('ChangeSolverType "HF Eigenmode"', 'ChangeSolverType solver_name', 'literal-string-required'),
    ('    .Type "pec"', '    .Type "normal"', 'a1-background-unsupported'),
    ('    .Zmax "electric"', '    .Zmax "open"', 'a1-boundary-unsupported'),
    ('    .Xsymmetry "none"', '    .Xsymmetry "magnetic"', 'a1-boundary-unsupported'),
    ('    .XminSpace 0', '    .XminSpace 10', 'a1-padding-unsupported'),
    ('WCS.ActivateWCS "global"', 'WCS.ActivateWCS "local"', 'a1-wcs-unsupported'),
    ('WCS.ActivateWCS "global"', '', 'cylinder-global-wcs-required'),
    ('Component.New "cavity"', '', 'cylinder-component-missing'),
    ('    .Reset\n', '', 'cylinder-reset-required'),
    ('    .Create\n', '', 'cylinder-create-missing'),
    ('    .Material "Vacuum"', '    .Material "Copper"', 'a1-cylinder-profile-unsupported'),
    ('    .InnerRadius 0', '    .InnerRadius 1', 'a1-cylinder-profile-unsupported'),
    ('    .Segments 0', '    .Segments 8', 'a1-cylinder-profile-unsupported'),
    ('    .Ycenter 0', '    .Ycenter 1', 'a1-cylinder-center-unsupported'),
    ('    .Xcenter 0\n', '', 'cylinder-explicit-settings-required'),
    ('    .OuterRadius RestoreDoubleParameter("R")', '    .OuterRadius -1', 'invalid-cylinder-dimensions'),
    ('    .Zrange -RestoreDoubleParameter("L")/2, RestoreDoubleParameter("L")/2', '    .Zrange 1, 0', 'invalid-cylinder-dimensions'),
    ('    .Zrange -RestoreDoubleParameter("L")/2, RestoreDoubleParameter("L")/2', '    .Zrange 0, 1\n    .Xrange 0, 1', 'a1-unused-cylinder-range'),
    ('Solver.FrequencyRange "fmin", "fmax"', 'Solver.FrequencyRange 1000, 500', 'invalid-frequency-range'),
    ('    .SetFrequencyTarget True, "fmin"', '    .SetFrequencyTarget True, "fmax+1"', 'invalid-frequency-target'),
    ('    .Set "Version", 1', '    .Set "Version", 2', 'uncalibrated-density-version'),
    ('    .Set "CellsPerWavelengthPolicy", "cellsperwavelength"', '    .Set "CellsPerWavelengthPolicy", "auto"', 'unknown-density-policy'),
])
def test_actual_command_differences_are_not_hidden(old, new, reason):
    assert old in HISTORY
    result = project(HISTORY.replace(old,new))
    assert result.status != 'resolved'
    assert result.reasons == (reason,)
    assert not result.fields and not result.publish_ready
    assert result.failure_origin


@pytest.mark.parametrize('command', [
    'EigenmodeSolver.Start', 'Solver.Start', 'RunSolver', 'Project.Save', 'Quit',
    'StoreParameter "fmin", 0', 'Application.OpenFile "other.cst"', 'Mesh.Reset',
    'MeshSettings.Reset', 'Background.Reset', 'Boundary.Reset', 'Cylinder.Delete',
    'Cylinder.Create "extra"', 'Units.Frequency "MHz", "GHz"', 'Units.FrequencYx "MHz"',
    'Call SetSomething', 'Evaluate "2"', 'Units.Frequency "MHz": Mystery.Settings 0',
    'Project.ChangeSolverType "HF Eigenmode"', 'With Project\nEnd With',
    'MeshAdaption3D.MinPasses RunMacro("evil")',
    'MeshAdaption3D.SetType RunMacro("evil")',
])
def test_allowlist_does_not_authorize_execution_or_unknown_object_methods(command):
    result = project(HISTORY+'\n'+command)
    assert result.status in ('unsupported','malformed')
    assert not result.fields and result.failure_origin
    assert result.failure_origin['line_start'] >= len(HISTORY.splitlines())


def test_eigenmode_reset_preserves_project_identity_frequency_range_and_mesh_channels():
    text = HISTORY+'\nEigenmodeSolver.Reset\nEigenmodeSolver.SetNumberOfModes 2'
    result = project(text)
    assert result.status == 'resolved'
    assert result.fields['solver.family'] == 'HF Eigenmode'
    assert result.fields['solver.frequency_range.min_mhz'] == 500
    assert result.fields['mesh.tet.near'] == 4
    assert result.fields['solver.requested_modes'] == 2
    assert 'solver.selected_method' not in result.fields
    assert 'solver.selected_method' in result.missing_fields


def test_metadata_and_other_scope_cannot_supply_missing_history_identity(tmp_path):
    path = tmp_path/'fake-identity.cst'
    missing = HISTORY.replace('ChangeSolverType "HF Eigenmode"','')
    path.write_bytes(container([
        ('Model/3D/Model.mod', missing.encode()),
        ('Model/Parameters.json', json.dumps({'parameters':PARAMETERS}).encode()),
        ('Model/Model.prj', b'[Model]\nLast Solver Type=HF Eigenmode'),
        ('Model/simulationproperties.json', b'{"active_solver":"HF Eigenmode","frequency_unit":"MHz"}'),
        ('SP/FME/Model/3D/Model.mod', HISTORY.encode())]))
    report = project_saved_settings(read_saved_source(path,scope='root'))
    assert report.reasons == ('history-identity-before-settings-required',)
    assert not report.fields


def test_order_and_side_effect_boundaries_are_conservative():
    for suffix, reason in [('\nChangeSolverType "HF Eigenmode"', 'solver-selection-after-settings'),
                           ('\nSolver.FrequencyRange 500, 1000', 'frequency-range-after-mesh'),
                           ('\nUnits.Frequency "GHz"\nUnits.Frequency "MHz"','a1-unit-unsupported'),
                           ('\nComponent.New "second"','a1-single-component-only'),
                           ('\nCylinder.Create','a1-single-cylinder-only')]:
        assert project(HISTORY+suffix).reasons == (reason,)


def test_parameter_change_is_recomputed_without_rewriting_expression():
    rows = [dict(row) for row in PARAMETERS]
    rows[0].update(expr='200',value='200')
    result = project(rows=rows)
    assert result.fields['geometry.cylinder.outerradius'] == 200
    assert result.fields['expressions.geometry.cylinder.outerradius'] == 'RestoreDoubleParameter("R")'
    assert 'StoreParameter' not in HISTORY


def test_python_only_number_syntax_cannot_become_vba_evidence():
    result = project(HISTORY.replace('    .InnerRadius 0','    .InnerRadius 0_0'))
    assert result.reasons == ('unsupported-expression',)
    assert not result.fields


def test_bad_saved_encoding_retains_member_identity_without_guessing_decoder(tmp_path):
    path = tmp_path/'legacy.cst'
    path.write_bytes(container([('Model/3D/Model.mod', b'\xff'),
                               ('Model/Parameters.json', b'{"parameters":[]}')]))
    source = read_saved_source(path,scope='root')
    report = project_saved_settings(source)
    assert report.reasons == ('encoding-profile-missing',)
    assert report.failure_origin['member'] == 'Model/3D/Model.mod'
    assert report.failure_origin['member_hash'] == hashlib.sha256(b'\xff').hexdigest()
    assert project_saved_settings(source,encoding='utf-8').status == 'malformed'


def test_exact_allowlist_contains_no_guessed_resets_or_runtime_calls():
    assert ('mesh','reset') not in COMMAND_ARITIES
    assert ('meshsettings','reset') not in COMMAND_ARITIES
    assert ('eigenmodesolver','reset') in COMMAND_ARITIES
    assert ('cylinder','reset') in COMMAND_ARITIES
    assert all(command not in ('start','save','quit','openfile') for _,command in COMMAND_ARITIES)


def test_synthetic_fixture_provenance_is_not_real_cst_acceptance():
    record = json.loads((Path(__file__).parents[1]/'knowledge-base/cst-a1-history-sources-20261102.json').read_text(encoding='utf-8'))
    assert record['synthetic_fixture']['sha256'] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert record['real_cst_started'] is False
    assert len(record['files']) == 11
    assert all(len(item['sha256']) == 64 for item in record['files'])


@pytest.mark.parametrize('text', [
    'Units.Geometry "mm"\nUnits.Frequency "MHz"',
    "' ChangeSolverType \"HF Eigenmode\"\n' Units.Frequency \"MHz\"",
    'EigenmodeSolver.SetNumberOfModes 1',
])
def test_saved_definition_must_have_complete_same_history_identity(text):
    report = project(text)
    assert report.status == 'unresolved'
    assert not report.fields and set(report.missing_fields) >= {'units.frequency','solver.family'}
