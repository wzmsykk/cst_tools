"""Typed draft/publication safety, no CST launches."""
from copy import deepcopy
import json
from pathlib import Path
import re
import pytest
from csttool.application_service import ServiceError
from csttool.configuration import write_json_atomic, read_json
from csttool.definition_editing import (changed_spec, render_history, render_edit_macro,
    validate_edit, preflight_edit, edit_document, reconcile_edit)
from test.project_creation_test import service, payload
from test.saved_project_source_test import container


def changes():
    return [dict(op='set_parameters',values={
        'R':dict(expression='100',quantity='length',description='半径'),
        'L':dict(expression='R',quantity='length',description='length expression')}),
        dict(op='ensure_component',component_id='cavity'),
        dict(op='create_cylinder',object_id='pillbox',component_id='cavity',axis='z',center=['0']*3,
             axial_range=['-L/2','L/2'],outer_radius='R',inner_radius='0',material='Vacuum',segments=0),
        dict(op='set_background',material='PEC',padding_mm=[0]*6),
        dict(op='set_boundaries',faces=['electric']*6,symmetry=['none']*3)]


def configuration():
    return dict(simulation=dict(solver='eigenmode',method='default',mesh=dict(type='tet',cells_per_wavelength=4,adaptive=False),
        frequency_range_mhz={'min':500,'max':2000},frequency_lower_target_mhz=500,requested_modes=1,losses='postprocess_only'),
        postprocess=[dict(metric_id='frequency',method_id='Frequency',settings={'mode':dict(selection='one',index=1)}),
            dict(metric_id='rq',method_id='R_over_Q',settings={'mode':dict(selection='one',index=1),
                'integration_line':dict(axis='z',offset_mm=[0]*3,beta=1,range='full')})])


def request(record,operation,**args):
    return dict(kind='definition',operation=operation,document_id=record['document_id'],
                expected_document_revision=record['document_revision'],**args)


def draft(tmp_path):
    app,calls=service(tmp_path)
    empty=app.create_project(payload(),operation_id='create')
    model=edit_document(app,request(empty,'apply_model_changes',changes=changes()),operation_id='model')
    configured=edit_document(app,request(model,'configure_simulation',**configuration()),operation_id='config')
    return app,empty,model,configured,calls


def test_drafts_are_immutable_expression_preserving_and_do_not_launch_native(tmp_path):
    app,empty,model,configured,calls=draft(tmp_path)
    assert calls==[1] and not configured['ready']
    assert model['spec']['parameters']['L']['expression']=='R'
    assert app.inspect_model(empty['document_id'],empty['document_revision'])==empty
    assert app.inspect_model(model['document_id'],model['document_revision'])==model
    with pytest.raises(ServiceError,match='STALE_DOCUMENT'):
        preflight_edit(app,request(model,'configure_simulation',**configuration()))
    history,projection=render_history(configured['spec'])
    assert not projection.missing_fields and projection.fields['geometry.cylinder.outerradius']==100
    assert 'StoreParameter' not in history and 'Start' not in history
    assert '.Zrange 0+' in history and '.Zrange (' not in history
    macro=render_edit_macro(tmp_path,configured['spec'],'a'*32)
    macro.encode('ascii')  # Chinese descriptions use ChrW, not host code page.
    assert 'StoreParameters(names, expressions)' in macro and 'If Not Rebuild Then' in macro
    assert max(map(len,macro.splitlines()))<900
    assert ' & vbCrLf' in macro


@pytest.mark.parametrize('mutation', ['code','cycle','duplicate','dimension','center','axis','methods','nonfinite'])
def test_invalid_drafts_fail_before_intent_or_native(tmp_path,mutation):
    app,empty,model,configured,calls=draft(tmp_path)
    if mutation in ('axis','methods','nonfinite'):
        args=configuration(); op='configure_simulation'
        if mutation=='axis':args['postprocess'][1]['settings']['integration_line']['axis']='x'
        if mutation=='methods':args['postprocess'][1]=deepcopy(args['postprocess'][0])
        if mutation=='nonfinite':args['simulation']['frequency_range_mhz']['max']=float('nan')
    else:
        op='apply_model_changes';rows=changes();rows=rows[:1]
        if mutation=='code':rows[0]['values']['R']['expression']='100: Kill "x"'
        if mutation=='cycle':rows[0]['values']['R']['expression']='L'
        if mutation=='duplicate':rows[0]['values']['r']=rows[0]['values']['R']
        if mutation=='dimension':rows[0]['values']['R']['quantity']='frequency'
        if mutation=='center':
            rows=changes();rows[2]['center'][0]='1'
            # Use empty parent so this tests nonzero center rather than second cylinder.
            configured=empty
            write_json_atomic(tmp_path/'control/documents'/empty['document_id']/'current.json',dict(document_revision=empty['document_revision']))
        args=dict(changes=rows)
    with pytest.raises(ValueError):
        edit_document(app,request(configured,op,**args),operation_id='bad')
    assert not (tmp_path/'control/runs/bad/definition-intent.json').exists()
    assert calls==[1]


