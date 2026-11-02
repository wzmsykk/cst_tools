from copy import deepcopy
import json
from pathlib import Path

import pytest

from csttool.configuration import write_json_atomic
from csttool.execution_snapshot import BUILD,ExecutionConfig
from csttool.native_execution_capture import KEYS,NATIVE_VERSION,render_capture_runtime
from csttool.run_store import RunStore


def prepare_case(tmp_path):
    source = tmp_path/'source.cst';source.write_bytes(b'frozen synthetic definition')
    model = tmp_path/'work/input.cst';model.parent.mkdir();model.write_bytes(source.read_bytes())
    store = RunStore(tmp_path,tmp_path/'logs/run',run_id='run-a')
    executable=tmp_path/'install/CST.exe';executable.parent.mkdir();executable.write_bytes(b'synthetic launcher')
    modeler=executable.parent/'AMD64/modeler_AMD64.exe';modeler.parent.mkdir();modeler.write_bytes(b'synthetic modeler')
    kwargs = dict(definition_path=source,model_path=model,project_id='project-a',
                  config=ExecutionConfig('Default','Tet',True,'480',False,1),setup_history=['approved setup'],executable=executable)
    intent = store.prepare_execution_attempt('task-a',**kwargs)
    return store,intent,kwargs


def frames(store,intent,*,pre_missing=True,solver_return='1'):
    directory=store.project/'observations';directory.mkdir(exist_ok=True)
    metadata=dict(format='CSTEXEC1',nonce=intent['nonce'],project=str(Path(intent['model_path']).with_suffix('')),
                  build=NATIVE_VERSION,solver='HF Eigenmode',length='mm',frequency='MHz')
    values=dict(SolverTypeTet='OK:1',FrequencyTargetActive='OK:True',FrequencyTargetValue='OK:480',
                AdaptionActiveTet='OK:False',Modes='OK:1',MeshType='OK:1')
    for phase in ('pre','started','post'):
        record=dict(metadata,phase=phase)
        if phase=='pre':record.update({key:'MISSING' if pre_missing else values[key] for key in KEYS})
        if phase=='post':record.update(values,solver_return=solver_return,calculated_modes='1' if solver_return=='1' else '0')
        record['end']='CSTEXEC1'
        (directory/('native-'+phase+'.tsv')).write_text(''.join(key+'\t'+value+'\n' for key,value in record.items()),encoding='utf-8')
    model=Path(intent['model_path']);db=model.with_suffix('')/'Result/Model.db'
    db.parent.mkdir(parents=True,exist_ok=True);db.write_bytes(b'synthetic database')
    closure=dict(exit_confirmed=True,active_pids=[],owned=[dict(pid=123,create_time=1)],
                 task_project=str(model),exit_code=0 if solver_return=='1' else 1)
    return directory,closure


def test_freeze_idempotence_and_conflicting_definition(tmp_path):
    store,intent,kwargs=prepare_case(tmp_path)
    assert store.prepare_execution_attempt('task-a',**kwargs)==intent
    with pytest.raises(ValueError,match='conflicts'):
        store.prepare_execution_attempt('task-a',**{**kwargs,'config':ExecutionConfig('Default','Tet',True,'600',False,1)})
    assert json.loads((store.directory/'tasks/task-a/execution/intent.json').read_text())==intent


def test_reconcile_is_idempotent_and_repairs_missing_artifact_index(tmp_path):
    store,intent,_=prepare_case(tmp_path);directory,closure=frames(store,intent)
    receipt=store.finalize_execution_attempt('task-a',observations=directory,closure=closure)
    assert receipt['status']=='execution-snapshot-match' and receipt['result_success'] is True
    assert not receipt['publish_ready']
    (store.directory/'tasks/task-a/artifacts.json').unlink()
    assert store.finalize_execution_attempt('task-a',observations=directory,closure=closure)==receipt
    assert (store.directory/'tasks/task-a/artifacts.json').is_file()
    assert json.loads((store.directory/'tasks/task-a/attempt.json').read_text())['event']=='submitted'
    assert len((store.directory/'events.jsonl').read_text().splitlines())==1


def test_failure_config_matching_does_not_make_failed_exit_standard_success(tmp_path):
    store,intent,_=prepare_case(tmp_path);directory,closure=frames(store,intent,solver_return='0')
    receipt=store.finalize_execution_attempt('task-a',observations=directory,closure=closure)
    assert receipt['status']=='execution-snapshot-match'
    assert receipt['result_success'] is False and receipt['process_exit_code']==1
    assert receipt['batch_exit_zero'] is False


@pytest.mark.parametrize('which,replacement', [('nonce','0'*32),('project','other-project'),
                                             ('build','other-build'),('solver','HF Frequency Domain'),
                                             ('length','cm'),('frequency','GHz')])
def test_native_identity_mismatch_cannot_be_relabelled(tmp_path,which,replacement):
    store,intent,_=prepare_case(tmp_path);directory,closure=frames(store,intent)
    path=directory/'native-post.tsv'
    rows=dict(line.split('\t',1) for line in path.read_text().splitlines());rows[which]=replacement
    path.write_text(''.join(k+'\t'+v+'\n' for k,v in rows.items()))
    with pytest.raises(ValueError):
        store.finalize_execution_attempt('task-a',observations=directory,closure=closure)
    assert not (store.directory/'tasks/task-a/execution/receipt.json').exists()


