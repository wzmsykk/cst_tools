from pathlib import Path
import pytest
from csttool import batch_desktop as module
from csttool.configuration import read_json


@pytest.mark.parametrize('value',['plain','a"b','中文路径'])
def test_shared_string_emission_preserves_existing_valid_rendering(value):
    from csttool.vb_codec import quote_vb_string
    assert module.literal_content(value)==quote_vb_string(value)


def test_shared_string_emission_rejects_control_characters():
    with pytest.raises(ValueError,match='control-free'):module.literal_content('bad\npath')


def test_macro_manifest_rejects_overlong_generated_lines_before_launch(tmp_path):
    source=tmp_path/'source.vb';source.write_text('source')
    with pytest.raises(ValueError,match='physical-line-budget'):
        module.macro_manifest(tmp_path,'x'*801,purpose='test',sources=[source])
    assert not (tmp_path/'generation-manifest.json').exists()
    module.macro_manifest(tmp_path,'Sub Main\nEnd Sub',purpose='test',sources=[source])
    assert read_json(tmp_path/'generation-manifest.json')['check']=='physical-lines-only'


def test_isolation_failure_never_falls_back_to_visible_launch(tmp_path,monkeypatch):
    calls=[]
    def fail():raise OSError('desktop unavailable')
    monkeypatch.setattr(module,'PrivateDesktop',fail)
    monkeypatch.setattr(module.subprocess,'Popen',lambda *a,**k:calls.append('unsafe fallback'))
    lease=module.BatchDesktopLease(tmp_path/'CST.exe',tmp_path/'a.cst',tmp_path)
    lease.isolate=True
    with pytest.raises(OSError,match='desktop unavailable'):lease.start(['fake'],None)
    assert calls==[]


def test_finish_releases_only_handles_never_terminates_process(tmp_path):
    class Desktop:
        name='test'
        def close(self):events.append('close desktop handle')
    class Observer:
        def __exit__(self,*args):events.append('stop observer')
        def report(self):return {}
    class Process:
        pid=123
        def kill(self):raise AssertionError('must never kill')
        def terminate(self):raise AssertionError('must never terminate')
    events=[];lease=module.BatchDesktopLease(tmp_path/'CST.exe',tmp_path/'a.cst',tmp_path)
    lease.desktop=Desktop();lease.observer=Observer();lease.process=Process()
    lease.finish()
    assert events==['stop observer','close desktop handle']
    assert read_json(tmp_path/'desktop-lease.json')['process_exit_not_implied']
