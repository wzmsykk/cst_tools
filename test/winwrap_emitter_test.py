"""Syntax construction and semantic preservation; no native compiler claim."""
import pytest

from csttool.winwrap_emitter import (String, Number, Function, Variable, Element,
    HistoryCall, With, Symbols, SubCall, Unary, resize_arrays, GeneratedCodeError, arithmetic, assign_string,
    render_history, validate_parameter_names)
from csttool.settings_projection import COMMAND_ARITIES, history_call_contract
from csttool.definition_editing import changed_spec, render_history as definition_history, render_edit_macro
from test.definition_editing_test import changes, configuration


def definition(axis='z'):
    rows=changes()
    rows[2]['axis']=axis
    spec=changed_spec({},dict(operation='apply_model_changes',changes=rows))
    config=configuration()
    config['postprocess'][1]['settings']['integration_line']['axis']=axis
    return changed_spec({'spec':spec},dict(operation='configure_simulation',**config))


@pytest.mark.parametrize('axis','xyz')
def test_typed_geometry_retains_nested_parameter_expressions_and_exact_projection(axis,tmp_path):
    spec=definition(axis)
    spec['parameters']['L']['expression']='2 * R'
    spec['cylinder']['axial_range']=['-(L + R)/2','(L+R)/2']
    history,projection=definition_history(spec)
    assert projection.fields['geometry.cylinder.'+axis+'range']==(-150,150)
    assert 'RestoreDoubleParameter("L")' in history
    assert 'RestoreDoubleParameter("R")' in history
    assert '.'+axis.upper()+'range 0+' in history
    assert '.Start' not in history
    macro=render_edit_macro(tmp_path,spec,'a'*32)
    assert macro.count('Sub Main\n')==1 and macro.count('Option Explicit\n')==1
    macro.encode('ascii')
    assert max(map(len,macro.splitlines()))<=800


@pytest.mark.parametrize('name',['f','F','history','NaMeS','ReportStage','CSTToolsBindNewProject',
                                 'Cylinder','restoreDoubleParameter','String','tick','value'])
def test_host_parameters_cannot_shadow_template_symbols_before_draft_publication(name):
    with pytest.raises(GeneratedCodeError,match='identifier conflict'):
        validate_parameter_names([name])
    rows=changes()[:1]
    rows[0]['values'][name]=dict(expression='2',quantity='length',description='')
    with pytest.raises(ValueError,match='GENERATED_CODE_INVALID'):
        changed_spec({},dict(operation='apply_model_changes',changes=rows))


def test_contexts_do_not_confuse_bare_sub_arguments_with_return_value_expressions():
    params={'L':{'expression':'4'}}
    expr=arithmetic('-L/2',params)
    code=render_history([With('Cylinder',(HistoryCall('Cylinder','Zrange',(expr,expr)),))])
    assert '.Zrange 0+' in code and '.Zrange (' not in code
    assert Function('RestoreDoubleParameter',(String('L'),)).render()=='RestoreDoubleParameter("L")'
    assert SubCall('SetParameterDescription',(String('L'),Variable('message'))).render()=='SetParameterDescription "L", message'
    assert resize_arrays((Variable('names'),Variable('expressions')),2)=='ReDim names(0 To 1), expressions(0 To 1)'
    with pytest.raises(GeneratedCodeError): resize_arrays((Variable('names'),),0)
    with pytest.raises(GeneratedCodeError,match='raw source'):
        HistoryCall('Cylinder','Zrange',('(-L/2)','L/2')).render()
    with pytest.raises(GeneratedCodeError,match='argument-safe'):
        HistoryCall('Cylinder','Zrange',(Unary('-',Number('2')),Number('2'))).render()


def test_registry_cards_derive_from_existing_commands_and_never_grant_live_or_transaction_semantics():
    assert len(COMMAND_ARITIES)==51
    for (obj,method),arity in COMMAND_ARITIES.items():
        card=history_call_contract(obj,method)
        assert card['arity']==arity and card['scope']=='loaded-3D'
        assert card['call_kind']=='statement' and card['documentation']
        assert 'not transactional' in card['side_effect']
    with pytest.raises(GeneratedCodeError): HistoryCall('Solver','Start').render()
    with pytest.raises(GeneratedCodeError): HistoryCall('Cylinder','Zrange',(Number('1'),)).render()
    with pytest.raises(GeneratedCodeError): With('Cylinder',(HistoryCall('Mesh','MeshType',(String('Tet'),)),)).render()


def test_string_data_is_unicode_safe_chunked_and_not_executable_source():
    data='text "quoted" 中文😀'*80+'\nsecond line'
    lines=assign_string(Element('names',0),data)
    assert 'vbCrLf' in '\n'.join(lines) and 'ChrW(' in '\n'.join(lines)
    assert max(map(len,lines))<=800
    '\n'.join(lines).encode('ascii')
    with pytest.raises(GeneratedCodeError): String('a\nEnd Sub').render()
    with pytest.raises(GeneratedCodeError): Variable('x: Kill').render()
    symbols=Symbols(['Radius'])
    with pytest.raises(GeneratedCodeError): symbols.declare('radius','Double')


def test_long_generated_history_rejected_before_native_instead_of_silently_truncated():
    spec=definition()
    spec['cylinder']['outer_radius']=' + '.join(['R']*40)
    with pytest.raises(GeneratedCodeError,match='physical-line-budget'):
        definition_history(spec)


def test_save_generation_failure_does_not_leave_an_execution_intent(tmp_path):
    from test.project_creation_test import service, payload
    from test.definition_editing_test import request
    from csttool.definition_editing import edit_document
    app,calls=service(tmp_path)
    empty=app.create_project(payload(),operation_id='create')
    rows=changes(); rows[2]['outer_radius']=' + '.join(['R']*40)
    model=edit_document(app,request(empty,'apply_model_changes',changes=rows),operation_id='model')
    config=edit_document(app,request(model,'configure_simulation',**configuration()),operation_id='config')
    with pytest.raises(GeneratedCodeError,match='physical-line-budget'):
        edit_document(app,request(config,'save_project'),operation_id='invalid-save')
    assert not (tmp_path/'control/runs/invalid-save/definition-intent.json').exists()
    assert calls==[1]
