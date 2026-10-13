"""Conservative local admission budgets, not OS-enforced CST resource limits."""
from contextlib import contextmanager
from dataclasses import dataclass
from threading import RLock
import psutil


class ResourceAdmissionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResourceBudget:
    estimated_threads: int = 1
    estimated_memory_bytes: int = 1024**3
    free_headroom_bytes: int = 512 * 1024**2

    def __post_init__(self):
        if min(self.estimated_threads, self.estimated_memory_bytes) <= 0 or self.free_headroom_bytes < 0:
            raise ValueError('resource budgets must be positive')


class ResourceAdmission:
    def __init__(self, budget):
        self.budget = budget
        self.active = 0
        self.lock = RLock()

    def check(self, workers):
        budget = self.budget
        if workers * budget.estimated_threads > (psutil.cpu_count() or 1):
            raise ResourceAdmissionError('requested worker CPU budget exceeds host capacity')
        if workers * budget.estimated_memory_bytes + budget.free_headroom_bytes > psutil.virtual_memory().available:
            raise ResourceAdmissionError('insufficient available memory for worker budget')

    @contextmanager
    def reservation(self):
        with self.lock:
            self.check(self.active + 1)
            self.active += 1
        try:
            yield
        finally:
            with self.lock:
                self.active -= 1
