"""Normal offscreen GUI exit against an existing synthetic Runner; never starts CST."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from GUI.main_window import MainWindow
from GUI.runner_backend import RunnerBackend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', required=True)
    parser.add_argument('--choice', choices=['stop', 'detach'], required=True)
    parser.add_argument('--lost-shutdown-response', action='store_true')
    args = parser.parse_args()
    app = QApplication([])
    backend = RunnerBackend()
    backend.supports_cst_backend_selection = False
    backend.select_project_directory(args.project)
    if args.lost_shutdown_response:
        original = backend.client.command
        def command(operation, *a, **kw):
            result = original(operation, *a, **kw)
            if operation == 'shutdown': raise OSError('injected lost shutdown HTTP response')
            return result
        backend.client.command = command
    window = MainWindow(engine=backend)
    window._runner_close_choice = lambda: args.choice
    window.show()
    timer = QTimer()
    def close_when_connected():
        if window.controller.instance and not window.controller.has_active_work and window.controller.state.name != 'STOPPING':
            timer.stop()
            window.close()
        elif window.controller.instance and window.controller.state.name == 'RUNNING':
            timer.stop()
            window.close()
    timer.timeout.connect(close_when_connected)
    timer.start(25)
    timed_out = []
    def deadline():
        timed_out.append(True)
        window._runner_close_choice = lambda: 'detach'
        window._close_confirmed = False
        window.close()
    QTimer.singleShot(20000, deadline)
    result = app.exec_()
    report = dict(pid=os.getpid(), choice=args.choice, controller_closed=window.controller.closed,
                  runner_stopped=window.controller.runner_stopped, timed_out=bool(timed_out),
                  gui_resources_closed=getattr(window, '_gui_resources_closed', False))
    (Path(args.project) / 'gui-exit-probe.json').write_text(json.dumps(report), encoding='utf-8')
    return 23 if timed_out else result


if __name__ == '__main__':
    sys.exit(main())
