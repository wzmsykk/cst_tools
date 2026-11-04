"""Lifecycle reconciliation for owned, non-solving G03 batch sessions.

Recovery waits for normal batch return. It never reruns a probe, adopts results,
uses global Active3D, or interprets physical exit as standard success.
"""
from pathlib import Path
import time
import math
import psutil
from .configuration import read_json, write_json_atomic


def definition_status_paths(catalog):
    """All owned definition phases, including nested GEO candidate verification."""
    catalog=Path(catalog).resolve()
    for path in sorted(catalog.rglob('session-status.json')):
        if not path.resolve().is_relative_to(catalog):raise ValueError('definition session escapes catalog')
        yield path


def definition_session_facts(project):
    catalog=(Path(project).resolve()/'control/definitions')
    sessions=[]
    for path in definition_status_paths(catalog):
        directory=path.parent.resolve()
        if not directory.is_relative_to(catalog.resolve()):
            raise ValueError('definition session escapes catalog')
        state='unknown';reason='缺少归属进程记录';report={}
        try:
            report=read_json(path)
            if not isinstance(report,dict):raise ValueError('definition status must be an object')
            owned=report.get('owned')
            # Earlier G03 producers persisted exit codes in the verification
            # journal, not the per-phase status. Read that existing proof only.
            if report.get('exit_confirmed') is True and report.get('exit_code') is None:
                proof_path=directory.parent/'verification.json'
                if proof_path.exists():
                    proof=read_json(proof_path)
                    if not isinstance(proof,dict):raise ValueError('definition proof must be an object')
                    if not isinstance(proof.get('sessions'),list) or any(not isinstance(s,dict) for s in proof['sessions']):
                        raise ValueError('definition proof sessions must be objects')
                    matches=[s for s in proof.get('sessions',[]) if s.get('phase')==directory.name]
                    if len(matches)==1 and matches[0].get('exit_confirmed') is True:
                        report={**report,'exit_code':matches[0].get('exit_code')}

            if report.get('exit_confirmed') is True:
                state='exited';reason='已记录归属进程退出'
            elif isinstance(owned,list) and owned:
                state='exited';reason='已记录的进程身份均已退出，未推断退出码'
                for identity in owned:
                    pid,created=identity['pid'],identity['create_time']
                    if type(pid) is not int or pid<=0 or (type(created) not in (int,float) or not math.isfinite(created)):
                        raise ValueError('invalid owned process identity')
                    try:
                        proc=psutil.Process(pid)
                        if abs(proc.create_time()-created)<.001 and proc.is_running():
                            state='running';reason='等待本次验证batch正常退出'
                    except psutil.NoSuchProcess:pass
            if state!='unknown' and report.get('exit_confirmed') is not True:
                from .acceptance_session import task_project_processes
                related=list(task_project_processes(directory/'definition.cst'))
                if related:
                    state='running';reason='已核实副本路径的验证进程仍在运行'
            standard=state=='exited' and report.get('exit_confirmed') is True and type(report.get('exit_code')) is int and report['exit_code']==0
            reconciled=report.get('disposition')=='abandoned-dead'
            pending=state!='exited' or (not standard and not reconciled)
        except (OSError,ValueError,KeyError,TypeError,psutil.Error) as error:
            report=report if isinstance(report,dict) else {}
            state='unknown';standard=False;pending=True;reason=str(error)
        bootstrap=directory.parent.name=='verification-bootstrap'
        sessions.append(dict(kind='project-bootstrap' if bootstrap else 'definition-verification',worker_id='G02' if bootstrap else 'G03',session_id=directory.parent.name+'/'+directory.name,
            workspace=str(directory),evidence_path=str(path),receipt_path=str(directory/'completed.txt'),
            process_state=state,process_identity_reason=reason,exit_code=report.get('exit_code'),
            exit_classification='zero' if standard else 'unverified',standard_closed=standard,
            task_outcome='definition-observation',
            model_state=('saved-empty-project' if standard else 'candidate-state-unknown') if bootstrap else 'frozen-definition-unchanged',
            disposition='standard-stop' if standard else report.get('disposition','pending'),
            needs_recovery=pending,missing_evidence=[] if not pending else [reason],
            result_observation=dict(state='not-applicable')))
    return sessions


def recover_definition_sessions(project,*,timeout=60,progress=None,pause_check=None):
    """Called under the project owner lock; observe/wait, never kill or re-execute."""
    deadline=time.monotonic()+timeout
    while True:
        if pause_check:pause_check()
        sessions=definition_session_facts(project)
        pending=[s for s in sessions if s['needs_recovery']]
        if not pending:return sessions
        for session in pending:
            if progress:progress(dict(stage='definition-recovery',session_id=session['session_id'],
                reason=session['process_identity_reason'],workspace=session['workspace']))
            if session['process_state']=='unknown':
                raise RuntimeError('G03 ownership unknown: '+session['workspace'])
            if session['process_state']=='exited':
                path=Path(session['evidence_path'])
                report=read_json(path)
                report.update(exit_confirmed=True,disposition='abandoned-dead',reconciled=True)
                # No exit code or verified definition is manufactured.
                write_json_atomic(path,report)
        if all(s['process_state']=='exited' for s in pending):continue
        if time.monotonic()>=deadline:raise TimeoutError('G03 batch still running; preserve session and retry recovery')
        time.sleep(min(.1,max(0,deadline-time.monotonic())))
