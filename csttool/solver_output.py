"""Extract observed settings and adaptive passes from CST output.txt."""
import locale
import re
import time

from .configuration import write_json_atomic


def parse_solver_output(text):
    settings, passes, refinement, messages = {}, [], [], []
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        setting = re.match(r'\s*(Mesh|Method|Desired accuracy|Number of modes|Consider losses|Solver order|Curved elements):\s*(.+)', line)
        if setting:
            settings[setting[1]] = setting[2]
        threads = re.search(r'Number of threads used:\s*(\d+)', line)
        if threads:
            settings['threads'] = int(threads[1])
        estimate = re.search(r'Estimation frequency:\s*([\d.eE+-]+)\s*(\S+)', line)
        if estimate:
            settings['estimation_frequency'] = {'value': float(estimate[1]), 'unit': estimate[2]}
        match = re.match(r'Pass\s+(\d+)\s*:', stripped)
        if match:
            current = {'pass': int(match[1]), 'modes': []}
            passes.append(current)
        mode = re.match(r'\s*(\d+)\s+([\d.eE+-]+)\s+(\w+)\s+([\d.eE+-]+)\s*$', line)
        if mode and current is not None:
            current['modes'].append({'mode': int(mode[1]), 'frequency': float(mode[2]),
                                     'frequency_unit': mode[3], 'accuracy': float(mode[4])})
        marked = re.search(r'Marked\s+(\d+)\s+of\s+(\d+)\s+for refinement', line)
        if marked:
            refinement.append({'pass': current['pass'] if current else None,
                               'marked': int(marked[1]), 'total': int(marked[2])})
        if any(word in stripped.casefold() for word in ('successful', 'stopped', 'error', 'warning', 'creating parametric')):
            messages.append(stripped)
    return {'settings': settings, 'passes': passes, 'refinement': refinement,
            'messages': messages, 'solver_success_observed': 'Eigenmode solver successful' in text}


class SolverOutputTracker:
    def __init__(self, path, directory, task, logger):
        self.path, self.directory, self.task, self.logger = path, directory, task, logger
        self.baseline = self._fingerprint()
        self.last = None
        self.next_poll = 0.0
        self.warned = False

    def _fingerprint(self):
        try:
            stat = self.path.stat()
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def poll(self, force=False):
        now = time.monotonic()
        if not force and now < self.next_poll:
            return
        self.next_poll = now + 1.0
        stamp = self._fingerprint()
        if stamp is None or stamp in (self.baseline, self.last):
            return
        try:
            raw = self.path.read_bytes()
            if stamp != self._fingerprint():
                return
            try:
                text = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw.decode(locale.getpreferredencoding(False), errors='replace')
            parsed = parse_solver_output(text)
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / 'output-observed.txt').write_bytes(raw)
            write_json_atomic(self.directory / 'solver-output.json', {
                'task_id': self.task.task_id, 'session_id': self.task.session_id,
                'source': str(self.path), 'source_mtime_ns': stamp[0], **parsed})
            self.last = stamp
        except (OSError, ValueError) as exc:
            if not self.warned:
                self.logger.warning('CST output.txt 提取失败，不影响求解：%s', exc)
                self.warned = True
