import json
import logging
import pytest

from csttool.native_progress import NativeProgressTracker, parse_native_progress
from csttool.runtime_protocol import Task, new_session_id


def text(header, percent=0, message='working: detail'):
    return f'Header:string:{header}\nText:string:{message}\nProgress:int:{percent}\n'


def test_parser_preserves_unknown_headers_and_colons():
    parsed = parse_native_progress(text('Unknown future stage', 37))
    assert parsed['header'] == 'Unknown future stage'
    assert parsed['text'] == 'working: detail'
    assert parsed['percent'] == 37
    assert parse_native_progress('Header:string:Mesh\n') is None
    assert parse_native_progress(text('Mesh', 101)) is None


def test_stage_history_ignores_old_file_and_tracks_transitions(tmp_path):
    path = tmp_path / 'progress.log'
    path.write_text(text('Old stage'), encoding='utf-8')
    task = Task.create(new_session_id(), {'nmodes': 1})
    tracker = NativeProgressTracker(path, tmp_path / 'history', '0', task.session_id,
                                    task, logging.getLogger('native-test'))
    tracker.poll(force=True)
    assert not tracker.directory.exists()
    for header, percent in [('Mesh', 10), ('Mesh', 50), ('Eigenmode', 0), ('Mesh', 100)]:
        path.write_text(text(header, percent), encoding='utf-8')
        tracker.poll(force=True)
    tracker.poll(force=True)
    records = [json.loads(line) for line in (tracker.directory / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(records) == 4
    assert [r['header'] for r in records] == ['Mesh', 'Mesh', 'Eigenmode', 'Mesh']
    assert all(r['task_id'] == task.task_id and 'raw' in r for r in records)
    assert json.loads((tracker.directory / 'stages.json').read_text())['observed_headers'] == ['Mesh', 'Eigenmode']


def test_partial_write_does_not_create_false_stage(tmp_path):
    path = tmp_path / 'progress.log'
    task = Task.create(new_session_id(), {})
    tracker = NativeProgressTracker(path, tmp_path / 'history', '0', task.session_id,
                                    task, logging.getLogger('native-test'))
    path.write_text('Header:string:Incomplete\n', encoding='utf-8')
    tracker.poll(force=True)
    assert tracker.last_observation is None
    assert not tracker.directory.exists()


def test_native_event_carries_task_identity_and_real_stage(tmp_path):
    path = tmp_path / 'progress.log'
    task = Task.create(new_session_id(), {'fmin': 500, 'fmax': 550})
    events = []
    tracker = NativeProgressTracker(path, tmp_path / 'history', '0', task.session_id,
                                    task, logging.getLogger('native-test'), events.append)
    path.write_text(text('Meshing:', 20), encoding='utf-8')
    tracker.poll(force=True)
    assert events[0].source == 'progress.log'
    assert events[0].session_id == task.session_id
    assert events[0].task_id == task.task_id
    assert events[0].stage == 'mesh'
    assert events[0].native_header == 'Meshing:'
    assert events[0].local_percent == 20


def test_postprocessing_header_is_normalized_but_raw_evidence_is_preserved(tmp_path):
    path = tmp_path / 'progress.log'
    task = Task.create(new_session_id(), {'fmin': 714.606, 'fmax': 764.606})
    events = []
    tracker = NativeProgressTracker(path, tmp_path / 'history', '0', task.session_id,
        task, logging.getLogger('native-postprocessing-test'), events.append)
    raw = text('Post-Processing:', 100, 'Creating parametric 1D results.')
    path.write_bytes(raw.encode('utf-8'))
    tracker.poll(force=True)
    assert events[0].stage == 'postprocess'
    assert events[0].native_header == 'Post-Processing:'
    assert events[0].local_percent == 100
    assert events[0].message == 'Creating parametric 1D results.'
    record = json.loads((tracker.directory / 'events.jsonl').read_text(encoding='utf-8'))
    assert record['raw'] == raw and record['header'] == 'Post-Processing:'


def test_unknown_native_stage_remains_opaque():
    from csttool.cst_progress import normalize_cst_stage
    assert normalize_cst_stage('Future CST stage:') == 'Future CST stage:'


@pytest.mark.parametrize(('header', 'message', 'stage'), [
    ('Collecting features:', 'Collecting all features', 'feature-collection'),
    ('Creating Tetrahedral Mesh:', 'Mesher initialization', 'tetrahedral-mesh'),
    ('Eigenmode solver:', 'Calculating eigenmode solution.', 'eigenmode-solver'),
    ('Post-Processing:', 'Creating parametric 1D results.', 'postprocess'),
])
def test_observed_application_log_stage_samples(tmp_path, header, message, stage):
    path = tmp_path / 'progress.log'
    task = Task.create(new_session_id(), {})
    events = []
    tracker = NativeProgressTracker(path, tmp_path / 'history', '0', task.session_id,
        task, logging.getLogger('application-log-stage-samples'), events.append)
    # application.log has no percent; this zero is synthetic input, not observed data.
    path.write_bytes(text(header, 0, message).encode('utf-8'))
    tracker.poll(force=True)
    assert events[0].stage == stage
    assert events[0].native_header == header
    assert events[0].message == message
