"""Bounded local export runs off the Qt event thread."""
from PyQt5.QtCore import QThread
from csttool.diagnostic_bundle import export_failure_bundle


class DiagnosticExportThread(QThread):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.outcome = None

    def run(self):
        try:
            self.outcome = {'result': export_failure_bundle(self.project)}
        except Exception as error:
            self.outcome = {'error': f'{type(error).__name__}: {error}'}
