"""GEO shared transaction/G03/MCP tests with explicit fake native peers."""
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import pytest
from csttool.application_service import ServiceError
from csttool.configuration import read_json,write_json_atomic
from csttool.definition_editing import edit_document,reconcile_edit
from csttool.definition_verifier import NativeDefinitionVerifier
from csttool.definition_geometry import geometry_objects
from csttool.execution_contract import StopIntent
from test.project_creation_test import service,payload
from test.geometry_contract_test import geo_request
from test.definition_editing_test import request,configuration
from test.history_program_test import saved
from test.single_simulation_service_test import FakeWorker
from test.support.calibrate_geometry import specimen


def geometry_service(tmp_path,monkeypatch):
    monkeypatch.setattr('csttool.definition_editing.require_geometry_calibration',lambda target:dict(fake_only=True))
    app,_=service(tmp_path);attempts=[]
    app.installations['local'].write_bytes(b'fake launcher')
    fake_modeler=tmp_path/'AMD64/modeler_AMD64.exe';fake_modeler.parent.mkdir();fake_modeler.write_bytes(b'fake modeler')
    def editor(exe,model,directory,macro):
        attempts.append('build');spec=read_json(directory/'spec.json')
        fake=saved(directory,spec,read_json(directory/'history-program.json'))
        assert Path(fake.path)==model
        nonce=re.search(r'Print #f, "([a-f0-9]{32})"',macro)[1]
        (directory/'completed.txt').write_text(nonce)
        return dict(exit_confirmed=True,exit_code=0)
    app.definition_editor=editor
    monkeypatch.setattr('csttool.definition_verifier.verify_capture_installation',lambda _:dict(version='2022',fake_only=True))
    def run(exe,model,directory,macro):
        attempts.append('verify');spec=read_json(model.parents[2]/'spec.json') if (model.parents[2]/'spec.json').exists() else run.spec
        nonce=re.search(r'Print #f, "nonce" & Chr\(9\) & "([a-f0-9]{32})"',macro)[1]
        identity=dict(nonce=nonce,project=str(model.with_suffix('')),build='Version 2022.5',length='mm',frequency='MHz',end='G03V1')
        if 'simulation' in spec:
            identity.update(solver='HF Eigenmode',mesh='Tetrahedral',fmin=str(spec['simulation']['frequency_range_mhz']['min']),fmax=str(spec['simulation']['frequency_range_mhz']['max']))
        (directory/'identity.tsv').write_text('\n'.join(k+'\t'+v for k,v in identity.items()))
        objects=geometry_objects(spec);live=[o for o in objects if o['state']=='live']
        facts=dict(nonce=nonce,project=str(model.with_suffix('')),count=str(len(live)),end='GEO1')
        for a in 'xyz':
            for i,side,op in ((0,'min',min),(1,'max',max)):
                value=op((o['bounds_mm'][a][i] for o in live),default=0)
                for kind in ('bounds','calculation'):facts[kind+'.'+a+side]=str(value)
        for i,o in enumerate(objects):
            prefix='solid.'+str(i)+'.';facts[prefix+'name']=o['native_name'];facts[prefix+'exists']=str(o['state']=='live')
            if o['state']=='live':facts.update({prefix+'material':o['material_id'],prefix+'solid':'True',prefix+'hybrid':'False',prefix+'volume_mm3':str(o['volume_mm3'])})
        (directory/'geometry.tsv').write_text('\n'.join(k+'\t'+v for k,v in facts.items()))
        (directory/'completed.txt').write_text(nonce)
        return dict(exit_confirmed=True,exit_code=0)
    app.definition_verifier=NativeDefinitionVerifier(runner=run)
    app.worker_factory=FakeWorker
    empty=app.create_project(payload(),operation_id='create')
    model=edit_document(app,request(empty,'apply_model_changes',geometry_profile='geometry-v1',changes=[dict(op='set_parameters',values=specimen()['parameters']),
        dict(op='ensure_component',component_id='vacuum'),dict(op='create_brick',object_id='body',component_id='vacuum',material_id='Vacuum',
            bounds_mm=dict(x=['-R','R'],y=['-R','R'],z=['-H/2','H/2']))]),operation_id='model')
    run.spec=model['spec']
    return app,model,attempts,run


def test_geometry_save_close_and_reconcile_never_grants_simulation_readiness(tmp_path,monkeypatch):
    app,model,attempts,run=geometry_service(tmp_path,monkeypatch)
    published=edit_document(app,request(model,'save_project',validation_target='geometry'),operation_id='save')
    assert published['geometry_saved'] and not published['ready'] and published['definition_revision'] is None
    assert attempts==['build','verify','verify']
    assert app.inspect_model(published['document_id'],published['document_revision'])==published
    assert reconcile_edit(app,'save')==published and attempts==['build','verify','verify']
    closed=edit_document(app,request(published,'close_project',disposition='save'),operation_id='close')
    assert closed['geometry_saved'] and not closed['ready'] and closed['state']=='closed'
    assert app.inspect_model(closed['document_id'],closed['document_revision'])==closed