def test_existing_database_and_incomplete_stage_refuse_adoption(tmp_path):
    store,intent,_=prepare_case(tmp_path);directory,closure=frames(store,intent,pre_missing=False)
    with pytest.raises(ValueError,match='preexisting database'):
        store.finalize_execution_attempt('task-a',observations=directory,closure=closure)
    frames(store,intent,pre_missing=True)
    (directory/'native-started.tsv').unlink()
    with pytest.raises(FileNotFoundError):
        store.finalize_execution_attempt('task-a',observations=directory,closure=closure)


def test_exit_unconfirmed_and_modified_receipt_are_not_overwritten(tmp_path):
    store,intent,_=prepare_case(tmp_path);directory,closure=frames(store,intent)
    with pytest.raises(ValueError,match='exit not confirmed'):
        store.finalize_execution_attempt('task-a',observations=directory,closure={**closure,'active_pids':[123]})
    store.finalize_execution_attempt('task-a',observations=directory,closure=closure)
    path=store.directory/'tasks/task-a/execution/receipt.json';record=json.loads(path.read_text())
    record['nonce']='wrong';write_json_atomic(path,record)
    with pytest.raises(ValueError,match='receipt conflict'):
        store.finalize_execution_attempt('task-a',observations=directory,closure=closure)


def test_runtime_only_collects_allowlisted_keys_without_launch_or_cleanup(tmp_path):
    _,intent,_=prepare_case(tmp_path)
    runtime=render_capture_runtime(intent,tmp_path/'observations')
    assert 'Sub Main' not in runtime and 'EigenmodeSolver.Start' not in runtime
    assert 'OpenFile' not in runtime and 'Quit' not in runtime and '\n    Save' not in runtime
    assert 'preexisting or unverified execution database; refuse Start' in runtime
    assert 'Err.Number = -2147418113' in runtime
    assert 'GetProjectPath("Project")' in runtime and 'GetApplicationVersion()' in runtime


def test_reconciliation_rejects_corrupt_snapshot_and_keeps_other_run_state(tmp_path):
    store,intent,_=prepare_case(tmp_path);directory,closure=frames(store,intent)
    store.finalize_execution_attempt('task-a',observations=directory,closure=closure)
    snapshot=store.directory/'tasks/task-a/execution/snapshot.json'
    value=json.loads(snapshot.read_text());value['values']['FrequencyTargetValue']='600'
    write_json_atomic(snapshot,value)
    with pytest.raises(ValueError,match='snapshot evidence conflict'):
        store.finalize_execution_attempt('task-a',observations=directory,closure=closure)
    assert json.loads((store.directory/'tasks/task-a/attempt.json').read_text())['event']=='submitted'


def test_fresh_copy_hash_and_intent_budget_are_checked_before_launch(tmp_path):
    store,intent,kwargs=prepare_case(tmp_path)
    Path(intent['model_path']).write_bytes(b'unrelated model')
    with pytest.raises(ValueError,match='fresh model'):
        store.prepare_execution_attempt('other-task',**kwargs)
    Path(intent['model_path']).write_bytes(Path(intent['definition_path']).read_bytes())
    with pytest.raises(ValueError,match='bounded owner setup'):
        store.prepare_execution_attempt('other-task',**{**kwargs,'setup_history':['a'*4096]*9})


def test_report_publication_gap_can_be_reconciled_without_solver(tmp_path,monkeypatch):
    import csttool.native_execution_capture as module
    store,intent,_=prepare_case(tmp_path);directory,closure=frames(store,intent)
    original=module.write_json_atomic
    def fail_receipt(path,value):
        if Path(path).name=='receipt.json':raise OSError('injected publication interruption')
        return original(path,value)
    monkeypatch.setattr(module,'write_json_atomic',fail_receipt)
    with pytest.raises(OSError,match='publication interruption'):
        store.finalize_execution_attempt('task-a',observations=directory,closure=closure)
    assert (store.directory/'tasks/task-a/execution/snapshot.json').is_file()
    monkeypatch.setattr(module,'write_json_atomic',original)
    receipt=store.finalize_execution_attempt('task-a',observations=directory,closure=closure)
    assert receipt['status']=='execution-snapshot-match'
    assert store.finalize_execution_attempt('task-a',observations=directory,closure=closure)==receipt


def test_installation_fingerprint_is_diagnostic_but_mid_attempt_change_is_rejected(tmp_path):
    store,intent,kwargs=prepare_case(tmp_path)
    # An unknown binary fingerprint is accepted before capture under 2022 policy.
    assert intent['installation']['modeler_sha256']
    directory,closure=frames(store,intent)
    modeler=Path(kwargs['executable']).parent/'AMD64/modeler_AMD64.exe'
    modeler.write_bytes(b'another patch installed after the attempt was frozen')
    with pytest.raises(ValueError,match='installation identity changed'):
        store.finalize_execution_attempt('task-a',observations=directory,closure=closure)
