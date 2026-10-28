import json
import logging
from pathlib import Path

from csttool.run_overview import RunOverview, RunOverviewHandler, rebuild_log_index
from csttool.run_store import RunStore
from csttool.logging_config import ApplicationLogSession, ContextLogger


def test_readable_name_preserves_identity_and_directory_is_reused(tmp_path):
    identity = 'a'*32
    overview = RunOverview(tmp_path, identity, 'HOM-500-1000MHz', resume=True)
    assert 'HOM-500-1000MHz_续跑' in overview.directory.name
    assert overview.directory.name.endswith('a'*8)
    assert overview.directory.name != identity
    data = json.loads((overview.directory/'run.json').read_text(encoding='utf-8'))
    assert data['run_id'] == identity
    assert data['created_local'].endswith('+08:00')
    again = RunOverview(tmp_path, identity, 'another purpose')
    assert again.directory == overview.directory
    assert data['purpose'] == 'HOM-500-1000MHz'
    store = RunStore(tmp_path, overview.directory, run_id=identity)
    store.event('task-1','submitted')
    assert json.loads((overview.directory/'run.json').read_text(encoding='utf-8'))['run_id'] == identity


def test_summary_has_coverage_first_error_source_and_paths(tmp_path):
    overview = RunOverview(tmp_path,'b'*32,'HOM-100-200MHz',settings={'fmin':100,'endfreq':200})
    checkpoint = tmp_path/'save/csv/hom_scan_checkpoint.json'
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text(json.dumps({'coverage':{'confirmed_frontier':150,'calculated_upper':160},
                                     'report':{'modes':[]},'pending':[{'lo':150,'hi':160}]}))
    handler = RunOverviewHandler(overview)
    logger = logging.getLogger('overview-test')
    logger.addHandler(handler)
    try:
        logger.error('首个错误',extra={'record_id':'record-1','diagnostics':'temp/diagnostic','recovery_hint':'先恢复'})
        logger.error('第二个错误')
        overview.update(status='INTERRUPTED')
    finally:
        logger.removeHandler(handler)
        handler.close()
    text = (overview.directory/'summary.md').read_text(encoding='utf-8')
    assert '150 MHz' in text and '160 MHz' in text
    assert '首个错误' in text and '第二个错误' not in text
    assert 'record-1' in text and 'temp/diagnostic' in text
    assert __file__ in text
    assert 'INTERRUPTED' in (tmp_path/'logs/index.md').read_text(encoding='utf-8')


def test_legacy_random_directories_are_indexed_not_moved_or_overwritten(tmp_path):
    old = tmp_path/'logs'/('c'*32)
    old.mkdir(parents=True)
    metadata = old/'run.json'
    metadata.write_text(json.dumps({'run_id':'c'*32,'project':str(tmp_path),'created_utc':'old time'}))
    (old/'application.log').write_text('preserved')
    before = metadata.read_bytes()
    broken = tmp_path/'logs/broken'
    broken.mkdir()
    (broken/'run.json').write_text('{bad')
    rebuild_log_index(tmp_path)
    assert metadata.read_bytes() == before
    assert (old/'application.log').read_text() == 'preserved'
    assert (old/'summary.md').is_file()
    index = (tmp_path/'logs/index.md').read_text(encoding='utf-8')
    assert 'old time' in index and '元数据损坏' in index
    assert old.name in index


def test_names_are_windows_safe_and_same_short_id_does_not_overwrite(tmp_path):
    a = RunOverview(tmp_path,'d'*32,'HOM:500/1000*?')
    b = RunOverview(tmp_path,'d'*8+'e'*24,'HOM:500/1000*?')
    assert a.directory != b.directory
    assert not any(c in a.directory.name for c in ':/*?')
    assert json.loads((a.directory/'run.json').read_text(encoding='utf-8'))['run_id'] == 'd'*32
    assert json.loads((b.directory/'run.json').read_text(encoding='utf-8'))['run_id'] == 'd'*8+'e'*24


def test_backend_and_manager_share_readable_directory(tmp_path):
    from test.application_backend_test import make_backend
    backend, _, _, _, calls = make_backend()
    backend._uses_default_manager = True  # Factory still returns a fake, never CST.
    owner = ApplicationLogSession(tmp_path/'startup.log',console=False)
    backend._log_owner = owner
    backend._base_logger = owner.logger
    backend.logger = owner.logger
    backend.select_project_directory(str(tmp_path))
    backend.select_cst_file('source.cst')
    try:
        backend.initialize_run(False,1)
        assert 'HOM-500' in backend.log_path.parent.name
        assert backend.log_path.parent == backend._run_overview.directory
        backend.prepare_run()
        assert calls[0]['run_directory'] == backend.log_path.parent
        assert calls[0]['run_overview'] is backend._run_overview
        assert calls[0]['run_id'] == backend.run_id
        backend.logger.error('模拟失败',extra={'diagnostics':'diagnostic-path'})
        assert '模拟失败' in (backend.log_path.parent/'summary.md').read_text(encoding='utf-8')
        backend.execute_run()
    finally:
        backend.close_logging()
    assert backend._overview_handler is None


def test_hom_checkpoints_refresh_live_summary_not_only_terminal_state(tmp_path):
    from types import SimpleNamespace
    from test.hom_scan_test import ScanManager
    from csttool.hom_scan_algorithm import HomScanAlgorithm
    overview = RunOverview(tmp_path,'f'*32,'HOM-100-120MHz')
    overview.update(status='RUNNING')
    manager = ScanManager(tmp_path)
    manager.run_store = SimpleNamespace(overview=overview)
    algorithm = HomScanAlgorithm(manager=manager,params=[])
    algorithm.set_cst_parameters([])
    algorithm.set_editable_attributes({'fmin':100,'fmax':110,'endfreq':120})
    report = algorithm.start()
    summary = json.loads((overview.directory/'run.json').read_text(encoding='utf-8'))
    # Missing postprocess output leaves a real gap; no false full coverage.
    assert report.failed and report.failed[0].lo == 114.000001
    assert summary['coverage']['confirmed_frontier'] == report.failed[0].lo
    assert summary['mode_count'] == len(report.modes)
    assert summary['pending_count'] == 0
    assert summary['status'] == 'RUNNING'  # Observer never invents terminal success.
