from pathlib import Path
import pytest
from csttool.configuration import write_json_atomic,read_json
from csttool.managed_cstworker import ManagedCSTWorker
from test.managed_cstworker_test import build_worker_shell
from test.cstmanager_test import FakeGlobalConfig,FakeProjectConfig
from csttool.cstmanager import CSTManager


def options():
    return {'geometry_id':'fixed-cavity','sampling':{'bounds_m':[0,1,0,1,0,1],
            'counts':[2,2,2],'scope':'specified-domain'},'modes':[1]}


def test_manager_opt_in_preflights_and_propagates_without_changing_mode_count(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr('csttool.vacuum_domain_registry.register_vacuum_domain',
        lambda *args,**kwargs: calls.append(args) or {'status':'registered'})
    configs=[]
    class Worker:
        def stop(self): return True
    manager=CSTManager(FakeGlobalConfig(tmp_path),FakeProjectConfig(tmp_path),[],maxTask=1,
        worker_factory=lambda wid,config,log: configs.append(config) or Worker(),vacuum_domain=options())
    try:
        assert len(calls)==1
        assert configs[0].vacuum_domain==options()
        assert configs[0].postprocess[0]['method']=='ExportModeField'
        assert configs[0].postprocess[0]['params']['iModeNumber']==1
    finally: manager.stop()


def test_manager_rejects_concurrent_optional_registration_before_start(tmp_path):
    with pytest.raises(ValueError,match='one Worker'):
        CSTManager(FakeGlobalConfig(tmp_path),FakeProjectConfig(tmp_path),[],maxTask=2,
            worker_factory=lambda *args:pytest.fail('must not start'),vacuum_domain=options())


def test_deferred_registration_is_idempotent_and_preserves_success_on_failure(tmp_path,monkeypatch):
    worker=build_worker_shell(tmp_path)
    worker._vacuum_domain=options()
    from types import SimpleNamespace
    worker._process=SimpleNamespace(poll=lambda:0)
    worker.session_id='test'
    worker.protocol=SimpleNamespace(read_stop_ack=lambda *args:object())
    worker.executable=Path('cst.exe')
    worker.run_store=None
    directory=tmp_path/'archive';directory.mkdir()
    snapshot=directory/'model.cst';snapshot.write_bytes(b'saved successful model')
    worker._domain_jobs=[('task',snapshot,directory,[])]
    calls=[]
    def failed(*args,**kwargs):
        calls.append(args)
        raise ValueError('open boundary')
    monkeypatch.setattr('csttool.vacuum_domain_registry.register_vacuum_domain',failed)
    worker._finish_domain_registration()
    worker._finish_domain_registration()
    assert len(calls)==1 and snapshot.read_bytes()==b'saved successful model'
    assert read_json(directory/'vacuum-domain-error.json')['solver_replayed'] is False


def test_registration_refuses_live_or_unconfirmed_process(tmp_path):
    from types import SimpleNamespace
    worker=build_worker_shell(tmp_path)
    worker._vacuum_domain=options()
    worker.session_id='test'
    worker.protocol=SimpleNamespace(read_stop_ack=lambda *args:None)
    worker._process=SimpleNamespace(poll=lambda:None)
    with pytest.raises(RuntimeError,match='stopped'): worker._finish_domain_registration()
    worker._process=SimpleNamespace(poll=lambda:0)
    with pytest.raises(RuntimeError,match='StopAck'): worker._finish_domain_registration()


def test_backend_optional_options_reach_manager_and_single_worker_guard(tmp_path):
    from test.application_backend_test import make_backend
    backend,_,project,_,calls=make_backend()
    path=tmp_path/'domain.json';write_json_atomic(path,options())
    project.currProjectDir=tmp_path;project.ready=True
    backend.alg.set_editable_attributes({'vacuum_domain_enabled':True,'vacuum_domain_config':str(path)})
    backend.worker_count=1
    backend._create_manager()
    assert calls[0]['vacuum_domain']==options()
    backend.jm=None;backend.worker_count=2
    with pytest.raises(Exception,match='一个Worker'): backend._create_manager()
