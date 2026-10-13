import subprocess

import pytest

from csttool import saved_field_export as exporter
from csttool.configuration import read_json


def setup_export(tmp_path, monkeypatch, available=True):
    source = tmp_path/'source.cst'
    source.write_bytes(b'original')
    directory = tmp_path/'export'
    directory.mkdir()
    processor = type('Processor', (), {'read_all_results':lambda self:[
        {'value':{'status':'available' if available else 'unavailable'}}]})()
    monkeypatch.setattr(exporter, 'prepare_saved_field_export', lambda *args:(directory/'export.bas', processor))
    process = type('Process', (), {'returncode':0, 'poll':lambda self:0})()
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs:process)
    def wait(*args):
        (directory/'completed.txt').write_text('SUCCESS')
        return {'exit_confirmed':True, 'foreign_processes':[]}
    monkeypatch.setattr(exporter, 'wait_probe', wait)
    return source, directory


@pytest.mark.parametrize('available,expected', [(True,'complete'), (False,'incomplete')])
def test_artifact_status_required(tmp_path, monkeypatch, available, expected):
    source, directory = setup_export(tmp_path, monkeypatch, available)
    result = exporter._export_saved_fields('cst.exe', source, directory, [])
    assert result['status'] == expected


def test_failed_marker_overrides_success(tmp_path, monkeypatch):
    source, directory = setup_export(tmp_path, monkeypatch)
    (directory/'failed.txt').write_text('failure')
    assert exporter._export_saved_fields('cst.exe',source,directory,[])['status']=='incomplete'


def test_stalled_session_persists_failure(tmp_path, monkeypatch):
    source, directory = setup_export(tmp_path, monkeypatch)
    def stall(*args):
        raise RuntimeError('exit-unconfirmed')
    monkeypatch.setattr(exporter,'wait_probe',stall)
    with pytest.raises(RuntimeError,match='exit-unconfirmed'):
        exporter._export_saved_fields('cst.exe',source,directory,[])
    result=read_json(directory/'export-result.json')
    assert result['status']=='incomplete'
    assert result['PostProcessResult']==[]
