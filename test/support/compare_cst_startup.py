"""Opt-in serial startup comparison; no solver, force-kill or user files."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.runtime_protocol import atomic_publish
from csttool.diagnostics import write_failure_report
from test.cst_integration_support import windows_process_snapshot, cst_processes, new_cst_processes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cst-exe', required=True)
    args = parser.parse_args()
    root = ROOT / '.pytest_cache' / 'startup-comparison' / uuid4().hex[:8]
    root.mkdir(parents=True)
    source = root / 'input.cst'
    shutil.copy2(ROOT / 'model/Pillbox_2015.cst', source)
    marker = root / 'stage.txt'
    macro = root / 'startup.bas'
    atomic_publish(macro, f'''Option Explicit
Sub Main
    Open "{marker}" For Output As #1
    Print #1, "macro-entered"
    Close #1
    OpenFile "{source}"
    Save
    Open "{marker}" For Append As #1
    Print #1, "project-saved"
    Close #1
    Quit
End Sub
''')
    reports = []
    for name, minimized, isolated in [('normal', False, False), ('minimized', True, False),
                                      ('isolated', False, True), ('worker-options', True, True)]:
        case = root / name
        case.mkdir()
        if marker.exists():
            marker.rename(case / 'previous-stage.txt')
        baseline = cst_processes(windows_process_snapshot())
        options = {}
        if minimized:
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 7
            options['startupinfo'] = startup
        if isolated:
            options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        started = time.monotonic()
        with (case / 'cst.log').open('wb') as log:
            process = subprocess.Popen([args.cst_exe, '-m', str(macro)], stdout=log,
                                       stderr=subprocess.STDOUT, **options)
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                pass
        remaining = new_cst_processes(baseline)
        entry = {'case': name, 'pid': process.pid, 'exit_code': process.poll(),
                 'elapsed': time.monotonic()-started, 'remaining': remaining,
                 'stage': marker.read_text() if marker.exists() else None}
        if process.poll() != 0 or remaining:
            entry['diagnostics'] = str(write_failure_report(case, phase='startup-comparison',
                                       process=process, paths={'log': case/'cst.log', 'marker': marker}))
        reports.append(entry)
        print(json.dumps(entry, ensure_ascii=True), flush=True)
        atomic_publish(case / 'report.json', json.dumps(entry, indent=2, ensure_ascii=False))
        if process.poll() is None or remaining:
            print('Stopped comparison: live session requires standard recovery.', flush=True)
            break
    atomic_publish(root / 'report.json', json.dumps(reports, indent=2, ensure_ascii=False))
    print(f'Report: {root / "report.json"}', flush=True)


if __name__ == '__main__':
    main()
