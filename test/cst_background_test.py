from pathlib import Path

from csttool.cst_background import BackgroundWindowObserver


class Backend:
    def __init__(self):
        self.rows=[]
        self.actions=[]
    def foreground(self):return dict(hwnd=9,pid=999)
    def windows(self):return self.rows
    def minimize(self,hwnd):self.actions.append(hwnd);return True


def make_observer(tmp_path):
    identities={10:dict(pid=10,create_time=1.0,name='modeler_AMD64.exe',path=str(tmp_path/'AMD64/modeler.exe'))}
    backend=Backend()
    observer=BackgroundWindowObserver(tmp_path,backend=backend,lookup=identities.get)
    return observer,backend,identities


def window(hwnd=1,**kwargs):
    return dict(hwnd=hwnd,pid=kwargs.get('pid',10),visible=True,minimized=False,
                owner=kwargs.get('owner',0),window_class=kwargs.get('window_class','CstMain'))


def test_no_actions_before_binding_and_no_foreign_or_dialog_actions(tmp_path):
    observer,backend,identities=make_observer(tmp_path)
    backend.rows=[window(),window(2,owner=1),window(3,window_class='#32770'),window(4,pid=999)]
    observer.sample()
    assert not backend.actions
    observer.bind([dict(pid=10,create_time=1.0)])
    observer.sample()
    assert backend.actions==[1]


def test_binding_checks_time_and_install_and_rechecks_pid_reuse(tmp_path):
    observer,backend,identities=make_observer(tmp_path)
    backend.rows=[window()]
    observer.bind([dict(pid=10,create_time=2.0)])
    observer.sample()
    assert not backend.actions
    observer.bind([dict(pid=10,create_time=1.0)])
    identities[10]=dict(identities[10],create_time=2.0)
    observer.sample()
    assert not backend.actions
    identities[10]=dict(identities[10],path=str(tmp_path.parent/'other/modeler.exe'))
    observer.bind([dict(pid=10,create_time=2.0)])
    observer.sample()
    assert not backend.actions


def test_foreground_events_before_binding_remain_failure_evidence(tmp_path):
    observer,backend,identities=make_observer(tmp_path)
    observer.record('foreground',window())
    assert observer.report()['owned_foreground_events']==0
    observer.bind([dict(pid=10,create_time=1.0)])
    assert observer.report()['owned_foreground_events']==1
    assert not backend.actions  # No attempt to steal the foreground back.


def test_observation_only_profile_never_minimizes_even_owned_windows(tmp_path):
    observer,backend,identities=make_observer(tmp_path)
    observer.minimize=False
    observer.bind([dict(pid=10,create_time=1.0)])
    backend.rows=[window()]
    observer.sample()
    assert observer.report()['owned_events']
    assert not backend.actions
