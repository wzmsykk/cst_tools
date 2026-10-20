"""Shared persisted recovery gate; independent of GUI and execution backends."""
from pathlib import Path
from .configuration import ProjectSettings, read_ini, read_json


EXPLICIT_RECOVERY_STATES = frozenset({'RUNNING', 'STOP_REQUESTED', 'RECOVERY_REQUIRED'})


def persisted_project_status(project):
    if project is None:
        return None
    path = Path(project) / 'project.ini'
    if not path.exists():
        return None
    return ProjectSettings.from_parser(read_ini(path)).task_status


def validate_recovery_checkpoint(project):
    """Read-only validation; never advances coverage or adopts pending results."""
    from .hom_scan import ScanCheckpointStore, ScanPolicy
    project = Path(project)
    path = project / 'save/csv/hom_scan_checkpoint.json'
    if path.exists():
        document = read_json(path)
        ScanCheckpointStore(path).load_with_snapshot(
            ScanPolicy(**document['policy']), document['projectFingerprint'])
    standard = project / 'save/standard_batch_checkpoint.json'
    if standard.exists():
        document = read_json(standard)
        if (document.get('schema_version') != 1 or not isinstance(document.get('results'), list)
                or type(document.get('pending_index')) is not int
                or document['pending_index'] != len(document['results'])
                or not isinstance(document.get('task_signature'), str)):
            raise ValueError('invalid standard checkpoint; recovery cannot confirm resume safety')
