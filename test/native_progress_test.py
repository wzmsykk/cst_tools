import json
import logging

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
    assert events[0].stage == 'Meshing:'
    assert events[0].local_percent == 20
