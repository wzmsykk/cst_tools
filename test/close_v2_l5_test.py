from pathlib import Path
from csttool.close_receipt import CloseReceipt, publish_close_receipt, read_close_receipt, declare_close_protocol
from csttool.runtime_protocol import new_session_id


def test_immutable_close_snapshot_survives_active_project_rewrite(tmp_path):
    sid = new_session_id()
    declare_close_protocol(tmp_path, sid, 'v2')
    snapshot = tmp_path / 'worker-input.cst.closed.cst'
    snapshot.write_bytes(b'saved-copy')
    active = tmp_path / 'worker-input.cst'
    active.write_bytes(b'active')
    receipt = CloseReceipt(sid, 'none', 'stop-request', 'not-started', 'saved', 'prepared',
                           'save', snapshot.name, snapshot.stat().st_size, 'none')
    publish_close_receipt(tmp_path, receipt)
    active.write_bytes(b'changed by batch shutdown')
    assert read_close_receipt(tmp_path, sid) == receipt
    snapshot.write_bytes(b'changed')
    import pytest
    with pytest.raises(ValueError, match='snapshot'):
        read_close_receipt(tmp_path, sid)


def test_production_saved_receipt_uses_backup_not_active_file():
    root = Path(__file__).parents[1]
    macro = (root / 'data/runtime_managed_worker_v1_main.vb').read_text()
    assert 'Backup "%PROJECT_PATH%.closed.cst"' in macro
    assert 'closeReceipt.SnapshotRef = "worker-input.cst.closed.cst"' in macro
    assert macro.index('    Save\n') < macro.index('Backup "%PROJECT_PATH%.closed.cst"')
    assert 'worker-input.cst.closed.cst' in (root / 'data/runtime_close_receipt_v2.vb').read_text()
