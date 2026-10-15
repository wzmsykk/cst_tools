"""Qt/real Manager flow with synthetic fields and explicitly fake native probes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from types import SimpleNamespace
from threading import RLock

import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QCloseEvent
from GUI.main_window import MainWindow
from GUI.run_controller import RunState
from csttool.cstmanager import CSTManager
from csttool.configuration import write_json_atomic,read_json
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.geometry_support import load_material_support
from csttool.physical_domain import common_quadrature
from csttool.result_reconciliation import file_hash
from test.gui_fake_worker_flow_test import (
    FakeWorkerGuiBackend,FlowFakeWorker,FakeGlobalConfig,FakeProjectConfig,FakeDialog,process_until,
)
from test.vacuum_mode_tracking_test import snapshot,descriptor,policy
from test.vacuum_domain_registry_test import inventory
from dataclasses import asdict


@pytest.fixture(scope='module')
def qapp(): return QApplication.instance() or QApplication([])


class MatchingFakeWorker(FlowFakeWorker):
    _finish_domain_registration=ManagedCSTWorker._finish_domain_registration
    _run_vacuum_matching=ManagedCSTWorker._run_vacuum_matching

    def __init__(self,wid,config,backend):
        super().__init__(wid,backend.tracker,backend.outcomes,backend.release)
        self.config=config;self.backend=backend;self.logger=backend.logger
        self._vacuum_domain=config.vacuum_domain
        self._vacuum_reference_store=config.vacuum_reference_store
        self._domain_jobs=[];self.run_store=None
        self._lifecycle_lock=RLock()
        self.executable=config.executable
        self.session_id=wid
        self.protocol=SimpleNamespace(read_stop_ack=lambda *args:object() if self.stopped else None)
        self._process=SimpleNamespace(poll=lambda:0 if self.stopped else None)
        self._stop_exit_is_confirmed=lambda:self.stopped

    def run_task(self,name,*,params):
        with self._lifecycle_lock:
            return self._run_synthetic_task(name,params=params)

    def _run_synthetic_task(self,name,*,params):
        result=super().run_task(name,params=params)
        if self._vacuum_domain is None or result['TaskStatus']!='Success': return result
        number=len(self.backend.archives)
        folder=self.backend.root/f'fake-archive-{number}';folder.mkdir()
        vector=(0,1,0) if self.backend.ambiguous and number==1 else (1,0,0)
        snap=snapshot(folder,name,[vector])
        desc=descriptor(folder,snap)
        fields=read_json(folder/desc['result_file'])['FieldArtifacts']
        for field in fields:
            field['value']['sampling_id']=snap.fields[0].sampling.identity
        project=folder/'model.cst';project.write_bytes(b'fake snapshot, not a CST model')
        self._domain_jobs.append((name,project,folder,fields))
        self.backend.archives.append(folder)
        return {**result,'DomainRegistration':{'status':'pending-after-stop',
            'matching_report':str(folder/'vacuum-mode-matching.json')}}

    def stop(self):
        self._release.set()
        with self._lifecycle_lock:
            assert self._tracker['active']==0
            self.stopped=True
            self._finish_domain_registration()


class MatchingFakeBackend(FakeWorkerGuiBackend):
    def __init__(self,root,*,ambiguous=False,recycle=False,reject=False,blocked=False):
        super().__init__(root,blocked=blocked)
        self.ambiguous=ambiguous;self.recycle=recycle;self.reject=reject
        self.archives=[];self.probes=[]

    def prepare_run(self):
        from csttool.vacuum_domain_registry import validate_managed_domain_options
        options=None
        if self.alg_attrs.get('vacuum_domain_enabled'):
            options=validate_managed_domain_options(read_json(self.alg_attrs['vacuum_domain_config']))
        def factory(wid,config,logger):
            worker=MatchingFakeWorker(wid,config,self);self.workers.append(worker);return worker
        self.manager=CSTManager(FakeGlobalConfig(self.root),FakeProjectConfig(self.root,self.pps),
            params=[],logger=self.logger,maxTask=self.worker_count,worker_factory=factory,
            vacuum_domain=options,max_jobs_per_worker=1 if self.recycle else 6)


def window_with_fake_matching(qapp,tmp_path,monkeypatch,**kwargs):
    monkeypatch.setattr("GUI.main_window.QMessageBox.question",lambda *a:16384)
    backend=MatchingFakeBackend(tmp_path,**kwargs)
    def fake_registration(executable,source,destination,sampling,*,geometry_id):
        assert backend.tracker['active']==0,'native probe must not run during fake solve'
        backend.probes.append(str(source))
        destination=Path(destination);destination.mkdir(parents=True)
        if backend.reject: return {'status':'rejected','rejection_reasons':['background-not-PEC']}
        inv=inventory(destination)
        mask=destination/'support.tsv';mask.write_text('Vacuum\n'*len(sampling.points()))
        support=load_material_support(sampling,mask,expected_sha256=file_hash(mask),geometry_id=geometry_id)
        result={'status':'registered','source_sha256':file_hash(source),'source_unchanged':True,
            'geometry_id':geometry_id,'sampling_id':sampling.identity,'support_file':'support.tsv',
            'support_sha256':file_hash(mask),'support_id':support.identity,
            'inventory_sha256':file_hash(inv),'quadrature':common_quadrature([support],['Vacuum']).to_mapping()}
        write_json_atomic(destination/'domain-registration.json',result)
        return result
    monkeypatch.setattr('csttool.vacuum_domain_registry.register_vacuum_domain',fake_registration)
    def forbidden(*args,**kwargs): pytest.fail('fake-worker flow must never launch a subprocess')
    monkeypatch.setattr('csttool.vacuum_domain_registry.subprocess.Popen',forbidden)
    window=MainWindow(backend,FakeDialog(),FakeDialog())
    model=tmp_path/'input.cst';model.write_bytes(b'fake project')
    monkeypatch.setattr('GUI.main_window.QFileDialog.getExistingDirectory',lambda *args,**kwargs:str(tmp_path))
    monkeypatch.setattr('GUI.main_window.QFileDialog.getOpenFileName',lambda *args,**kwargs:(str(model),True))
    window.selectProjectDirButton.click();window.selectCSTPathButton.click()
    config=tmp_path/'domain-options.json'
    write_json_atomic(config,{'geometry_id':'cavity-v1','sampling':{
        'bounds_m':[0,1,0,1,0,1],'counts':[2,2,2],'scope':'specified-domain'},'modes':[1],
        'matching':{'reference_strategy':'first-valid','policy':asdict(policy()),'sampling_evidence':'synthetic fixture only'}})
    # Use the same dialog signal -> service update entry as the GUI.
    window.CalcDialogBox.values.update(vacuum_domain_enabled=True,vacuum_domain_config=str(config))
    window.CalcDialogBox._signal_done.emit()
    return window,backend


@pytest.mark.parametrize('ambiguous,recycle',[(False,False),(True,False),(False,True)])
def test_gui_fake_matching_fixed_reference_and_recycling(qapp,tmp_path,monkeypatch,ambiguous,recycle):
    window,backend=window_with_fake_matching(qapp,tmp_path,monkeypatch,ambiguous=ambiguous,recycle=recycle)
    window.StartButton.click()
    process_until(qapp,lambda:not window.controller.has_active_work)
    assert window.controller.state is RunState.READY
    reports=[read_json(folder/'vacuum-mode-matching.json') for folder in backend.archives]
    assert [r['status'] for r in reports]==['reference-established','unconfirmed' if ambiguous else 'matched']
    assert len(backend.tracker['calls'])==2,'unconfirmed must not replay solver'
    assert len(backend.workers)==(2 if recycle else 1)
    assert all(w.stopped for w in backend.workers)
    assert '模式匹配结束' in window.logTextBox.widget.toPlainText()
    window.close()


def test_gui_fake_preflight_rejection_starts_no_workers(qapp,tmp_path,monkeypatch):
    window,backend=window_with_fake_matching(qapp,tmp_path,monkeypatch,reject=True)
    window.StartButton.click();process_until(qapp,lambda:not window.controller.has_active_work)
    assert window.controller.state is RunState.FAILED
    assert not backend.workers and not backend.tracker['calls']
    assert window.StartButton.isEnabled()
    window.close()


def test_gui_fake_disabled_option_has_no_probe_or_matching(qapp,tmp_path,monkeypatch):
    window,backend=window_with_fake_matching(qapp,tmp_path,monkeypatch)
    window.CalcDialogBox.values['vacuum_domain_enabled']=False
    window.CalcDialogBox._signal_done.emit()
    window.StartButton.click();process_until(qapp,lambda:not window.controller.has_active_work)
    assert window.controller.state is RunState.READY
    assert len(backend.tracker['calls'])==2
    assert not backend.probes and not backend.archives
    window.close()


def test_gui_fake_close_during_solve_finishes_before_registration(qapp,tmp_path,monkeypatch):
    window,backend=window_with_fake_matching(qapp,tmp_path,monkeypatch,blocked=True)
    window.StartButton.click();process_until(qapp,lambda:backend.tracker['active']>0)
    event=QCloseEvent();window.closeEvent(event)
    assert not event.isAccepted() and window.controller.state is RunState.STOPPING
    process_until(qapp,lambda:not window.controller.has_active_work)
    process_until(qapp,lambda:not window._close_pending)
    assert all(worker.stopped for worker in backend.workers)
    assert len(backend.tracker['calls'])==1
    assert read_json(backend.archives[0]/'vacuum-mode-matching.json')['status']=='reference-established'