def test_committed_draft_response_gap_repairs_without_reapplying(tmp_path,monkeypatch):
    app,calls=service(tmp_path);empty=app.create_project(payload(),operation_id='create')
    import csttool.definition_editing as module
    original=module.write_json_atomic
    def broken(path,value):
        if path.name=='definition-result.json':raise OSError('response publication lost')
        return original(path,value)
    monkeypatch.setattr(module,'write_json_atomic',broken)
    command=request(empty,'apply_model_changes',changes=changes())
    with pytest.raises(OSError):edit_document(app,command,operation_id='gap')
    monkeypatch.setattr(module,'write_json_atomic',original)
    recovered=reconcile_edit(app,'gap')
    assert reconcile_edit(app,'gap')==recovered and calls==[1]
    assert edit_document(app,command,operation_id='gap')==recovered


def test_uncommitted_edit_never_replays_and_close_requires_explicit_save(tmp_path, monkeypatch):
    # Synthetic native peer only; the repository's real calibration stays stale
    # after generator changes until a separately authorized native acceptance.
    monkeypatch.setattr('csttool.definition_editing.require_calibration', lambda: {'fake_only': True})
    app,empty,model,configured,calls=draft(tmp_path)
    with pytest.raises(ServiceError,match='SETTING_UNVERIFIED'):
        preflight_edit(app,request(configured,'close_project',disposition='save'))
    def fail_editor(*args):raise OSError('native failed before commit')
    app.definition_editor=fail_editor
    command=request(configured,'save_project')
    with pytest.raises(OSError):edit_document(app,command,operation_id='save-fail')
    with pytest.raises(ServiceError,match='RUN_RECONCILIATION_REQUIRED'):reconcile_edit(app,'save-fail')
    with pytest.raises(ServiceError,match='RUN_RECONCILIATION_REQUIRED'):edit_document(app,command,operation_id='save-fail')
    assert app.inspect_model(configured['document_id'],configured['document_revision'])==configured


def test_save_uses_shared_g03_before_ready_and_preserves_parameters(tmp_path, monkeypatch):
    monkeypatch.setattr('csttool.definition_editing.require_calibration', lambda: {'fake_only': True})
    app,empty,model,configured,calls=draft(tmp_path)
    def editor(exe,path,directory,macro):
        spec=configured['spec'];history=render_history(spec)[0]
        path.write_bytes(container([('Model/3D/Model.mod',history.encode()),
            ('Model/Parameters.json',json.dumps({'parameters':[dict(name=k,expr=v['expression'],descr=v['description']) for k,v in spec['parameters'].items()]}).encode())]))
        nonce=re.search(r'Print #f, "([a-f0-9]{32})"',macro)[1]
        (directory/'completed.txt').write_text(nonce)
        write_json_atomic(directory/'session-status.json',dict(exit_confirmed=True,exit_code=0))
        return dict(exit_confirmed=True,exit_code=0)
    app.definition_editor=editor
    def verify(path,projection,exe):
        calls.append('verify')
        import hashlib
        return dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),scope='root',status='verified',
                    gates=['saved-reopened','identity','settings','standard-close'])
    verify.verify_on_stage=False
    app.definition_verifier=verify
    saved=edit_document(app,request(configured,'save_project'),operation_id='save')
    assert calls==[1,'verify'] and saved['ready'] and saved['state']=='saved'
    assert saved['geometry_saved'] and saved['validation_target']=='simulation'
    assert app.inspect_model(saved['document_id'],saved['document_revision'])==saved
    assert app.inspect_definition(saved['document_id'],saved['definition_revision'])['ready']
    closed=edit_document(app,request(saved,'close_project',disposition='save'),operation_id='close')
    assert closed['state']=='closed'
    with pytest.raises(ServiceError,match='DOCUMENT_CLOSED'):preflight_edit(app,request(closed,'apply_model_changes',changes=changes()[:1]))
