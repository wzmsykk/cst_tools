"""GEO-1 public definition transactions and declaration projection; no CST."""
from copy import deepcopy
import pytest

from csttool.application_service import ServiceError
from csttool.configuration import write_json_atomic
from csttool.definition_editing import (changed_spec, edit_document, fingerprint,
    preflight_edit, reconcile_edit, render_history, validate_edit, SCHEMA)
from csttool.geometry_contract import project_geometry
from test.project_creation_test import service, payload
from test.definition_editing_test import request, changes as a1_changes


def changes():
    return [
        dict(op='set_parameters', values={
            'R':dict(expression='5',quantity='length',description='孔半径'),
            'H':dict(expression='4*R',quantity='length',description='高度')}),
        dict(op='ensure_component',component_id='vacuum'),
        dict(op='create_brick',object_id='body',component_id='vacuum',material_id='Vacuum',
             bounds_mm={a:['-H','H'] for a in 'xyz'}),
        dict(op='create_cylinder',object_id='tool',component_id='vacuum',material_id='Vacuum',
             axis='z',transverse_center_mm=['R','0'],axial_range_mm=['-H','H'],
             outer_radius_mm='R',inner_radius_mm='R/2'),
        dict(op='boolean_solids',operation='difference',target_id='body',tool_id='tool'),
        dict(op='translate_solid',target_id='body',translation_mm=['R','0','H']),
        dict(op='define_selection_set',selection_id='cavity',entity_kind='solid',members=['body'])]


def geo_request(record, rows=None):
    return request(record,'apply_model_changes',geometry_profile='geometry-v1',changes=changes() if rows is None else rows)


def draft(tmp_path):
    app, calls = service(tmp_path)
    empty = app.create_project(payload(), operation_id='create')
    model = edit_document(app, geo_request(empty), operation_id='geo')
    return app, empty, model, calls


def test_public_transaction_persists_expressions_projection_and_distinct_readiness(tmp_path):
    app, empty, model, calls = draft(tmp_path)
    assert calls == [1]  # only the synthetic empty-project creator
    assert model['state']=='draft' and model['ready'] is False
    assert model['geometry_saved'] is False and model['definition_revision'] is None
    assert model['validation_target'] is None
    assert model['spec']['parameters']['H']['expression']=='4*R'
    projection = model['geometry_projection']
    assert projection['evidence']=='declaration' and not projection['native_verified']
    assert not projection['simulation_supported'] and not projection['native_save_supported']
    assert projection['objects']['body']['state']=='live'
    assert projection['objects']['tool']['state']=='consumed'
    assert projection['selection_sets']=={'cavity':['body']}
    assert projection['features'][0]['resolved']['z']==['-20','20']
    assert len({f['caption'] for f in projection['features']})==len(projection['features'])
    assert app.inspect_model(model['document_id'],model['document_revision'])==model
    assert app.inspect_model(empty['document_id'],empty['document_revision'])==empty
    assert edit_document(app,geo_request(empty),operation_id='geo')==model
    assert reconcile_edit(app,'geo')==model
    changed = edit_document(app,geo_request(model,[dict(op='set_parameters',values={
        'R':dict(expression='6',quantity='length',description='孔半径')})]),operation_id='param')
    assert changed['geometry_projection']['features'][0]['resolved']['z']==['-24','24']
    assert changed['spec']['geometry']['features']==model['spec']['geometry']['features']
    assert calls==[1] and not changed['geometry_saved']


