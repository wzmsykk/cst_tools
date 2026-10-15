"""OS-held ownership: never infer permission to steal a lock from a heartbeat."""
import os
from pathlib import Path


class RunnerOwnership:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            raise RuntimeError('another controller owns this project') from None
        self.stream = stream
        return self

    def close(self):
        if self.stream:
            self.stream.close()
            self.stream = None


def protect_directory(path):
    """Restrict endpoint credentials before publishing them; fail closed."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        import csv
        import subprocess
        result = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True)
        sid = next(csv.reader([result.strip()]))[-1]
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r',
                        f'*{sid}:(OI)(CI)F'], check=True, capture_output=True)
    else:
        os.chmod(path, 0o700)
