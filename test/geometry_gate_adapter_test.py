"""Independent GEO gate and existing GUI/CLI adapter boundaries, all offline."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from csttool import winwrap_checks as checks
from csttool.configuration import write_json_atomic
from csttool.winwrap_emitter import GeneratedCodeError
from test.definition_editing_test import request


def synthetic_gate(root,targets):
    sources={'synthetic-fixture-only':'a'*64}
    evidence=dict(sources=sources,cases={k:dict(status='verified',synthetic_only=True) for k in ('C1','C2','C3','C4','C5','C6','C7','GEO-4')})
    path='knowledge-base/geometry-calibration-20261104.json'
    write_json_atomic(root/path,evidence)
    digest=hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    record=dict(profile=checks.GEO_NATIVE_PROFILE,accepted=True,sources=sources,targets=targets,evidence_file=path,evidence_sha256=digest)
    write_json_atomic(root/'data/geometry-calibration.json',record)
    return sources,record,evidence


@pytest.mark.parametrize('fault',[None,'missing','a1-profile','stale','evidence','incomplete','not-object','bad-targets','hot-edit'])
def test_geo_gate_binds_target_complete_matrix_and_current_source(tmp_path,monkeypatch,fault):
    sources,record,evidence=synthetic_gate(tmp_path,['geometry','simulation'])
    monkeypatch.setattr(checks,'ROOT',tmp_path);monkeypatch.setattr(checks,'LOADED_SOURCES',sources)
    monkeypatch.setattr(checks,'generator_fingerprint',lambda:sources)
    if fault=='missing':(tmp_path/'data/geometry-calibration.json').unlink()
    elif fault=='a1-profile':record['profile']=checks.PROFILE
    elif fault=='stale':record['sources']={}
    elif fault=='evidence':record['evidence_sha256']='wrong'
    elif fault=='incomplete':
        evidence['cases']['C7']['status']='pending';write_json_atomic(tmp_path/record['evidence_file'],evidence)
        record['evidence_sha256']=hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    elif fault=='not-object':record=[]
    elif fault=='bad-targets':record['targets']='geometry simulation'
    elif fault=='hot-edit':monkeypatch.setattr(checks,'LOADED_SOURCES',{})
    if fault!='missing':write_json_atomic(tmp_path/'data/geometry-calibration.json',record)
    if fault:
        with pytest.raises(GeneratedCodeError):checks.require_geometry_calibration('geometry')
    else:
        assert checks.require_geometry_calibration('geometry')==record
        assert checks.require_geometry_calibration('simulation')==record


def test_geometry_only_evidence_never_authorizes_simulation(tmp_path,monkeypatch):
    sources,record,evidence=synthetic_gate(tmp_path,['geometry'])
    monkeypatch.setattr(checks,'ROOT',tmp_path);monkeypatch.setattr(checks,'LOADED_SOURCES',sources)
    monkeypatch.setattr(checks,'generator_fingerprint',lambda:sources)
    checks.require_geometry_calibration('geometry')
    with pytest.raises(GeneratedCodeError):checks.require_geometry_calibration('simulation')


def test_gui_definition_adapter_validates_and_copies_into_existing_command_slot():
    from GUI.runner_controller import RunnerController
    captured=[];port=SimpleNamespace(_command=lambda op,payload:captured.append((op,payload)) or True)
    payload=dict(kind='definition',operation='apply_model_changes',document_id='doc',expected_document_revision='a'*64,
                 geometry_profile='geometry-v1',changes=[dict(op='ensure_component',component_id='vacuum')])
    assert RunnerController.submit_definition(port,payload)
    payload['changes'][0]['component_id']='changed-after-submit'
    assert captured[0][0]=='start' and captured[0][1]['changes'][0]['component_id']=='vacuum'
    invalid={**payload,'arbitrary_vba':'MsgBox "bad"'}
    with pytest.raises(ValueError):RunnerController.submit_definition(port,invalid)
    assert len(captured)==1


@pytest.mark.parametrize('operation',['apply_model_changes','save_project'])
def test_existing_cli_start_forwards_same_definition_contract(tmp_path,monkeypatch,capsys,operation):
    from csttool import runner_client
    model=dict(document_id='doc',document_revision='a'*64)
    payload=request(model,operation,**(dict(geometry_profile='geometry-v1',changes=[dict(op='ensure_component',component_id='vacuum')])
        if operation=='apply_model_changes' else dict(validation_target='geometry')))
    config=tmp_path/'definition.json';write_json_atomic(config,payload);calls=[]
    class Client:
        def __init__(self,*args):pass
        def connect(self,**kw):return dict(run_id=None)
        def command(self,*args,**kw):calls.append((args,kw));return dict(accepted=True)
    monkeypatch.setattr(runner_client,'RunnerClient',Client)
    monkeypatch.setattr('sys.argv',['runner_client','--project',str(tmp_path),'start','--config',str(config)])
    runner_client.main()
    assert calls[1][0]==('start',payload) and calls[0][0]==('claim',) and calls[-1][0]==('release',)
    assert 'accepted' in capsys.readouterr().out
