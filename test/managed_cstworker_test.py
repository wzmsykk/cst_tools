import logging
from pathlib import Path
import os
import threading
import json
from pathlib import Path

import pytest

from csttool.configuration import CstBackendSettings, GlobalSettings, ProjectSettings
from csttool.cstmanager import CSTManager, ManagerState
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.managed_cstworker import ManagedWorkerShutdownError
from csttool.postprocess_cst import CstPostProcessor
from csttool.runtime_protocol import Task
from csttool.runtime_protocol import Completion, CompletionStatus
from csttool.runtime_protocol import encode_completion


def test_default_solver_wait_accepts_completion_after_forty_minutes(tmp_path, monkeypatch, caplog):
    worker = build_worker_shell(tmp_path)
    worker.log_path = tmp_path / "cst.log"
    task = Task.create(worker.session_id, {})
    clock = [0.0]
    checks = []
    monkeypatch.setattr("csttool.managed_cstworker.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(worker, "_ensure_running", lambda: checks.append(clock[0]))
    monkeypatch.setattr(worker, "_keep_window_minimized", lambda: None)

    def advance(_):
        clock[0] = 2401.0
        worker.completion_path.parent.mkdir(parents=True, exist_ok=True)
        worker.completion_path.write_text(encode_completion(
            Completion(task.task_id, task.session_id, CompletionStatus.SUCCESS)
        ), encoding="utf-8")

    monkeypatch.setattr("csttool.managed_cstworker.time.sleep", advance)
    with caplog.at_level(logging.INFO):
        completion = worker._wait_completion(task)
    assert worker.TASK_TIMEOUT is None
    assert completion.status is CompletionStatus.SUCCESS
    assert checks == [0.0, 2401.0]
    assert any(getattr(record, "event", None) == "CST_WAIT_PROGRESS"
               and record.timeout_seconds is None for record in caplog.records)


def test_unlimited_solver_wait_still_detects_process_failure(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    task = Task.create(worker.session_id, {})
    def failed():
        raise RuntimeError("CST process exited")
    monkeypatch.setattr(worker, "_ensure_running", failed)
    with pytest.raises(RuntimeError, match="CST process exited"):
        worker._wait_completion(task)


def test_wait_logs_debug_samples_but_only_ten_minute_info_heartbeats(tmp_path, monkeypatch, caplog):
    worker = build_worker_shell(tmp_path)
    worker.log_path = tmp_path / 'cst.log'
    task = Task.create(worker.session_id, {})
    clock = [0.0]
    ticks = iter([30, 60, 599, 600, 630, 1200, 1230])
    monkeypatch.setattr('csttool.managed_cstworker.time.monotonic', lambda: clock[0])
    monkeypatch.setattr(worker, '_ensure_running', lambda: None)
    monkeypatch.setattr(worker, '_keep_window_minimized', lambda: None)
    def advance(_):
        clock[0] = next(ticks)
        if clock[0] == 1230:
            worker.completion_path.parent.mkdir(parents=True)
            worker.completion_path.write_text(encode_completion(
                Completion(task.task_id, task.session_id, CompletionStatus.SUCCESS)
            ), encoding='utf-8')
    monkeypatch.setattr('csttool.managed_cstworker.time.sleep', advance)
    with caplog.at_level(logging.DEBUG):
        worker._wait_completion(task)
    records = [r for r in caplog.records if getattr(r, 'event', None) == 'CST_WAIT_PROGRESS']
    assert [r.elapsed_seconds for r in records if r.levelno == logging.INFO] == [600, 1200]
    assert any(r.levelno == logging.DEBUG and r.elapsed_seconds == 30 for r in records)


def test_explicit_solver_timeout_remains_available_for_test_harness(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker.TASK_TIMEOUT = 1.0
    task = Task.create(worker.session_id, {})
    clock = [0.0]
    monkeypatch.setattr("csttool.managed_cstworker.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("csttool.managed_cstworker.time.sleep", lambda _: clock.__setitem__(0, 2.0))
    monkeypatch.setattr(worker, "_ensure_running", lambda: None)
    monkeypatch.setattr(worker, "_keep_window_minimized", lambda: None)
    with pytest.raises(TimeoutError):
        worker._wait_completion(task)


def build_worker_shell(tmp_path):
    worker = object.__new__(ManagedCSTWorker)
    worker.logger = logging.getLogger("managed-worker-test")
    worker.root = tmp_path
    worker.project_path = tmp_path / "worker-input.cst"
    worker.session_id = "11111111-1111-4111-8111-111111111111"
    worker.task_path = tmp_path / "protocol" / "current.task"
    worker.completion_path = tmp_path / "protocol" / "current.completion"
    worker.ack_path = tmp_path / "protocol" / "current.ack"
    worker.marker_path = tmp_path / "worker.state"
    worker.stop_request_path = tmp_path / "protocol" / "stop.request"
    worker.stop_ack_path = tmp_path / "protocol" / "stop.ack"
    worker.result_root = tmp_path / "results"
    worker.macro_path = tmp_path / "runtime_managed_worker_v1.bas"
    worker.postprocess = CstPostProcessor()
    worker.postprocess.configure(
        [
            {
                "resultName": "frequency",
                "method": "Frequency",
                "params": {"iModeNumber": 1},
            },
            {
                "resultName": "rq",
                "method": "R_over_Q",
                "params": {
                    "iModeNumber": 1,
                    "axis": "x",
                    "xoffset": 0,
                    "yoffset": 2,
                    "zoffset": 3,
                },
            },
        ]
    )
    return worker


def test_archive_failure_does_not_dispatch_task(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker._lock = threading.RLock()
    worker._stopping = False
    worker.parameter_definitions = ()
    worker.marker_path.write_text('ready', encoding='ascii')
    monkeypatch.setattr(worker, '_wait_for_marker', lambda *args: None)
    def fail_archive(*args):
        raise OSError('archive unavailable')
    monkeypatch.setattr('csttool.managed_cstworker.archive_task', fail_archive)
    with pytest.raises(OSError, match='archive unavailable'):
        worker.run_task('mode-1', params={})
    assert worker.marker_path.read_text(encoding='ascii') == 'ready'
    assert not worker.task_path.exists()


def test_named_result_archive_preserves_cst_companion_and_task_identity(tmp_path):
    worker = build_worker_shell(tmp_path)
    task = Task.create(worker.session_id, {"fmin": 700, "fmax": 800})
    directory = worker.result_root / task.task_id
    directory.mkdir(parents=True)
    (directory / "project.cst").write_bytes(b"snapshot")
    (directory / "project" / "Result").mkdir(parents=True)
    (directory / "project" / "Result" / "field.rd0").write_bytes(b"field-data")
    postprocess = [{"resultName": "frequency", "value": 721.049793675422}]

    result_dir, snapshot = worker._name_result_archive(task, "hom_700_800", directory, postprocess)

    assert result_dir.name == f"hom_700_800__f_721.049794MHz__{task.task_id}"
    assert snapshot.name == "hom_700_800__f_721.049794MHz.cst"
    assert snapshot.read_bytes() == b"snapshot"
    assert (snapshot.with_suffix("") / "Result" / "field.rd0").read_bytes() == b"field-data"
    assert not directory.exists()
    metadata = json.loads((result_dir / "task_result.json").read_text(encoding="utf-8"))
    assert metadata["taskId"] == task.task_id
    assert metadata["projectSnapshot"] == snapshot.name
    assert metadata["postprocess"] == postprocess


def test_named_archive_keeps_original_on_destination_collision(tmp_path):
    worker = build_worker_shell(tmp_path)
    task = Task.create(worker.session_id, {})
    directory = worker.result_root / task.task_id
    directory.mkdir(parents=True)
    (directory / "project.cst").write_bytes(b"snapshot")
    (directory / "project").mkdir()
    destination = worker.result_root / f"task__{task.task_id}"
    destination.mkdir()
    (destination / "existing.txt").write_text("keep", encoding="utf-8")

    result_dir, snapshot = worker._name_result_archive(task, "task", directory, [])
    assert result_dir == directory
    assert snapshot.name == "project.cst"
    assert snapshot.read_bytes() == b"snapshot"
    assert (directory / "project").is_dir()
    assert (destination / "existing.txt").read_text(encoding="utf-8") == "keep"


def test_archive_name_cannot_escape_result_root(tmp_path):
    worker = build_worker_shell(tmp_path)
    task = Task.create(worker.session_id, {})
    directory = worker.result_root / task.task_id
    directory.mkdir(parents=True)
    (directory / "project.cst").write_bytes(b"snapshot")
    result_dir, snapshot = worker._name_result_archive(task, '../bad:name\\file', directory, [])
    assert result_dir.parent == worker.result_root
    assert snapshot.parent == result_dir
    assert snapshot.is_file()


def test_worker_names_archive_only_after_acknowledgement(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker.ID = "0"
    worker._lock = threading.RLock()
    worker._stopping = False
    worker.parameter_definitions = ()
    observed = []
    sample = [{"resultName": "frequency", "value": 721.049793675422}]

    def wait_completion(task):
        directory = worker.result_root / task.task_id
        directory.mkdir(parents=True)
        (directory / "project.cst").write_bytes(b"confirmed-snapshot")
        (directory / "project").mkdir()
        observed.append(directory)
        return Completion(task.task_id, task.session_id, CompletionStatus.SUCCESS)

    def wait_ready(marker, timeout):
        if observed:
            assert worker.ack_path.exists()
            assert (observed[0] / "project.cst").is_file()

    monkeypatch.setattr(worker, "_wait_completion", wait_completion)
    monkeypatch.setattr(worker, "_wait_for_marker", wait_ready)
    monkeypatch.setattr(worker.postprocess, "read_all_results", lambda: sample)
    result = worker.run_task("hom_700_800", params={"fmin": 700, "fmax": 800})
    assert result["TaskStatus"] == "Success"
    snapshot = Path(result["ProjectSnapshot"])
    assert snapshot.is_file()
    assert snapshot.parent == Path(result["ResultDirectory"])
    assert result["TaskID"] in snapshot.parent.name
    assert not observed[0].exists()


def test_optional_field_artifacts_do_not_enter_scalar_results(tmp_path, monkeypatch):
    worker=build_worker_shell(tmp_path)
    worker.ID='0';worker._lock=threading.RLock();worker._stopping=False
    worker.parameter_definitions=()
    def complete(task):
        directory=worker.result_root/task.task_id;directory.mkdir(parents=True)
        (directory/'project.cst').write_bytes(b'snapshot');(directory/'project').mkdir()
        return Completion(task.task_id,task.session_id,CompletionStatus.SUCCESS)
    monkeypatch.setattr(worker,'_wait_completion',complete)
    monkeypatch.setattr(worker,'_wait_for_marker',lambda *args:None)
    monkeypatch.setattr(worker.postprocess,'read_all_results',lambda:[
        {'id':0,'resultName':'frequency','value':570.0},
        {'id':1,'resultName':'field','value':{'kind':'field-artifact','status':'unavailable','reason':'disk full'}}])
    result=worker.run_task('field-test',params={})
    assert result['TaskStatus']=='Success'
    assert result['PostProcessResult']==[{'id':0,'resultName':'frequency','value':570.0}]
    assert result['FieldArtifacts'][0]['value']['status']=='unavailable'
    receipt=json.loads(Path(result['ReceiptPath']).read_text())
    assert receipt['postprocess']==result['PostProcessResult']
    assert receipt['field_artifacts'][0]['value']['context']['task_id']==result['TaskID']


def test_optional_diagnostic_missing_reference_does_not_request_solver_replay(tmp_path):
    worker=build_worker_shell(tmp_path)
    worker.ID='0';worker._stopping=False
    worker._field_reference_result=tmp_path/'missing-reference.json'
    worker._field_match_policy={'minimum_mac':.9,'minimum_margin':.05,'minimum_subspace_overlap':.99}
    task=Task.create(worker.session_id,{})
    result=worker._run_optional_field_diagnostic(task,tmp_path,[])
    assert result['status']=='incomplete'
    assert Path(result['path']).exists()


def test_managed_worker_macro_is_dynamic_ack_gated_and_standard_exit(tmp_path):
    worker = build_worker_shell(tmp_path)

    worker._build_macro()

    macro = worker.macro_path.read_text(encoding="ascii")
    assert macro.lower().count("sub main") == 1
    assert "current.task" in macro
    assert "CSTP_ReadTask" in macro
    assert "CSTP_ReadAck" in macro
    assert "CSTP_ReadStopRequest" in macro
    assert "Do\n" in macro
    assert 'Private Sub CSTPMW_CloseSession' in macro
    assert '    Save\n' in macro and '    Quit\n' not in macro
    assert 'closeStage = "batch-return"' in macro
    assert "stopped-with-completion" in macro
    assert "EigenResult_Simple_output" in macro
    assert "EigenResult_Complex_output" in macro
    assert "%" not in macro
    script = worker.project_path.with_suffix('')/'Model'/'3D'/'Model.run'
    assert script.read_text(encoding='ascii') == macro
    assert '\n    OpenFile ' not in macro
    worker.executable = Path('cst.exe')
    assert worker._launch_command() == ['cst.exe','-m','-b',str(worker.project_path)]


def test_expression_kind_comes_from_parameter_metadata_or_runtime_value():
    worker = object.__new__(ManagedCSTWorker)
    worker.parameter_definitions = (
        {"name": "literal", "type": "double"},
        {"name": "expr", "type": "expression"},
    )

    names = worker._expression_names(
        {"literal": 2.5, "expr": "2 * literal", "dynamic": "literal + 1"}
    )

    assert names == frozenset({"expr", "dynamic"})


def test_managed_worker_uses_non_activating_minimized_startup_on_windows():
    worker = object.__new__(ManagedCSTWorker)
    worker._run_in_background = True

    options = worker._background_startup_options()

    if os.name == "nt":
        startupinfo = options["startupinfo"]
        assert startupinfo.dwFlags & __import__("subprocess").STARTF_USESHOWWINDOW
        assert startupinfo.wShowWindow == 7
        assert options["creationflags"] & __import__(
            "subprocess"
        ).CREATE_NEW_PROCESS_GROUP
    else:
        assert options == {}


def test_managed_worker_can_leave_cst_window_interactive():
    worker = object.__new__(ManagedCSTWorker)
    worker._run_in_background = False

    options = worker._background_startup_options()
    if os.name == "nt":
        assert "startupinfo" not in options
        assert options["creationflags"] & __import__(
            "subprocess"
        ).CREATE_NEW_PROCESS_GROUP
    else:
        assert options == {}


def test_standard_stop_timeout_does_not_kill_cst(tmp_path, caplog):
    class Process:
        pid = 1

        def __init__(self):
            self.killed = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

    worker = build_worker_shell(tmp_path)
    worker.ID = "test"
    worker._lock = threading.RLock()
    worker._process = Process()
    worker._stopping = False
    worker.STOP_TIMEOUT = 0.01
    worker.protocol = __import__(
        "csttool.runtime_protocol", fromlist=["FileProtocol"]
    ).FileProtocol(tmp_path / "protocol")

    with pytest.raises(ManagedWorkerShutdownError, match="process is still running"):
        worker.stop()

    assert not worker._process.killed
    assert "WORKER_STOP_FAILED" in caplog.text
    assert "WORKER_STOPPED" not in caplog.text


@pytest.mark.parametrize("ack_fails", [False, True])
def test_task_logs_results_before_ack_and_only_completes_after_ready(tmp_path, monkeypatch, caplog, ack_fails):
    from types import SimpleNamespace
    from csttool.runtime_protocol import CompletionStatus

    worker = build_worker_shell(tmp_path)
    worker.ID = "test"
    worker._lock = threading.RLock()
    worker._stopping = False
    worker.parameter_definitions = ()
    worker.TASK_TIMEOUT = 1
    calls = []

    def wait_marker(*args):
        calls.append(args)
        if ack_fails and len(calls) == 2:
            raise TimeoutError("ready timeout")

    def complete(task):
        snapshot = worker.result_root / task.task_id / "project.cst"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_bytes(b"snapshot")
        return SimpleNamespace(status=CompletionStatus.SUCCESS)

    monkeypatch.setattr(worker, "_wait_for_marker", wait_marker)
    monkeypatch.setattr(worker, "_wait_completion", complete)
    monkeypatch.setattr(worker.postprocess, "read_all_results", lambda: [])
    caplog.set_level(logging.DEBUG)
    if ack_fails:
        from csttool.managed_cstworker import ManagedAcknowledgmentPending
        with pytest.raises(ManagedAcknowledgmentPending) as captured:
            worker.run_task("mode-1", params={})
        received = json.loads(captured.value.receipt_path.read_text(encoding='utf-8'))
        assert received['phase'] == 'received' and received['status'] == 'Success'
        assert Path(received['snapshot']).is_file()
        assert "TASK_ACK_FAILED" in caplog.text
        assert "WORKER_TASK_COMPLETE" not in caplog.text
    else:
        worker.run_task("mode-1", params={})
        received = json.loads(next((worker.root / 'received').glob('*.json')).read_text(encoding='utf-8'))
        assert received['phase'] == 'acknowledged'
        assert Path(received['snapshot']).is_file()
        events = ["CST_COMPLETION ", "RESULT_READ_DONE", "TASK_ACK_PUBLISHED", "TASK_ACK_READY", "WORKER_TASK_COMPLETE"]
        offsets = [caplog.text.index(event) for event in events]
        assert offsets == sorted(offsets)
    assert worker._active_task_context == {}


def test_emergency_termination_is_explicit(tmp_path):
    class Process:
        def __init__(self):
            self.killed = False

        def poll(self):
            return None if not self.killed else 1

        def kill(self):
            self.killed = True

        def wait(self, timeout):
            return 1

    worker = build_worker_shell(tmp_path)
    worker._lock = threading.RLock()
    worker._process = Process()
    worker._log_stream = None

    worker.emergency_terminate()

    assert worker._process.killed


def test_ready_marker_is_invalidated_before_task_publication(tmp_path, monkeypatch):
    worker = build_worker_shell(tmp_path)
    worker.ID = "test"
    worker._lock = __import__("threading").RLock()
    worker._stopping = False
    worker.parameter_definitions = ()
    worker.session_id = "11111111-1111-4111-8111-111111111111"
    worker.marker_path.write_text("ready", encoding="ascii")
    observed = []

    monkeypatch.setattr(worker, "_wait_for_marker", lambda expected, timeout: None)
    monkeypatch.setattr(
        "csttool.managed_cstworker.atomic_publish",
        lambda path, text: observed.append(worker.marker_path.read_text(encoding="ascii")),
    )
    monkeypatch.setattr(worker, "_wait_completion", lambda task: (_ for _ in ()).throw(RuntimeError("stop")))

    with pytest.raises(RuntimeError, match="stop"):
        worker.run_task("task", params={"x": 1})

    assert observed[0].startswith("dispatched:")


class _Global:
    def __init__(self, root):
        self.settings = GlobalSettings().with_cst("2022", str(root / "cst.exe"))


class _Project:
    def __init__(self, root):
        self.currProjectDir = root
        self.settings = ProjectSettings(name="test-project", cst_filename=Path("model.cst"))

    def get_postprocess_settings(self):
        return []


class _BadStopWorker:
    def run_task(self, resultname, *, params):
        raise AssertionError("not used")

    def stop(self):
        raise RuntimeError("standard shutdown failed")


def test_manager_propagates_worker_shutdown_failure_after_closing(tmp_path):
    manager = CSTManager(
        _Global(tmp_path),
        _Project(tmp_path),
        params=[],
        logger=logging.getLogger("managed-worker-stop-test"),
        maxTask=1,
        worker_factory=lambda *_args: _BadStopWorker(),
    )

    with pytest.raises(RuntimeError, match="did not stop cleanly"):
        manager.stop()

    assert manager.state is ManagerState.CLOSED
from csttool.configuration import GlobalSettings, ProjectSettings
