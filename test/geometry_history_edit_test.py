"""H1-H7: sequential declaration editing via the shared service, no CST."""
from copy import deepcopy
import hashlib

import pytest

from csttool.application_service import ServiceError
from csttool.configuration import read_json, write_json_atomic
from csttool.definition_editing import (edit_document, fingerprint,
    preflight_edit, reconcile_edit)
from csttool.geometry_contract import project_geometry
from test.geometry_contract_test import changes, draft, geo_request
from test.definition_editing_test import request
from test.project_creation_test import service, payload


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('GEO-1.1 must never invoke native construction or calibration')
    monkeypatch.setattr('csttool.native_definition_builder.run_new_definition',forbidden)
    monkeypatch.setattr('csttool.definition_editing.require_calibration',forbidden)


def feature(model, op, oid=None):
    return next(r for r in model['spec']['geometry']['features']
                if r['op']==op and (oid is None or r.get('object_id')==oid))


def update(row, **values):
    replacement={k:deepcopy(v) for k,v in row.items() if k!='feature_id'}
    replacement.update(values)
    return dict(op='update_feature',feature_id=row['feature_id'],replacement=replacement)


def remove(row):
    return dict(op='remove_feature',feature_id=row['feature_id'])


def apply(app, model, rows, run):
    return app.execute_definition_operation(geo_request(model,rows),operation_id=run)


def projected(model, row):
    return next(r for r in model['geometry_projection']['features'] if r['feature_id']==row['feature_id'])


def assert_unchanged(app, model, run):
    current=read_json(app.project/'control/documents'/model['document_id']/'current.json')
    assert current['document_revision']==model['document_revision']
    assert app.inspect_model(model['document_id'],model['document_revision'])==model
    assert not (app.project/'control/runs'/run/'definition-intent.json').exists()


