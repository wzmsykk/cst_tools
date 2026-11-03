"""Shared launch/observation resources for already-loaded CST batch projects.

No COM lookup, window activation, dialog answering or process termination.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import time
from .configuration import write_json_atomic
from .cst_process_env import cst_process_environment
from .cst_background import PrivateDesktop, BackgroundWindowObserver, WindowsWindowBackend
from .windows_desktop_process import DesktopProcess
from .acceptance_session import task_project_processes


def literal_content(value):
    """Shared typed string emission for fixed-template literal placeholders."""
    from .winwrap_emitter import String
    return String(str(value)).render()[1:-1]


def macro_manifest(directory, text, *, purpose, sources):
    """Physical-line guard and reproducible origin; not a full grammar proof."""
    from .winwrap_emitter import check_lines
    check_lines(text.splitlines())
    write_json_atomic(Path(directory)/'generation-manifest.json', dict(purpose=purpose,
        generated_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
        check='physical-lines-only', line_limit=800,
        sources=[dict(path=str(p),sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest()) for p in sources]))


class BatchDesktopLease:
    def __init__(self, executable, project, directory, *, isolate=True):
        self.executable=Path(executable);self.project=Path(project);self.directory=Path(directory)
        self.isolate=bool(isolate and os.name=='nt')
        self.desktop=None;self.observer=None;self.process=None
        self.last_observed=0.

    def start(self, command, log, **options):
        try:
            if self.isolate:
                self.desktop=PrivateDesktop()
                self.observer=BackgroundWindowObserver(self.executable.parent,minimize=False,
                    backend=WindowsWindowBackend(self.desktop.handle))
                self.observer.__enter__()
                self.process=DesktopProcess(command,desktop='WinSta0\\'+self.desktop.name,
                    cwd=self.directory,env=cst_process_environment(),log=log)
            else:
                self.process=subprocess.Popen(command,cwd=self.directory,env=cst_process_environment(),
                    stdout=log,stderr=subprocess.STDOUT,**options)
            write_json_atomic(self.directory/'desktop-lease.json',dict(isolated=self.isolate,
                desktop=self.desktop.name if self.desktop else None,pid=self.process.pid,resources_closed=False))
            return self.process
        except BaseException:
            self.finish()
            raise

    def observe(self, records=None):
        if self.observer:
            if records is None:
                now=time.monotonic()
                if now-self.last_observed < .5:return
                self.last_observed=now
                records=[dict(pid=p.pid,create_time=p.create_time()) for p in task_project_processes(self.project)]
            self.observer.bind(records)

    def finish(self):
        """Release local handles only, never imply or force native process exit."""
        observer,self.observer=self.observer,None
        try:
            if observer:
                observer.__exit__(None,None,None)
                report=observer.report();report['private_desktop']=self.desktop.name
                write_json_atomic(self.directory/'window-observation.json',report)
        finally:
            if self.desktop:
                self.desktop.close()
            write_json_atomic(self.directory/'desktop-lease.json',dict(isolated=self.isolate,
                desktop=self.desktop.name if self.desktop else None,
                pid=self.process.pid if self.process else None,resources_closed=True,
                process_exit_not_implied=True))
