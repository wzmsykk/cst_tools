"""Bounded JSONL replay. Raw logs remain authoritative and untouched."""
import json
import os


def read_events(path, cursor=0, limit=100):
    if not path.exists():
        return {'schema_version': 2, 'cursor': 0, 'events': []}
    stat = path.stat()
    generation = f'{path}:{stat.st_dev}:{stat.st_ino}:{stat.st_ctime_ns if os.name == "nt" else 0}'
    state = dict(cursor) if isinstance(cursor, dict) else {'offset': cursor}
    if state.get('generation', generation) != generation or not 0 <= state.get('offset', 0) <= stat.st_size:
        state = {'offset': 0}
    state['generation'] = generation
    records = []
    budget = 262144
    with path.open('rb') as stream:
        stream.seek(state.get('offset', 0))
        while budget > 0 and len(records) < min(200, max(1, limit)):
            begin = stream.tell()
            line = stream.readline(min(65537, budget))
            budget -= len(line)
            if not line:
                break
            discarding = state.get('discarding', False)
            if discarding:
                state['discarding'] = not line.endswith(b'\n')
            elif len(line) > 65536:
                records.append({'level': 'WARNING', 'event': 'LOG_RECORD_SKIPPED',
                                'message': '日志记录过长；请查看原始 JSONL',
                                'context': {'raw_file': str(path), 'byte_offset': begin}})
                state['discarding'] = not line.endswith(b'\n')
            elif not line.endswith(b'\n'):
                stream.seek(begin)  # An ordinary incomplete tail is not a business event.
                break
            else:
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise ValueError('record is not an object')
                    records.append(record)
                except (ValueError, UnicodeError):
                    records.append({'level': 'WARNING', 'event': 'LOG_RECORD_INVALID',
                                    'message': '日志记录损坏；请查看原始 JSONL',
                                    'context': {'raw_file': str(path), 'byte_offset': begin}})
        state['offset'] = stream.tell()
    return {'schema_version': 2, 'cursor': state, 'events': records}
