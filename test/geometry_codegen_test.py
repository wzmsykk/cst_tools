"""GEO-2 offline source emission/projection/checking/mapping, no CST."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from csttool.definition_editing import changed_spec, render_history as render_a1, render_edit_macro
from csttool.geometry_contract import native_solid_name
from csttool.geometry_codegen import render_geometry_history, validate_geometry_history
from csttool.settings_projection import (COMMAND_ARITIES, GEOMETRY_PROFILE, project_geometry_history,
    geometry_expression_identity, history_call_contract)
from csttool.winwrap_emitter import (GeneratedCodeError, HistoryCall, String, Variable,
    assign_string, validate_parameter_names)
from csttool.winwrap_checks import (check_history, geometry_definition_map, map_native_error,
    check_calibration, generator_fingerprint)
from test.geometry_contract_test import changes, draft, geo_request
from test.definition_editing_test import configuration, changes as a1_changes, request


def spec(rows=None):
    return changed_spec({},dict(operation='apply_model_changes',geometry_profile='geometry-v1',
        changes=changes() if rows is None else rows))


def project(blocks, model, **kwargs):
    return project_geometry_history(blocks,[dict(name=k,expr=v['expression']) for k,v in model['parameters'].items()],
        scope=kwargs.get('scope','root'),available_scopes=kwargs.get('available_scopes',('root',)))


def mutation(blocks,index,old,new):
    changed=deepcopy(list(blocks));assert old in changed[index]['history']
    changed[index]['history']=changed[index]['history'].replace(old,new,1)
    return changed


@pytest.mark.parametrize('axis',list('xyz'))
def test_all_primitives_nonzero_xyz_hollow_and_expression_provenance(axis):
    rows=changes();rows[3]['axis']=axis
    rows.insert(4,dict(op='create_sphere',object_id='ball',component_id='vacuum',material_id='PEC',
        center_mm=['R','-H/2','3'],radius_mm='R/2'))
    model=spec(rows);before=deepcopy(model);blocks,report=render_geometry_history(model)
    assert model==before and report.status=='resolved' and not report.missing_fields
    assert report.parser_profile==GEOMETRY_PROFILE and not report.publish_ready and report.live_value is None
    assert len(blocks)==1+len(model['geometry']['features'])
    assert len({b['caption'] for b in blocks})==len(blocks)
    cylinder=report.fields['geometry.features'][1]['resolved']
    assert cylinder['axis']==axis and cylinder['inner_radius_mm']=='2.5'
    assert report.fields['geometry.features'][2]['resolved']==dict(radius_mm='2.5',center_mm=['5','-10','3'])
    assert '.Center 0+' in blocks[3]['history'] and '.CenterRadius' in blocks[3]['history']
    assert all('StoreParameter' not in b['history'] and 'Group.' not in b['history'] and 'Pick.' not in b['history'] for b in blocks)
    assert 'geometry.features[1].outer_radius_mm' in report.exact_values
    assert report.origins['geometry.features[1].outer_radius_mm']['block_index']==2
    assert {'geometry.objects','geometry.features','components'}<=report.origins.keys()
    assert blocks[2]['history'].count('center ')==2
    mapping=geometry_definition_map(model,blocks)
    assert next(r for r in mapping['history'] if r['block_index']==3 and r['method']=='Axis')['input_field']=='geometry.features[2]'


@pytest.mark.parametrize('operation',['union','difference','intersection'])
def test_boolean_consumption_and_deletion_are_projected_from_actual_commands(operation):
    rows=changes();rows[4]['operation']=operation
    rows += [dict(op='delete_object',object_id='body'),dict(op='delete_selection_set',selection_id='cavity')]
    model=spec(rows);blocks,report=render_geometry_history(model)
    assert report.fields['geometry.objects'][native_solid_name('vacuum','body')]['state']=='deleted'
    assert report.fields['geometry.objects'][native_solid_name('vacuum','tool')]['state']=='consumed'
    assert report.fields['geometry.features'][2]['operation']==operation
    assert report.fields['geometry.features'][2]['resolved']['result_geometry']=='unverified'
    assert not any('volume' in str(key).lower() for key in report.fields)


def test_empty_geometry_and_edited_feature_ids_have_deterministic_code():
    model=spec([dict(op='ensure_component',component_id='vacuum')])
    blocks,report=render_geometry_history(model)
    assert len(blocks)==1 and report.fields['geometry.features']==() and report.fields['geometry.objects']=={}
    model=spec();feature=model['geometry']['features'][-1]
    replacement={k:v for k,v in feature.items() if k!='feature_id'};replacement['translation_mm']=['H','0','R']
    updated=changed_spec({'spec':model},dict(operation='apply_model_changes',geometry_profile='geometry-v1',
        changes=[dict(op='update_feature',feature_id=feature['feature_id'],replacement=replacement)]))
    before=render_geometry_history(model)[0];after=render_geometry_history(updated)[0]
    assert before[-1]['caption']==after[-1]['caption'] and before[-1]['history']!=after[-1]['history']
    assert render_geometry_history(updated)[0]==after


def test_a1_default_profile_is_not_widened(tmp_path):
    assert ('brick','create') not in COMMAND_ARITIES and ('solid','subtract') not in COMMAND_ARITIES
    with pytest.raises(GeneratedCodeError):HistoryCall('Brick','Create').render()
    assert HistoryCall('Brick','Create').render(profile=GEOMETRY_PROFILE)=='Brick.Create'
    with pytest.raises(GeneratedCodeError):check_history(render_geometry_history(spec())[0][1]['history'])
    a1=changed_spec({},dict(operation='apply_model_changes',changes=a1_changes()))
    a1=changed_spec({'spec':a1},dict(operation='configure_simulation',**configuration()))
    history,projection=render_a1(a1)
    assert projection.status=='resolved' and check_history(history)
    assert 'MacroCheckThis' in render_edit_macro(tmp_path,a1,'nonce')
    validate_parameter_names(['Brick'])  # This assertion is about A1 policy, not native acceptance.
    with pytest.raises(GeneratedCodeError):validate_parameter_names(['Brick'],profile=GEOMETRY_PROFILE)
    assert 'pending' in history_call_contract('Sphere','Center',profile=GEOMETRY_PROFILE)['version']


def test_numeric_equivalence_cannot_hide_lost_parameter_references():
    model=spec();blocks,_=render_geometry_history(model)
    changed=mutation(blocks,2,'.OuterRadius 0+RestoreDoubleParameter("R")','.OuterRadius 0+5')
    assert project(changed,model).status=='resolved'
    with pytest.raises(GeneratedCodeError,match='symbolic') as caught:validate_geometry_history(model,changed)
    assert caught.value.input_field=='geometry.features[1].outer_radius_mm'
    assert caught.value.origin['block_index']==2
    assert geometry_expression_identity('0+(-RestoreDoubleParameter("R")/2)',[dict(name='R',expr='5')])==geometry_expression_identity('-R/2',[dict(name='R',expr='5')])


@pytest.mark.parametrize('old,new',[
    ('.Xrange 0+(-RestoreDoubleParameter("H")), 0+RestoreDoubleParameter("H")','.Xrange 0+1, 0+2'),
    ('.Material "Vacuum"','.Material "PEC"'),
    ('.Reset',''),('.Create',''),('.Reset','.Reset\n .Reset'),
    ('.Material "Vacuum"','.Material "Vacuum"\n .Material "Vacuum"'),
    ('End With',''),('With Brick','With Shell'),
])
def test_mutated_primitive_program_is_never_accepted(old,new):
    model=spec();blocks,_=render_geometry_history(model)
    changed=mutation(blocks,1,old,new)
    with pytest.raises(GeneratedCodeError):validate_geometry_history(model,changed)


@pytest.mark.parametrize('command',['Execute "bad"','Evaluate "1"','Application.Quit','Group.Reset',
    'Pick.ClearAllPicks','Solver.Start','Solid.Insert "a", "b"','WCS.ActivateWCS "local"'])
def test_unknown_side_effects_and_wrong_coordinate_system_are_rejected(command):
    model=spec();blocks,_=render_geometry_history(model)
    changed=deepcopy(list(blocks));changed[1]['history']+='\n'+command
    with pytest.raises(GeneratedCodeError):validate_geometry_history(model,changed)
    report=project(changed,model)
    assert report.status!='resolved' and not report.fields and not report.publish_ready


@pytest.mark.parametrize('old,new',[
    ('.MultipleObjects False','.MultipleObjects True'),('.GroupObjects False','.GroupObjects True'),
    ('.UsePickedPoints False','.UsePickedPoints True'),('.Touch False','.Touch True'),
    ('.Repetitions 1','.Repetitions 2'),('"Shape", "Translate"','"Shape", "Rotate"'),
])
def test_transform_flags_have_semantic_checks_beyond_command_arity(old,new):
    model=spec();blocks,_=render_geometry_history(model);changed=mutation(blocks,4,old,new)
    check_history(changed[4]['history'],profile=GEOMETRY_PROFILE)
    report=project(changed,model)
    assert report.status!='resolved' and not report.fields
    assert report.failure_origin['block_index']==4
    with pytest.raises(GeneratedCodeError):validate_geometry_history(model,changed)


def test_original_parenthesized_bare_call_is_rejected_independently():
    model=spec();blocks,_=render_geometry_history(model)
    changed=mutation(blocks,2,'.Zrange 0+(','.Zrange (')
    # Arithmetic projection is not a compiler. The separate syntax-shape layer is required.
    with pytest.raises(GeneratedCodeError,match='unsafe bare first argument'):
        check_history(changed[2]['history'],profile=GEOMETRY_PROFILE)
    with pytest.raises(GeneratedCodeError):validate_geometry_history(model,changed)


def test_order_caption_and_consumed_reference_fail_closed():
    model=spec();blocks,_=render_geometry_history(model)
    duplicate=deepcopy(list(blocks));duplicate[2]['caption']=duplicate[1]['caption']
    report=project(duplicate,model)
    assert report.status=='ambiguous' and not report.fields
    swapped=deepcopy(list(blocks));swapped[2]['history'],swapped[3]['history']=swapped[3]['history'],swapped[2]['history']
    assert project(swapped,model).status!='resolved'
    body=native_solid_name('vacuum','body');tool=native_solid_name('vacuum','tool')
    dead=mutation(blocks,4,body,tool)
    assert 'not-live' in project(dead,model).reasons[0]
    with pytest.raises(GeneratedCodeError):validate_geometry_history(model,swapped)


@pytest.mark.parametrize('scope,scopes',[('DS',('DS','root')),('root',('child',))])
def test_projection_requires_explicit_root_scope(scope,scopes):
    model=spec();blocks,_=render_geometry_history(model)
    report=project(blocks,model,scope=scope,available_scopes=scopes)
    assert report.status=='rejected' and not report.fields


def test_budgets_unknown_profile_and_invalid_text_are_rejected():
    model=spec();blocks,_=render_geometry_history(model)
    assert project(list(blocks)*200,model).status=='rejected'
    huge=[dict(caption='CST Tools GEO setup',history=' '* (2*1024*1024+1))]
    assert project(huge,model).status=='rejected'
    with pytest.raises(GeneratedCodeError):check_history('Brick.Create',profile='unknown')
    with pytest.raises(GeneratedCodeError):check_history('\ud800',profile=GEOMETRY_PROFILE)


def test_valid_but_overlong_emitted_statement_fails_with_feature_location():
    name='Radius'+'x'*55
    rows=[dict(op='set_parameters',values={name:dict(expression='1',quantity='length',description='radius')}),
        dict(op='ensure_component',component_id='vacuum'),
        dict(op='create_sphere',object_id='ball',component_id='vacuum',material_id='Vacuum',
             center_mm=['0']*3,radius_mm='+'.join([name]*10))]
    model=spec(rows)
    with pytest.raises(GeneratedCodeError) as caught:render_geometry_history(model)
    assert caught.value.feature_id==model['geometry']['features'][0]['feature_id']
    assert caught.value.input_field=='geometry.features[0]'


def test_source_map_binds_actual_lines_assignments_and_feature_fields():
    model=spec();blocks,_=render_geometry_history(model);mapping=geometry_definition_map(model,blocks)
    assert mapping['schema_version']==2 and mapping['profile']==GEOMETRY_PROFILE
    assert mapping['program_sha256']==hashlib.sha256(json.dumps(blocks,sort_keys=True,allow_nan=False).encode()).hexdigest()
    assert 'no executable macro' in mapping['outer_kind']
    for index,block in enumerate(blocks):
        lines=assign_string(Variable('history'),block['history'])
        rebuilt=''
        for line in lines[1:]:
            if line.endswith('& vbCrLf'):rebuilt+='\n'
            else:rebuilt+=line.partition('& "')[2][:-1].replace('""','"')
        assert rebuilt==block['history']
        for row in (r for r in mapping['outer'] if r['block_index']==index):
            assert 1<=row['line_start']<=row['line_end']<=len(lines)
            assert row['implementation']=='csttool.winwrap_emitter.assign_string'
    cylinder=next(r for r in mapping['history'] if r['block_index']==2 and r['method']=='OuterRadius')
    assert cylinder['input_field']=='geometry.features[1].outer_radius_mm'
    assert cylinder['feature_id']==model['geometry']['features'][1]['feature_id']
    boolean=next(r for r in mapping['history'] if r['block_index']==3 and r['method']=='Subtract')
    assert boolean['input_fields']==['geometry.features[2].target_id','geometry.features[2].tool_id','geometry.features[2].operation']
    raw='10576\nUnexpected text.\n[*check*#'+str(cylinder['line']+3)+'] '+cylinder['statement']+'\n'
    assert map_native_error(raw,mapping)['origin'] is None
    assert map_native_error(raw,mapping,block_index=2)['origin']==cylinder
    assert map_native_error(raw,mapping,block_index=True)['origin'] is None
    assert map_native_error(raw.replace(cylinder['statement'],'different statement'),mapping,block_index=2)['origin'] is None


def test_codegen_does_not_open_native_save_gate_or_call_editor(tmp_path,monkeypatch):
    app,empty,model,calls=draft(tmp_path)
    stamp=Path(__file__).resolve().parents[1]/'data/winwrap-a1-calibration.json'
    original=stamp.read_bytes()
    blocks,projection=render_geometry_history(model['spec'])
    assert projection.status=='resolved' and not projection.publish_ready
    def forbidden(*args,**kwargs):raise AssertionError('offline codegen cannot dispatch native')
    monkeypatch.setattr('csttool.native_definition_builder.run_new_definition',forbidden)
    monkeypatch.setattr('csttool.definition_editing.require_calibration',forbidden)
    def missing(target):raise GeneratedCodeError('synthetic GEO calibration absent')
    monkeypatch.setattr('csttool.definition_editing.require_geometry_calibration',missing)
    with pytest.raises(ValueError,match='GENERATED_CODE_INVALID'):
        app.execute_definition_operation(request(model,'save_project',validation_target='geometry'),operation_id='save')
    assert not (app.project/'control/runs/save/definition-intent.json').exists() and calls==[1]
    assert stamp.read_bytes()==original
    stale={**json.loads(original), 'sources':{}}
    with pytest.raises(GeneratedCodeError):check_calibration(stale,generator_fingerprint())