def test_geo_simulation_uses_same_worker_capture_adoption_and_export(tmp_path,monkeypatch):
    FakeWorker.calls=0;FakeWorker.stop_error=False;FakeWorker.metrics=(500.,1.2);FakeWorker.capture_bad=False
    app,model,attempts,run=geometry_service(tmp_path,monkeypatch)
    model=edit_document(app,request(model,'apply_model_changes',geometry_profile='geometry-v1',changes=[dict(op='set_background',material='PEC',padding_mm=[0]*6),
        dict(op='set_boundaries',faces=['electric']*6,symmetry=['none']*3)]),operation_id='settings')
    model=edit_document(app,request(model,'configure_simulation',**configuration()),operation_id='config')
    run.spec=model['spec']
    published=edit_document(app,request(model,'save_project',validation_target='simulation'),operation_id='save')
    assert published['geometry_saved'] and published['ready'] and published['definition_revision']
    assert app.inspect_model(published['document_id'],published['document_revision'])==published
    command=dict(kind='simulation',document_id=published['document_id'],definition_revision=published['definition_revision'])
    execution=app.execute_simulation(command,run_id='solve',stop=StopIntent(),update=lambda **kw:None)
    execution.run(command)
    result=app.get_simulation_results('solve')
    assert FakeWorker.calls==1 and result['status']=='success'
    assert {m['method_id'] for m in result['metrics']}=={'Frequency','R_over_Q'}
    with pytest.raises(ValueError,match='RUN_RECONCILIATION_REQUIRED'):execution.run(command)
    assert FakeWorker.calls==1


@pytest.mark.parametrize('fault',['history','close','observation','response'])
def test_geo_failed_candidate_never_changes_current_or_reexecutes(tmp_path,monkeypatch,fault):
    app,model,attempts,run=geometry_service(tmp_path,monkeypatch)
    editor=app.definition_editor
    def broken(exe,path,directory,macro):
        result=editor(exe,path,directory,macro)
        if fault=='history':path.write_bytes(b'not a CST container')
        if fault=='close':result['exit_confirmed']=False
        if fault=='response':raise TimeoutError('lost response after save')
        return result
    app.definition_editor=broken
    if fault=='observation':
        def bad(*args,**kwargs):raise ValueError('wrong native object/count')
        monkeypatch.setattr(app.definition_verifier,'verify_geometry',bad)
    pointer=tmp_path/'control/documents'/model['document_id']/'current.json';before=pointer.read_bytes()
    command=request(model,'save_project',validation_target='geometry')
    with pytest.raises((ValueError,OSError)):edit_document(app,command,operation_id='failed')
    assert pointer.read_bytes()==before and attempts.count('build')==1
    with pytest.raises(ValueError,match='RUN_RECONCILIATION_REQUIRED'):edit_document(app,command,operation_id='failed')
    assert attempts.count('build')==1


def test_real_sdk_dispatches_geo_profile_and_target_without_signature_gap(tmp_path):
    pytest.importorskip('mcp')
    from mcp import Client
    from csttool.mcp_server import create_server,MCPApplicationAdapter
    from test.mcp_application_adapter_test import Client as FakeClient
    async def run():
        adapter=MCPApplicationAdapter(tmp_path,client_factory=FakeClient)
        handle=adapter.connect_project('caller')['control_handle'];FakeClient.calls=[]
        async with Client(create_server(tmp_path,adapter=adapter),mode='2026-07-28') as client:
            result=await client.call_tool('apply_model_changes',dict(control_handle=handle,document_id='doc',expected_document_revision='a'*64,
                geometry_profile='geometry-v1',changes=[dict(op='ensure_component',component_id='vacuum')],request_id='edit'))
            assert not result.is_error
            assert FakeClient.calls[-1][0][1]['geometry_profile']=='geometry-v1'
            result=await client.call_tool('save_project',dict(control_handle=handle,document_id='doc',expected_document_revision='a'*64,
                validation_target='geometry',request_id='save'))
            assert not result.is_error and FakeClient.calls[-1][0][1]['validation_target']=='geometry'
    asyncio.run(run())


def test_geometry_verification_holds_project_lock_and_reports_its_phase(tmp_path,monkeypatch):
    from csttool.project_run_lock import ProjectRunLock
    app,model,attempts,run=geometry_service(tmp_path,monkeypatch);original=app.definition_verifier.verify_geometry;events=[]
    def observe(*args,**kwargs):
        lock=ProjectRunLock(app.project)
        with pytest.raises(RuntimeError):lock.acquire()
        return original(*args,**kwargs)
    monkeypatch.setattr(app.definition_verifier,'verify_geometry',observe)
    record=edit_document(app,request(model,'save_project',validation_target='geometry'),operation_id='save',progress=events.append)
    assert record['geometry_saved'] and any(e['stage']=='geometry-verify' for e in events)


def test_raw_probe_scope_is_local_but_service_checks_its_whole_catalog(tmp_path,monkeypatch):
    app,model,attempts,run=geometry_service(tmp_path,monkeypatch)
    unknown=app.catalog/'unrelated'/'operation'/'verification-edit'/'saved'/'verification-managed-x'/'saved'/'session-status.json'
    write_json_atomic(unknown,dict(exit_confirmed=False))
    raw=tmp_path/'isolated-probe';raw.mkdir();source=saved(raw,model['spec'])
    proof=app.definition_verifier.verify_geometry(source.path,model['spec'],app.installations['local'])
    assert proof['status']=='verified' and attempts==['verify','verify']
    before=list(attempts)
    with pytest.raises(ValueError,match='exit unconfirmed'):
        edit_document(app,request(model,'save_project',validation_target='geometry'),operation_id='blocked')
    assert attempts==before and not (app.project/'control/runs/blocked/definition-intent.json').exists()
