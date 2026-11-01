"""Bounded local export runs off the Qt event thread."""
from PyQt5.QtCore import QThread, pyqtSignal
from csttool.diagnostic_bundle import export_failure_bundle, ExportCancelled


class DiagnosticExportThread(QThread):
    progress = pyqtSignal(object)
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.outcome = None

    def run(self):
        try:
            self.outcome = {'result': export_failure_bundle(self.project,
                cancel_check=self.isInterruptionRequested, progress=self.progress.emit)}
        except ExportCancelled:
            self.outcome = {'cancelled': True}
        except Exception as error:
            self.outcome = {'error': f'{type(error).__name__}: {error}'}
