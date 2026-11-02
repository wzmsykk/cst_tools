"""Run B2 semantic oracles against implementation, not fixture self-assertions."""
import hashlib
import json
from pathlib import Path

import pytest

from csttool.saved_project_source import read_saved_source
from csttool.settings_projection import project_history, project_saved_settings
from test.saved_project_source_test import container

ROOT = Path(__file__).parents[1]
BOOK = json.loads((ROOT/'test/fixtures/cst_settings_verifier_v06/cases.json').read_text(encoding='utf-8'))
CASES = [c for c in BOOK['cases'] if c['group'] in ('history', 'scope', 'mesh')]
ANCHORS = 'Units.Geometry "mm"\r\nUnits.Frequency "MHz"\r\nChangeSolverType "HF Eigenmode"\r\n'


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_b2_semantic_oracles(case):
    data, expected = case['input'], case['expected']
    scope = data['scope']
    result = project_history(data['histories'].get(scope, ''), data['parameters'].get(scope, []),
                             scope=scope, available_scopes=data['available_scopes'],
                             active_solver=data.get('active_solver', {}).get(scope))
    assert result.status == expected['status']
    assert result.reasons == tuple(expected['reasons'])
    for key, value in expected['fields'].items():
        assert result.fields[key] == value
    if expected['status'] != 'resolved':
        assert not result.fields
    assert result.publish_ready is False and result.live_value is None


def test_b1_bound_projection_and_source_ranges(tmp_path):
    history = ANCHORS + "'@ settings\r\nWith EigenmodeSolver\r\n .SetNumberOfModes _\r\n CInt(RestoreDoubleParameter(\"nmodes\"))\r\nEnd With\r\n"
    path = tmp_path/'input.cst'
    path.write_bytes(container([
        ('Model/3D/Model.mod', history.encode()),
        ('Model/Parameters.json', b'{"parameters":[{"name":"nmodes","expr":"1+1","value":"2"}]}')]))
    before = path.read_bytes()
    source = read_saved_source(path, scope='root')
    report = project_saved_settings(source)
    assert report.status == 'resolved'
    assert report.fields['solver.requested_modes'] == 2
    origin = report.origins['solver.requested_modes']
    assert origin['source_hash'] == hashlib.sha256(before).hexdigest()
    assert origin['member_hash'] == hashlib.sha256(history.encode()).hexdigest()
    assert origin['parameter_hash'] == source.member_hashes['Model/Parameters.json']
    assert (origin['step'], origin['line_start'], origin['line_end']) == (1, 6, 7)
    assert history.encode()[origin['byte_start']:origin['byte_end']].startswith(b' .SetNumberOfModes _')
    with pytest.raises(TypeError):
        report.fields['solver.requested_modes'] = 9
    assert path.read_bytes() == before
    with pytest.raises(TypeError):
        project_saved_settings(source, frequency_unit='MHz')  # removed caller-trust path


@pytest.mark.parametrize('text,reason', [
    ('EigenmodeSolver.SetNumberOfModes 1\nMystery.Settings 2', 'unknown-call-taints-settings'),
    ('EigenmodeSolver.SetNumberOfModes 1\nIf True Then: EigenmodeSolver.SetNumberOfModes 3: End If', 'unsupported-control-flow'),
    ('With Unknown\n.SetNumberOfModes 2\nEnd With', 'unknown-object-alias'),
    ('EigenmodeSolver.SetNumberOfModes "2', 'unterminated-string'),
    ('EigenmodeSolver.SetNumberOfModes _', 'unterminated-continuation'),
    ('EigenmodeSolver.SetNumberOfModes "2^999999"', 'unsupported-expression'),
    ('EigenmodeSolver.SetNumberOfModes "2**2"', 'unsupported-expression'),
    ('EigenmodeSolver.SetNumberOfModes "True"', 'unsupported-expression'),
    ('EigenmodeSolver.SetNumberOfModes "2 + [1][0]"', 'unsupported-expression'),
])
def test_unsupported_code_cannot_retain_old_values(text, reason):
    result = project_history(text, [], scope='root', available_scopes=['root'])
    assert result.reasons == (reason,)
    assert not result.fields and not result.publish_ready