@pytest.mark.parametrize('axis',list('xyz'))
def test_xyz_nonzero_hollow_cylinder_and_sphere_inputs_are_projected_without_geometry_claims(tmp_path,axis):
    app,calls=service(tmp_path); empty=app.create_project(payload(),operation_id='create')
    rows=changes()[:2]+[dict(op='create_cylinder',object_id='tube',component_id='vacuum',material_id='PEC',
        axis=axis,transverse_center_mm=['1','2'],axial_range_mm=['3','7'],outer_radius_mm='5',inner_radius_mm='2'),
        dict(op='create_sphere',object_id='sphere',component_id='vacuum',material_id='Vacuum',center_mm=['1','2','3'],radius_mm='R')]
    model=edit_document(app,geo_request(empty,rows),operation_id='geo')
    resolved=model['geometry_projection']['features'][0]['resolved']
    assert resolved['axis']==axis and resolved['transverse_center_mm']==['1','2']
    assert resolved['axial_range_mm']==['3','7']
    assert 'volume' not in model['geometry_projection']['objects']['tube']
    assert calls==[1]


@pytest.mark.parametrize('mutation',[
    'missing-component','forward-component','duplicate-id','case-id','missing-target',
    'self-boolean','cross-material','cross-component','consumed-member','consumed-target',
    'reused-tombstone','dangling-after-delete','empty-set','duplicate-members','face-set',
    'bad-path','script','function','cycle','transitive-quantity','invalid-radius','invalid-bounds',
    'nonfinite','extra-field','mixed-a1','missing-profile'])
def test_invalid_batches_fail_before_intent_and_preserve_previous_revision(tmp_path,mutation):
    app,calls=service(tmp_path);empty=app.create_project(payload(),operation_id='create')
    rows=changes(); command=geo_request(empty,rows)
    if mutation=='missing-component': rows.pop(1)
    elif mutation=='forward-component': rows.insert(3,rows.pop(1))
    elif mutation=='duplicate-id': rows[3]['object_id']='body'
    elif mutation=='case-id': rows[3]['object_id']='BODY'
    elif mutation=='missing-target':rows[4]['target_id']='absent'
    elif mutation=='self-boolean':rows[4]['tool_id']='body'
    elif mutation=='cross-material':rows[3]['material_id']='PEC'
    elif mutation=='cross-component':
        rows[3]['component_id']='other';rows.insert(2,dict(op='ensure_component',component_id='other'))
    elif mutation=='consumed-member':rows[-1]['members']=['tool']
    elif mutation=='consumed-target':rows[5]['target_id']='tool'
    elif mutation=='reused-tombstone':rows.insert(5,deepcopy(rows[3]))
    elif mutation=='dangling-after-delete':rows.append(dict(op='delete_object',object_id='body'))
    elif mutation=='empty-set':rows[-1]['members']=[]
    elif mutation=='duplicate-members':rows[-1]['members']=['body','body']
    elif mutation=='face-set':rows[-1]['entity_kind']='face'
    elif mutation=='bad-path':rows[2]['object_id']='root:body'
    elif mutation=='script':rows[2]['bounds_mm']['x'][0]='0: Kill "x"'
    elif mutation=='function':rows[2]['bounds_mm']['x'][0]='abs(R)'
    elif mutation=='cycle':rows[0]['values']['R']['expression']='H'
    elif mutation=='transitive-quantity':rows[0]['values']['R']['quantity']='frequency'
    elif mutation=='invalid-radius':rows[3]['inner_radius_mm']='R'
    elif mutation=='invalid-bounds':rows[2]['bounds_mm']['z']=['H','-H']
    elif mutation=='nonfinite':rows[0]['values']['R']['expression']='1e999'
    elif mutation=='extra-field':rows[2]['vba']='Execute arbitrary'
    elif mutation=='mixed-a1':rows[3]=a1_changes()[2]
    elif mutation=='missing-profile':command.pop('geometry_profile')
    with pytest.raises(ServiceError):edit_document(app,command,operation_id='bad')
    assert not (tmp_path/'control/runs/bad/definition-intent.json').exists()
    assert app.inspect_model(empty['document_id'],empty['document_revision'])==empty and calls==[1]


