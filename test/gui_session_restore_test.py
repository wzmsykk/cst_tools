"""GUI selection restoration is not authorization to replay a computation."""
import json
from pathlib import Path
import pytest
from GUI.session_store import GuiSessionStore
from GUI.runner_backend import RunnerBackend
from GUI.main_window import MainWindow
from GUI.run_controller import RunState
from csttool.configuration import write_json_atomic
from csttool.runner import Runner
from test.gui_runner_test import app, Client, wait
from test.runner_test import WaitingExecution
from test.gui_log_restore_test import write_log


def test_selection_survives_new_backend_and_does_not_store_runtime_authority(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    store = GuiSessionStore(tmp_path / 'settings/gui.json')
    first = RunnerBackend(session_store=store)
    first.select_project_directory(project)
    restored = RunnerBackend(session_store=GuiSessionStore(store.path))
    assert restored.restore_last_project()
    assert restored.project == str(project.resolve())
    assert json.loads(store.path.read_text()) == {'schema_version': 1, 'project': str(project.resolve())}
    assert not restored.client.launch_attempted and not (project / 'control').exists()


@pytest.mark.parametrize('value', ['broken', [], {'schema_version': 999, 'project': 'x'},
                                   {'schema_version': 1, 'project': 'missing-relative'}])
def test_bad_saved_selection_does_not_create_project_or_runner(tmp_path, value):
    store = GuiSessionStore(tmp_path / 'settings.json')
    store.path.write_text(value if value == 'broken' else json.dumps(value))
    backend = RunnerBackend(session_store=store)
    assert not backend.restore_last_project()
    assert backend.project is None and backend.client is None and backend.restore_message


def test_deleted_previous_project_is_not_recreated(tmp_path):
    project = tmp_path / 'gone'; project.mkdir()
    store = GuiSessionStore(tmp_path / 'session.json'); store.remember(project); project.rmdir()
    backend = RunnerBackend(session_store=store)
    assert not backend.restore_last_project() and not project.exists()


def test_restore_project_settings_from_manifest_without_writing_project(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    manifest = project / 'save/csv/scan_manifest.json'
    write_json_atomic(manifest, dict(schema_version=3,frequency_start=500, initial_window=50,
        frequency_stop=1000,mesh_cells_per_wavelength=8,preprocess_modify_mesh=False,
        worker_count=2,source_project='source.cst'))
    settings = [{'resultName':'frequency','method':'Frequency','params':{'iModeNumber':1}}]
    write_json_atomic(project / 'pps.json', settings)
    before = manifest.read_bytes(), (project / 'pps.json').read_bytes()
    store = GuiSessionStore(tmp_path / 'session.json'); store.remember(project)
    backend = RunnerBackend(session_store=store)
    assert backend.restore_last_project() and backend.has_checkpoint
    assert backend.algorithm['fmin']==500 and backend.algorithm['fmax']==550
    assert backend.algorithm['endfreq']==1000 and not backend.algorithm['preprocess_modify_mesh']
    assert backend.restored_worker_count==2 and backend.postprocess==settings
    assert before == (manifest.read_bytes(), (project / 'pps.json').read_bytes())


@pytest.mark.parametrize('state', ['RUNNING','INTERRUPTED','RECOVERY_REQUIRED'])
def test_open_window_automatically_restores_project_live_facts_and_logs(app, tmp_path, monkeypatch, state):
    project = tmp_path / 'project'; project.mkdir()
    store = GuiSessionStore(tmp_path / 'session.json'); store.remember(project)
    directory = project / 'logs/previous'; write_log(directory, 'previous project event')
    runner = Runner(project, WaitingExecution)
    runner.update(state=state, run_id='original-run', log_directory=str(directory),
                  coverage={'confirmed_frontier':812.5,'calculated_upper':850},mode_count=4)
    class DirectClient(Client):
        client_id = 'new-window'
        def connect(self, **kw): return runner.snapshot()
        def events(self, cursor=0): return runner.events(cursor)
    client = DirectClient(str(project.resolve()))
    monkeypatch.setattr('GUI.runner_backend.RunnerClient',lambda path: client)
    backend = RunnerBackend(session_store=store); backend.supports_cst_backend_selection=False
    window = MainWindow(engine=backend)
    monkeypatch.setattr(window,'_runner_close_choice',lambda:'detach')
    try:
        wait(app,lambda: window.controller.instance==runner.instance_id)
        def restored_log():
            window.logTextBox.flush_pending()
            return any(row['message']=='previous project event' for row in window.logTextBox.model.rows)
        wait(app,restored_log)
        assert window.dirNameLineEdit.text()==str(project.resolve())
        assert backend.runner_status['run_id']=='original-run'
        assert '812.5 MHz' in window.stateDetailLabel.text()
        assert client.ops==[] and runner.worker is None
        if state=='RECOVERY_REQUIRED': assert window.controller.state is RunState.RECOVERY_REQUIRED
    finally:
        window.close(); wait(app,lambda: window.controller.closed); app.processEvents()
        runner.close()


def test_smoke_entrypoint_skips_persistent_selection():
    import ast
    tree=ast.parse(Path('gui_app.py').read_text(encoding='utf-8'))
    branch=next(node for node in ast.walk(tree) if isinstance(node,ast.If) and isinstance(node.test,ast.Name) and node.test.id=='smoke_test')
    assert 'GuiSessionStore' not in ast.unparse(branch.body)