def test_parameter_names_case_insensitive_and_cache_is_not_authority():
    text = 'EigenmodeSolver.SetNumberOfModes "NMODES + 1"'
    rows = [{'name':'nmodes', 'expr':'2', 'value':'2'}]
    assert project_history(text, rows, scope='root', available_scopes=['root']).fields['solver.requested_modes'] == 3
    rows.append({'name':'NMODES', 'expr':'9'})
    assert project_history(text, rows, scope='root', available_scopes=['root']).reasons == ('duplicate-parameter',)


def test_real_sources_remain_bounded_and_not_publishable():
    for name, scope, expected in [('Pillbox.cst', 'root', 'unsupported'),
                                   ('Enlarged.cst', 'SP/FME', 'unsupported')]:
        source = read_saved_source(ROOT/'model'/name, scope=scope)
        result = project_saved_settings(source)
        assert result.status == expected
        assert not result.publish_ready and not result.fields
        assert result.reasons == (('encoding-profile-missing',) if name == 'Enlarged.cst'
                                  else ('unknown-call-taints-settings',))


def test_missing_optional_metadata_does_not_hide_bad_present_json(tmp_path):
    items = [('Model/3D/Model.mod', (ANCHORS+'EigenmodeSolver.SetNumberOfModes 1').encode()),
             ('Model/Parameters.json', b'{"parameters":[]}')]
    path = tmp_path/'source.cst'
    path.write_bytes(container(items))
    report = project_saved_settings(read_saved_source(path, scope='root'))
    assert report.status == 'resolved'
    assert report.reasons == ('optional-metadata-missing',)  # D04 semantic behavior
    path.write_bytes(container(items+[('Model/simulationproperties.json', b'{')]))
    result = project_saved_settings(read_saved_source(path, scope='root'))
    assert result.status == 'malformed' and not result.fields


@pytest.mark.parametrize('reset,tail,remaining', [
    ('MeshSettings.Reset', 'MeshSettings.SetMeshType "Tet"\nMeshSettings.Set "StepsPerWaveNear", 8', 'unsupported'),
    ('Mesh.Reset', 'Mesh.StepsPerWavelengthTet 8', 'unsupported'),
    ('EigenmodeSolver.Reset', 'EigenmodeSolver.SetNumberOfModes 2', 'ambiguous'),
])
def test_reset_does_not_clear_other_object_channels(reset, tail, remaining):
    text = ('Mesh.StepsPerWavelengthTet 4\nMeshSettings.SetMeshType "Tet"\n'
            'MeshSettings.Set "StepsPerWaveNear", 4\n'+reset+'\n'+tail)
    result = project_history(text, [], scope='root', available_scopes=['root'])
    assert result.status == remaining
    assert not result.fields


def test_resolved_partial_report_never_implies_reset_defaults_or_ready():
    result = project_history('EigenmodeSolver.Reset\nEigenmodeSolver.SetNumberOfModes 2', [],
                             scope='root', available_scopes=['root'])
    assert result.status == 'resolved'
    assert 'solver.requested_modes' not in result.missing_fields
    assert 'solver.frequency_target.enabled' in result.missing_fields
    assert not result.publish_ready


def test_quotes_colons_comments_and_continuation_are_lexical():
    # An unknown call containing fake statements in a string must not be executed.
    result = project_history('Mystery.Value "x: EigenmodeSolver.SetNumberOfModes 5 \' x"', [],
                             scope='root', available_scopes=['root'])
    assert result.status == 'unsupported' and not result.fields
    result = project_history('Rem ignored: Call Unknown\nEigenmodeSolver.SetNumberOfModes 1: '
                             'EigenmodeSolver.SetNumberOfModes 2 \' ignored "', [],
                             scope='root', available_scopes=['root'])
    assert result.fields['solver.requested_modes'] == 2


def test_expression_and_history_budgets():
    result = project_history('EigenmodeSolver.SetNumberOfModes "'+('1+'*2500)+'1"', [],
                             scope='root', available_scopes=['root'])
    assert result.reasons == ('expression-budget-exceeded',)
    result = project_history(' '* (2*1024*1024+1), [], scope='root', available_scopes=['root'])
    assert result.reasons == ('history-budget-exceeded',)