def test_delete_requires_explicit_selection_update_and_does_not_reuse_id(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    updated=edit_document(app,geo_request(model,[dict(op='delete_object',object_id='body'),
        dict(op='delete_selection_set',selection_id='cavity')]),operation_id='delete')
    assert updated['geometry_projection']['objects']['body']['state']=='deleted'
    assert updated['geometry_projection']['selection_sets']=={}
    assert model['geometry_projection']['selection_sets']=={'cavity':['body']}
    with pytest.raises(ServiceError):
        edit_document(app,geo_request(updated,[changes()[2]]),operation_id='reuse')
    assert calls==[1]


@pytest.mark.parametrize('target',[None,'geometry','simulation'])
def test_native_save_not_authorized_by_declaration_or_a1_stamp(tmp_path,monkeypatch,target):
    app,empty,model,calls=draft(tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError('must reject before native/gate/intent')
    app.definition_editor=forbidden
    monkeypatch.setattr('csttool.definition_editing.require_calibration',forbidden)
    from csttool.winwrap_emitter import GeneratedCodeError
    def missing(target):raise GeneratedCodeError('synthetic GEO calibration absent')
    monkeypatch.setattr('csttool.definition_editing.require_geometry_calibration',missing)
    args={} if target is None else dict(validation_target=target)
    with pytest.raises(ValueError,match='INVALID_ARGUMENT' if target is None else 'GENERATED_CODE_INVALID' if target=='geometry' else 'SETTING_UNVERIFIED'):
        edit_document(app,request(model,'save_project',**args),operation_id='save')
    assert not (tmp_path/'control/runs/save/definition-intent.json').exists()
    assert app.inspect_model(model['document_id'],model['document_revision'])==model
    with pytest.raises(ServiceError,match='UNSUPPORTED_CAPABILITY'):render_history(model['spec'])
    assert calls==[1]


def test_profile_cannot_be_switched_or_implicitly_upgraded_and_close_is_metadata_only(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    with pytest.raises(ServiceError):preflight_edit(app,request(model,'apply_model_changes',changes=changes()[:1]))
    with pytest.raises(ServiceError):changed_spec(model,request(model,'configure_simulation'))
    with pytest.raises(ServiceError):changed_spec({'spec':{'parameters':{},'components':[],'cylinder':{}}},geo_request(model))
    with pytest.raises(ServiceError,match='SETTING_UNVERIFIED'):
        preflight_edit(app,request(model,'close_project',disposition='save'))
    closed=edit_document(app,request(model,'close_project',disposition='discard_candidate'),operation_id='close')
    assert closed['state']=='closed' and not closed['geometry_saved'] and not closed['ready']
    assert app.inspect_model(closed['document_id'],closed['document_revision'])==closed
    assert calls==[1]


def test_response_gap_reconciliation_and_later_cas_are_shared_not_replayed(tmp_path,monkeypatch):
    app,calls=service(tmp_path);empty=app.create_project(payload(),operation_id='create')
    import csttool.definition_editing as module
    original=module.write_json_atomic
    def broken(path,value):
        if path.name=='definition-result.json':raise OSError('response gap')
        return original(path,value)
    monkeypatch.setattr(module,'write_json_atomic',broken)
    with pytest.raises(OSError):edit_document(app,geo_request(empty),operation_id='gap')
    monkeypatch.setattr(module,'write_json_atomic',original)
    recovered=reconcile_edit(app,'gap')
    assert reconcile_edit(app,'gap')==recovered
    with pytest.raises(ServiceError,match='STALE_DOCUMENT'):preflight_edit(app,geo_request(empty))
    assert calls==[1]


@pytest.mark.parametrize('field,value',[('ready',True),('geometry_saved',True),('state','saved'),
    ('definition_revision','a'*64),('validation_target','geometry'),('geometry_projection',{})])
def test_even_rehashed_metadata_cannot_claim_unobserved_native_save_or_readiness(tmp_path,field,value):
    app,empty,model,calls=draft(tmp_path)
    bad={**model,field:value};bad.pop('document_revision');bad['document_revision']=fingerprint(bad)
    write_json_atomic(tmp_path/'control/documents'/bad['document_id']/(bad['document_revision']+'.json'),bad)
    with pytest.raises(ServiceError,match='DOCUMENT_INVALID'):
        app.inspect_model(bad['document_id'],bad['document_revision'])


def test_projection_budgets_and_parameter_edits_revalidate_existing_geometry(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    for key, value in [('components',['c'+str(i) for i in range(33)]),
                       ('geometry',dict(profile='geometry-v1',features=model['spec']['geometry']['features']*129))]:
        spec=deepcopy(model['spec']);spec[key]=value
        with pytest.raises(ServiceError):project_geometry(spec)
    with pytest.raises(ServiceError):edit_document(app,geo_request(model,[dict(op='set_parameters',values={
        'R':dict(expression='-1',quantity='length',description='半径')})]),operation_id='invalid-edit')
    assert not (tmp_path/'control/runs/invalid-edit/definition-intent.json').exists()
    assert calls==[1]


def test_shared_schema_is_valid_and_requires_explicit_profile_for_new_changes():
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(SCHEMA)
    parent=dict(document_id='doc',document_revision='a'*64)
    validate_edit(geo_request(parent))
    invalid=geo_request(parent);invalid.pop('geometry_profile')
    with pytest.raises(ServiceError):validate_edit(invalid)
    for target in ('geometry','simulation'):
        validate_edit(request(parent,'save_project',validation_target=target))
    with pytest.raises(ServiceError):validate_edit(request(parent,'save_project',validation_target='anything'))


def test_existing_application_service_and_runner_accept_the_same_geometry_payload(tmp_path):
    from csttool.runner import validate_run_payload
    app,calls=service(tmp_path)
    empty=app.create_project(payload(),operation_id='create')
    command=geo_request(empty)
    validate_run_payload(command)
    assert app.preflight_definition_operation(command)==empty
    model=app.execute_definition_operation(command,operation_id='shared-geo')
    assert app.definition_operation_result('shared-geo')==model
    assert model['geometry_projection']['selection_sets']=={'cavity':['body']}
    assert not model['ready'] and calls==[1]


@pytest.mark.parametrize('operation',['union','difference','intersection'])
def test_boolean_contract_consumes_only_tool_without_claiming_native_result(operation):
    rows=changes();rows[4]['operation']=operation
    spec=changed_spec({},dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=rows))
    projected=project_geometry(spec)
    assert projected['objects']['body']['state']=='live'
    assert projected['objects']['tool']['state']=='consumed'
    assert projected['features'][2]['resolved']['result_geometry']=='unverified'


def test_parameter_case_collision_is_rejected_and_members_canonicalized(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    rows=[dict(op='create_sphere',object_id='ball',component_id='vacuum',material_id='Vacuum',
        center_mm=['0']*3,radius_mm='R'),
        dict(op='define_selection_set',selection_id='both',entity_kind='solid',members=['body','ball'])]
    updated=edit_document(app,geo_request(model,rows),operation_id='set')
    assert updated['geometry_projection']['selection_sets']['both']==['ball','body']
    with pytest.raises(ServiceError):edit_document(app,geo_request(updated,[dict(op='set_parameters',values={
        'r':dict(expression='2',quantity='length',description='duplicate')})]),operation_id='collision')


def test_documents_above_snapshot_default_remain_readable_and_total_budget_rejects_before_intent(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    def parameters(count):
        return [dict(op='set_parameters',values={'P'+str(i):dict(expression='1'+' '*4095,
            quantity='length',description='long bounded expression') for i in range(count)})]
    large=edit_document(app,geo_request(model,parameters(20)),operation_id='large')
    path=tmp_path/'control/documents'/large['document_id']/(large['document_revision']+'.json')
    assert path.stat().st_size>64*1024
    assert app.inspect_model(large['document_id'],large['document_revision'])==large
    with pytest.raises(ServiceError,match='512 KiB'):
        edit_document(app,geo_request(large,parameters(126)),operation_id='too-large')
    assert not (tmp_path/'control/runs/too-large/definition-intent.json').exists()
    assert calls==[1]
