import json
import pytest
from csttool.result_reconciliation import file_hash, find_received_result


def test_reconciliation_requires_closed_session_and_exact_definition(tmp_path):
    workspace = tmp_path / 'session'
    received = workspace / 'received'
    received.mkdir(parents=True)
    snapshot = tmp_path / 'model.cst'
    snapshot.write_bytes(b'confirmed')
    receipt = dict(phase='received', status='Success', job='hom', parameters={'nmodes': 1},
                   execution_fingerprint='definition', workspace=str(workspace),
                   snapshot=str(snapshot), snapshot_sha256=file_hash(snapshot), postprocess=[])
    path = received / 'task.json'
    path.write_text(json.dumps(receipt))
    assert find_received_result([tmp_path], 'hom', {'nmodes': 1}, 'definition') is None
    (workspace / 'recovery.json').write_text('{"disposition":"standard-stop"}')
    assert find_received_result([tmp_path], 'hom', {'nmodes': 1}, 'definition')[0] == path
    supplementary = workspace / 'recovery-l1.json'
    supplementary.write_text(json.dumps(dict(schema_version=1, session_id='session', disposition='abandoned-dead')))
    assert find_received_result([tmp_path], 'hom', {'nmodes': 1}, 'definition')[0] == path
    supplementary.write_text(json.dumps(dict(schema_version=1, session_id='other-session', disposition='abandoned-dead')))
    with pytest.raises(ValueError, match='identity mismatch'):
        find_received_result([tmp_path], 'hom', {'nmodes': 1}, 'definition')
    supplementary.unlink()
    assert find_received_result([tmp_path], 'hom', {'nmodes': 1}, 'changed') is None
    snapshot.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='changed'):
        find_received_result([tmp_path], 'hom', {'nmodes': 1}, 'definition')
