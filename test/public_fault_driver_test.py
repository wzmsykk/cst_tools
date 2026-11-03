"""Supervisor ordering/stop-on-unknown tests; no native process launch."""
from pathlib import Path
import pytest
from csttool.configuration import write_json_atomic, read_json
from test.support.validate_public_faults import supervise, ALL, PUBLIC


def test_plan_has_unique_ack_points_and_separate_controller_faults():
    assert len(ALL) == len(set(ALL)) == 15
    assert 'during-solver' in ALL and 'wrong-ack' in ALL
    assert PUBLIC == ('controller-before-publication', 'controller-before-adoption-receipt', 'solver-rejection')


@pytest.mark.parametrize('fault', ['nonzero', 'unclosed', 'source-changed', 'residual'])
def test_supervisor_preserves_report_and_never_starts_next_on_uncertain_exit(tmp_path, fault):
    source=tmp_path/'source.cst';source.write_bytes(b'fixture');exe=tmp_path/'CST.exe';exe.touch()
    calls=[]
    class Child:
        def wait(self):
            if fault == 'source-changed':source.write_bytes(b'changed')
            write_json_atomic(tmp_path/'before-parameters/report.json',dict(passed=True,
                close=dict(standard_closed=fault!='unclosed')))
            return 1 if fault == 'nonzero' else 0
    def launch(*args, **kwargs): calls.append(args);return Child()
    def processes(): return [{'pid':123}] if fault=='residual' and calls else []
    with pytest.raises(AssertionError):
        supervise(tmp_path,source,exe,['before-parameters','after-rebuild'],launch=launch,processes=processes)
    assert len(calls)==1
    assert read_json(tmp_path/'report.json')['passed'] is False
    assert read_json(tmp_path/'progress.json')['state']=='blocked'


def test_supervisor_does_not_launch_when_cst_already_running(tmp_path):
    source=tmp_path/'source.cst';source.touch()
    def launch(*args,**kwargs):raise AssertionError('must not launch')
    with pytest.raises(AssertionError,match='CST still active'):
        supervise(tmp_path,source,source,['before-parameters'],launch=launch,processes=lambda:[{'pid':123}])
    assert read_json(tmp_path/'report.json')['cases']==[]


def test_successful_supervision_is_serial_and_retains_all_case_reports(tmp_path):
    source=tmp_path/'source.cst';source.write_bytes(b'fixture')
    order=[]
    class Child:
        def __init__(self,case):self.case=case
        def wait(self):
            order.append(self.case)
            write_json_atomic(tmp_path/self.case/'report.json',dict(passed=True,close=dict(standard_closed=True)))
            return 0
    def launch(args,**kwargs):return Child(args[args.index('--child')+1])
    result=supervise(tmp_path,source,source,['before-parameters','after-rebuild'],
        launch=launch,processes=lambda:[],keep_raw=True)
    assert result['passed'] and order==['before-parameters','after-rebuild']
    assert len(result['cases'])==2


def test_cleanup_removes_only_companion_and_keeps_parameters_macro_and_source(tmp_path,monkeypatch):
    from test.support import validate_public_faults as module
    from test.saved_project_source_test import container
    monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.setattr(module,'cst_processes',lambda:[])
    monkeypatch.setattr(module.subprocess,'check_output',lambda *a,**kw:'')
    root=tmp_path/'artifacts/case';root.mkdir(parents=True)
    source=tmp_path/'original.cst';source.write_bytes(b'original')
    model=root/'copy.cst';model.write_bytes(container([('Model/Parameters.json',b'{"parameters":[]}')]))
    result=root/'copy/Result';result.mkdir(parents=True);(result/'field.bin').write_bytes(b'raw')
    (root/'macro.bas').write_text('retained')
    assert module.cleanup_case(root,source)==1
    assert not result.exists() and model.exists() and source.read_bytes()==b'original'
    assert (root/'macro.bas').exists() and (root/'copy.cst.members/Model/Parameters.json').exists()


def test_default_cli_is_plan_only_without_source_or_native_launch(monkeypatch,capsys):
    from test.support import validate_public_faults as module
    monkeypatch.setattr(module.sys,'argv',['validate_public_faults.py'])
    def forbidden(*args,**kwargs):raise AssertionError('plan must not acquire native probe')
    monkeypatch.setattr(module,'exclusive_probe',forbidden)
    module.main()
    assert 'PLAN ONLY' in capsys.readouterr().out


@pytest.mark.parametrize('field',['parent_pid','case','source_sha256','executable'])
def test_child_rejects_foreign_parent_intent_before_any_native_call(tmp_path,monkeypatch,field):
    from test.support import validate_public_faults as module
    source=tmp_path/'source.cst';source.write_bytes(b'fixture')
    root=tmp_path/'artifacts/case';root.mkdir(parents=True)
    owner=dict(parent_pid=module.os.getppid(),case='before-parameters',source_sha256=module.digest(source),executable=str(source))
    owner[field]=-1 if field=='parent_pid' else 'foreign'
    write_json_atomic(root/'parent-intent.json',owner)
    monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.setattr(module.sys,'argv',['probe','--run-cst','--source',str(source),'--cst-exe',str(source),
        '--child','before-parameters','--root',str(root)])
    def forbidden(*args,**kwargs):raise AssertionError('foreign child must not start CST')
    monkeypatch.setattr(module,'run_timing',forbidden)
    with pytest.raises(SystemExit) as error:module.main()
    assert error.value.code==2
