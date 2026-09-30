import json
import threading
from pathlib import Path

from csttool.diagnostics import write_run_manifest
from csttool.worker_models import WorkerConfig, SimulationResult


def test_manifest_excludes_callback_without_copying_owner(tmp_path):
    class Listener:
        def __init__(self):
            self.lock = threading.Lock()

        def progress(self, event):
            pass

    config = WorkerConfig(tmp_path, tmp_path, Path('cst.exe'), Path('model.cst'),
                          ({'name': 'R', 'value': '100'},),
                          progress_callback=Listener().progress)
    destination = write_run_manifest(tmp_path / 'diagnostics.json', config,
                                     {'completion': tmp_path / 'completion.txt'})
    document = json.loads(destination.read_text(encoding='utf-8'))
    assert document['schema_version'] == 1
    assert 'progress_callback' not in document['config']
    assert document['config']['parameters'][0]['name'] == 'R'
    assert len(document['source_sha256']['csttool/managed_cstworker.py']) == 64


def test_result_serialization_keeps_algorithm_contract(tmp_path):
    result = SimulationResult('1', 'Success', 'job', {'R': 100}, [],
                              snapshot=tmp_path / 'snapshot.cst')
    assert dict(result) == result.to_mapping()
    assert result['RunParameters'] == {'R': 100}
    assert result['ProjectSnapshot'] == str(tmp_path / 'snapshot.cst')
