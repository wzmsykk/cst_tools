"""Conservative sustained-memory guard, independent of solver wall time."""
from dataclasses import dataclass

import psutil

MemorySamplingError = psutil.Error


@dataclass(frozen=True)
class MemoryGuardPolicy:
    enabled: bool = True
    physical_fraction: float = 0.90
    minimum_bytes: int = 8 * 1024**3
    growth_factor: float = 4.0
    sustained_seconds: float = 600.0
    stalled_seconds: float = 600.0
    sample_seconds: float = 30.0

    def __post_init__(self):
        if not 0 < self.physical_fraction <= 1:
            raise ValueError("physical_fraction must be within (0, 1]")
        if self.growth_factor < 1 or min(self.minimum_bytes, self.sustained_seconds,
                                      self.stalled_seconds, self.sample_seconds) <= 0:
            raise ValueError("memory guard thresholds must be positive; growth_factor >= 1")


class SustainedMemoryGuard:
    def __init__(self, policy):
        self.policy = policy
        self.baseline = None
        self.high_since = None
        self.last_progress = None
        self.log_size = None

    def observe(self, now, memory_bytes, physical_bytes, log_size):
        if self.last_progress is None or log_size != self.log_size:
            self.last_progress, self.log_size = now, log_size
        if self.baseline is None:
            self.baseline = max(memory_bytes, 1)
        limit = max(self.policy.minimum_bytes,
                    physical_bytes * self.policy.physical_fraction,
                    self.baseline * self.policy.growth_factor)
        if not self.policy.enabled or memory_bytes < limit:
            self.high_since = None
            return False
        if self.high_since is None:
            self.high_since = now
        return (now - self.high_since >= self.policy.sustained_seconds
                and now - self.last_progress >= self.policy.stalled_seconds)


def owned_process_memory(process):
    """Only sample a live Popen-owned root and its current descendants.

    Windows private bytes avoid counting shared DLL pages repeatedly. Other
    platforms use RSS. Access errors fail closed: never infer permission to kill.
    """
    if process.poll() is not None:
        return None
    root = psutil.Process(process.pid)
    try:
        members = [root, *root.children(recursive=True)]
        total = 0
        for member in members:
            try:
                info = member.memory_info()
                total += getattr(info, "private", info.rss)
            except psutil.NoSuchProcess:
                if member.pid == root.pid:
                    return None
        if process.poll() is not None:
            return None
        return total, psutil.virtual_memory().total
    except psutil.NoSuchProcess:
        return None
