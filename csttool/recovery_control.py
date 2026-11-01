"""Cooperative recovery pause; no process termination or result rollback."""
class RecoveryPaused(RuntimeError):
    pass