def test_h1_update_dimensions_and_translation_preserves_identity_expression_and_old_revision(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    body=feature(model,'create_brick'); move=feature(model,'translate_solid')
    before=deepcopy(model)
    changed=apply(app,model,[update(body,bounds_mm={a:['-R','R'] for a in 'xyz'}),
        update(move,translation_mm=['H','R','0'])],'edit')
    assert [r['feature_id'] for r in changed['spec']['geometry']['features']]==[r['feature_id'] for r in model['spec']['geometry']['features']]
    assert projected(changed,body)['resolved']['x']==['-5','5']
    assert projected(changed,move)['resolved']['translation_mm']==['20','5','0']
    assert projected(changed,body)['content_sha256']!=projected(model,body)['content_sha256']
    assert projected(changed,body)['caption']==projected(model,body)['caption']
    assert feature(changed,'create_brick')['bounds_mm']['x']==['-R','R']
    assert changed['spec']['geometry']['identities']==model['spec']['geometry']['identities']
    assert changed['source_sha256']==model['source_sha256'] and not changed['geometry_saved'] and not changed['ready']
    assert model==before and app.inspect_model(model['document_id'],model['document_revision'])==before
    assert calls==[1]


@pytest.mark.parametrize('mutation',['kind','rename','unknown-field','partial-replacement','unknown-id','reorder'])
def test_h1_typed_update_cannot_change_feature_kind_identity_or_order(tmp_path,mutation):
    app,empty,model,calls=draft(tmp_path); row=feature(model,'create_brick'); command=update(row)
    if mutation=='kind':command['replacement']={k:v for k,v in changes()[3].items()};command['replacement']['object_id']='body'
    elif mutation=='rename':command['replacement']['object_id']='different'
    elif mutation=='unknown-field':command['replacement']['properties_json']='arbitrary'
    elif mutation=='partial-replacement':command['replacement']={'bounds_mm':{'x':['0','1']}}
    elif mutation=='unknown-id':command['feature_id']='f_'+'0'*32
    else:command['position']=0
    with pytest.raises(ServiceError):apply(app,model,[command],'bad')
    assert_unchanged(app,model,'bad')


def three_solids(tmp_path, material='Vacuum'):
    app,calls=service(tmp_path);empty=app.create_project(payload(),operation_id='create')
    rows=changes();rows.insert(4,dict(op='create_sphere',object_id='other',component_id='vacuum',
        material_id=material,center_mm=['0']*3,radius_mm='R'))
    model=apply(app,empty,rows,'model')
    return app,model,calls


def test_h2_boolean_input_update_rebuilds_dependency_and_consumption_projection(tmp_path):
    app,model,calls=three_solids(tmp_path)
    boolean=feature(model,'boolean_solids'); body=feature(model,'create_brick');other=feature(model,'create_sphere')
    move=feature(model,'translate_solid')
    changed=apply(app,model,[update(boolean,tool_id='other')],'edit')
    objects=changed['geometry_projection']['objects']
    assert objects['other']['state']=='consumed' and objects['tool']['state']=='live'
    assert projected(changed,boolean)['depends_on']==sorted([body['feature_id'],other['feature_id']])
    assert projected(changed,move)['depends_on']==[boolean['feature_id']]
    assert projected(changed,boolean)['consumers']==[move['feature_id']]
    assert projected(changed,move)['selection_consumers']==['cavity']
    assert projected(changed,boolean)['inputs'][1]['source_feature_id']==other['feature_id']
    assert objects['body']['native_name']==model['geometry_projection']['objects']['body']['native_name']
    assert calls==[1]


@pytest.mark.parametrize('case,code',[('missing','missing-object'),('forward','forward-reference'),
    ('self','self-boolean'),('material','incompatible-operands'),('consumed','consumed')])
def test_h2_invalid_operands_report_cause_and_transitive_consumers(tmp_path,case,code):
    app,model,calls=three_solids(tmp_path,material='PEC' if case=='material' else 'Vacuum')
    boolean=feature(model,'boolean_solids'); move=feature(model,'translate_solid')
    if case=='forward':
        model=apply(app,model,[dict(op='create_sphere',object_id='later',component_id='vacuum',material_id='Vacuum',center_mm=['0']*3,radius_mm='R')],'later')
    if case=='consumed':
        command=dict(op='translate_solid',target_id='tool',translation_mm=['0']*3)
    else:command=update(boolean,tool_id={'missing':'absent','forward':'later','self':'body','material':'other'}[case])
    with pytest.raises(ServiceError) as caught:apply(app,model,[command],'bad')
    diagnostics=caught.value.diagnostics
    assert code in {r['code'] for r in diagnostics['issues']}
    assert diagnostics['phase']=='geometry-declaration' and 'geometry_diagnostics=' in str(caught.value)
    if case!='consumed':
        assert boolean['feature_id'] in diagnostics['affected_feature_ids']
        assert move['feature_id'] in diagnostics['affected_feature_ids']
        assert 'cavity' in diagnostics['affected_selection_ids']
    assert_unchanged(app,model,'bad')


def test_h3_remove_boolean_is_not_delete_solid_and_remaining_features_are_replayed(tmp_path):
    app,empty,model,calls=draft(tmp_path); boolean=feature(model,'boolean_solids');move=feature(model,'translate_solid')
    changed=apply(app,model,[remove(boolean)],'remove-boolean')
    assert changed['geometry_projection']['objects']['tool']['state']=='live'
    assert changed['geometry_projection']['objects']['body']['state']=='live'
    assert projected(changed,move)['depends_on']==[feature(changed,'create_brick')['feature_id']]
    deleted=apply(app,changed,[dict(op='delete_object',object_id='body'),dict(op='delete_selection_set',selection_id='cavity')],'delete-body')
    assert deleted['geometry_projection']['objects']['body']['state']=='deleted'
    restored=apply(app,deleted,[remove(feature(deleted,'delete_object'))],'undo-delete')
    assert restored['geometry_projection']['objects']['body']['state']=='live'
    assert restored['spec']['geometry']['identities']==model['spec']['geometry']['identities']
    assert calls==[1]


def test_h4_remove_creator_reports_all_downstream_and_requires_explicit_batch_repair(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    body=feature(model,'create_brick');boolean=feature(model,'boolean_solids');move=feature(model,'translate_solid')
    with pytest.raises(ServiceError) as caught:apply(app,model,[remove(body)],'bad')
    diagnostics=caught.value.diagnostics
    assert any(r['code']=='removed-creator' and r['object_id']=='body' and r['causal_feature_id']==body['feature_id'] for r in diagnostics['issues'])
    assert diagnostics['affected_feature_ids']==[boolean['feature_id'],move['feature_id']]
    assert diagnostics['affected_selection_ids']==['cavity']
    assert_unchanged(app,model,'bad')
    repaired=apply(app,model,[remove(body),remove(boolean),remove(move),dict(op='delete_selection_set',selection_id='cavity')],'repair')
    assert 'body' not in repaired['geometry_projection']['objects']
    assert repaired['spec']['geometry']['identities']['body']==body['feature_id']
    for oid in ['body','BODY']:
        command={k:v for k,v in body.items() if k!='feature_id'};command['object_id']=oid
        with pytest.raises(ServiceError,match='cannot be reused'):apply(app,repaired,[command],'reuse-'+oid)
    assert app.inspect_model(model['document_id'],model['document_revision'])==model
    assert calls==[1]


def test_h4_reservation_drop_or_reassignment_is_rejected_against_immediate_parent(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    body=feature(model,'create_brick')
    changed=apply(app,model,[remove(body),remove(feature(model,'boolean_solids')),remove(feature(model,'translate_solid')),
        dict(op='delete_selection_set',selection_id='cavity')],'remove')
    for new_owner in [None,'f_'+'0'*32]:
        bad=deepcopy(changed);bad.pop('document_revision')
        if new_owner is None:del bad['spec']['geometry']['identities']['body']
        else:bad['spec']['geometry']['identities']['body']=new_owner
        bad['geometry_projection']=project_geometry(bad['spec']);bad['document_revision']=fingerprint(bad)
        write_json_atomic(app.project/'control/documents'/bad['document_id']/(bad['document_revision']+'.json'),bad)
        with pytest.raises(ServiceError,match='reservations cannot'):
            app.inspect_model(bad['document_id'],bad['document_revision'])


def test_h5_current_parameter_table_updates_all_dependencies_and_independent_parameters(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    model=apply(app,model,[dict(op='set_parameters',values={
        'R_A':dict(expression='2',quantity='length',description='A'),
        'R_B':dict(expression='3',quantity='length',description='B')}),
        dict(op='create_sphere',object_id='a',component_id='vacuum',material_id='Vacuum',center_mm=['0']*3,radius_mm='R_A'),
        dict(op='create_sphere',object_id='b',component_id='vacuum',material_id='Vacuum',center_mm=['0']*3,radius_mm='R_B')],'independent')
    changed=apply(app,model,[dict(op='set_parameters',values={'R':dict(expression='6',quantity='length',description='半径')})],'parameters')
    body=feature(model,'create_brick');cylinder=feature(model,'create_cylinder')
    assert projected(changed,body)['parameter_names']==['H','R']
    assert projected(changed,body)['resolved']['x']==['-24','24']
    assert projected(changed,cylinder)['resolved']['outer_radius_mm']=='6'
    assert projected(changed,feature(model,'create_sphere','a'))['resolved']['radius_mm']=='2'
    assert projected(changed,feature(model,'create_sphere','b'))['resolved']['radius_mm']=='3'
    assert projected(changed,body)['content_sha256']==projected(model,body)['content_sha256']
    assert changed['spec']['parameters']['H']['expression']=='4*R'
    assert calls==[1]


def test_h5_invalid_dimensions_include_feature_field_and_affected_selection(tmp_path):
    app,empty,model,calls=draft(tmp_path);body=feature(model,'create_brick')
    with pytest.raises(ServiceError) as caught:
        apply(app,model,[update(body,bounds_mm={a:['R','-R'] for a in 'xyz'})],'bad')
    diagnostic=caught.value.diagnostics
    assert diagnostic['issues'][0]['feature_id']==body['feature_id']
    assert diagnostic['issues'][0]['input_field']=='bounds_mm.x'
    assert diagnostic['affected_selection_ids']==['cavity']
    assert_unchanged(app,model,'bad')


@pytest.mark.parametrize('gap',['definition-commit.json','current.json','definition-result.json'])
def test_h6_durable_write_gaps_reconcile_commits_without_reapplying(tmp_path,monkeypatch,gap):
    app,empty,model,calls=draft(tmp_path)
    import csttool.definition_editing as module
    original=module.write_json_atomic
    def broken(path,value):
        if path.name==gap:raise OSError('injected '+gap)
        return original(path,value)
    command=geo_request(model,[remove(feature(model,'boolean_solids'))])
    monkeypatch.setattr(module,'write_json_atomic',broken)
    with pytest.raises(OSError):app.execute_definition_operation(command,operation_id='gap')
    monkeypatch.setattr(module,'write_json_atomic',original)
    if gap=='definition-commit.json':
        with pytest.raises(ServiceError,match='RUN_RECONCILIATION_REQUIRED'):reconcile_edit(app,'gap')
        with pytest.raises(ServiceError,match='RUN_RECONCILIATION_REQUIRED'):edit_document(app,command,operation_id='gap')
        assert read_json(app.project/'control/documents'/model['document_id']/'current.json')['document_revision']==model['document_revision']
    else:
        repaired=reconcile_edit(app,'gap')
        assert repaired['geometry_projection']['objects']['tool']['state']=='live'
        assert reconcile_edit(app,'gap')==repaired
        assert edit_document(app,command,operation_id='gap')==repaired
        changed_command=geo_request(model,[remove(feature(model,'translate_solid'))])
        with pytest.raises(ServiceError,match='REQUEST_CONFLICT'):edit_document(app,changed_command,operation_id='gap')
    assert calls==[1]


def test_h6_late_recovery_never_moves_current_back_or_repeats_edit(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    earlier=apply(app,model,[remove(feature(model,'boolean_solids'))],'earlier')
    later=apply(app,earlier,[update(feature(earlier,'translate_solid'),translation_mm=['1','2','3'])],'later')
    (app.project/'control/runs/earlier/definition-result.json').unlink()
    with pytest.raises(ServiceError,match='STALE_DOCUMENT'):reconcile_edit(app,'earlier')
    with pytest.raises(ServiceError,match='STALE_DOCUMENT'):preflight_edit(app,geo_request(model,[remove(feature(model,'translate_solid'))]))
    assert read_json(app.project/'control/documents'/model['document_id']/'current.json')['document_revision']==later['document_revision']
    assert calls==[1]


@pytest.mark.parametrize('stop_at',[1,2])
def test_h6_interrupted_edit_does_not_publish_or_replay(tmp_path,stop_at):
    app,empty,model,calls=draft(tmp_path);count=[]
    def cancel():
        count.append(1)
        if len(count)==stop_at:raise RuntimeError('paused offline edit')
    command=geo_request(model,[remove(feature(model,'boolean_solids'))])
    with pytest.raises(RuntimeError):edit_document(app,command,operation_id='stop',cancel_check=cancel)
    assert not (app.project/'control/runs/stop/definition-commit.json').exists()
    assert read_json(app.project/'control/documents'/model['document_id']/'current.json')['document_revision']==model['document_revision']
    if stop_at==2:
        with pytest.raises(ServiceError,match='RUN_RECONCILIATION_REQUIRED'):reconcile_edit(app,'stop')
    assert calls==[1]


@pytest.mark.parametrize('value',[True,None,[],{'vba':'run'},'unknown'])
def test_h7_unknown_or_untyped_feature_edits_reject_before_intent(tmp_path,value):
    app,empty,model,calls=draft(tmp_path)
    with pytest.raises(ServiceError):apply(app,model,[dict(op='update_feature',feature_id=feature(model,'create_brick')['feature_id'],replacement=value)],'bad')
    assert_unchanged(app,model,'bad')


def test_h7_identity_reservations_are_bounded_independently_of_live_features(tmp_path):
    app,empty,model,calls=draft(tmp_path);spec=deepcopy(model['spec'])
    reserved=spec['geometry']['identities']
    for i in range(512-len(reserved)):reserved['retired'+str(i)]='f_'+hashlib.sha256(str(i).encode()).hexdigest()[:32]
    assert project_geometry(spec)['native_build_state']=='unverified'
    reserved['oneMore']='f_'+'0'*32
    with pytest.raises(ServiceError):project_geometry(spec)
    with pytest.raises(ServiceError):apply(app,model,[dict(op='remove_feature',feature_id=feature(model,'create_brick')['feature_id'],identities={})],'bad')
    assert_unchanged(app,model,'bad')


def test_h7_empty_and_removed_references_do_not_authorize_native_save_or_ready(tmp_path,monkeypatch):
    from csttool.winwrap_emitter import GeneratedCodeError
    def missing(target):raise GeneratedCodeError('synthetic GEO calibration absent')
    monkeypatch.setattr('csttool.definition_editing.require_geometry_calibration',missing)
    app,empty,model,calls=draft(tmp_path)
    rows=[remove(row) for row in model['spec']['geometry']['features']]+[dict(op='delete_selection_set',selection_id='cavity')]
    changed=apply(app,model,rows,'empty-geometry')
    assert changed['spec']['geometry']['features']==[] and len(changed['spec']['geometry']['identities'])==2
    assert changed['geometry_projection']['declaration_valid'] and not changed['geometry_saved'] and not changed['ready']
    for target in ['geometry','simulation']:
        with pytest.raises(ValueError,match='GENERATED_CODE_INVALID' if target=='geometry' else 'SETTING_UNVERIFIED'):
            app.execute_definition_operation(request(changed,'save_project',validation_target=target),operation_id='save-'+target)
        assert not (app.project/'control/runs'/('save-'+target)/'definition-intent.json').exists()
    assert calls==[1]


def test_h7_diagnostic_issue_truncation_preserves_total_and_all_affected_steps(tmp_path):
    app,empty,model,calls=draft(tmp_path);spec=deepcopy(model['spec'])
    body=feature(model,'create_brick')
    spec['geometry']['features']=[r for r in spec['geometry']['features'] if r['feature_id']!=body['feature_id']]
    for i in range(80):
        spec['geometry']['features'].append(dict(feature_id='f_'+hashlib.sha256(('tail'+str(i)).encode()).hexdigest()[:32],
            op='translate_solid',target_id='body',translation_mm=['0']*3))
    with pytest.raises(ServiceError) as caught:project_geometry(spec)
    diagnostics=caught.value.diagnostics
    assert diagnostics['issue_count']>64 and len(diagnostics['issues'])==64 and diagnostics['issues_truncated']
    assert spec['geometry']['features'][-1]['feature_id'] in diagnostics['affected_feature_ids']
    assert '"truncated":true' in str(caught.value)
    assert len(str(caught.value))<5000


def test_h5_invalid_parameter_reports_phase_without_claiming_complete_geometry_impact(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    with pytest.raises(ServiceError) as caught:
        apply(app,model,[dict(op='set_parameters',values={'R':dict(expression='H',quantity='length',description='cycle')})],'bad')
    diagnostic=caught.value.diagnostics
    assert diagnostic['phase']=='geometry-parameters'
    assert diagnostic['issues'][0]['input_field']=='parameters.R'
    assert diagnostic['impact_complete'] is False
    assert_unchanged(app,model,'bad')


def test_h7_obsolete_development_spec_is_rejected_without_rewriting_old_revision(tmp_path):
    app,empty,model,calls=draft(tmp_path)
    old=deepcopy(model);old.pop('document_revision');del old['spec']['geometry']['identities']
    old['document_revision']=fingerprint(old)
    path=app.project/'control/documents'/old['document_id']/(old['document_revision']+'.json')
    write_json_atomic(path,old);before=path.read_bytes()
    with pytest.raises(ServiceError,match='identities are required'):
        app.inspect_model(old['document_id'],old['document_revision'])
    assert path.read_bytes()==before and calls==[1]
