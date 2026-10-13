"""CST2022 native interface scope probe, also runnable by bundled Python3.6."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]


def child(directory):
    sys.path.insert(0,'D:/Program Files (x86)/CST Studio Suite 2022/AMD64/python_cst_libraries')
    from cst.interface import DesignEnvironment
    source=ROOT/'artifacts/hom-mesh-baseline-de2d6b90/cell-30/prepared.cst'
    de=None
    project=None
    report={'solver_run':False}
    def stage(value):
        (directory/'stage.txt').write_text(value)
    try:
        stage('native-start')
        de=DesignEnvironment.new(options=['-m','-i'])
        report['native_pid']=de.pid()
        stage('native-load')
        project=de.open_project(str(source))
        stage('native-save-copy')
        project.save(str(directory/'copy.cst'),include_results=True)
        report['filename']=project.filename()
        stage('native-full-rebuild')
        report['rebuilt']=project.modeler.full_history_rebuild(timeout=90)
        stage('native-save-after-rebuild')
        project.save()
        report['status']='complete' if report['rebuilt']==1 else 'incomplete'
        report['evidence_scope']='native return and saved-copy lifecycle; not a captured macro error log'
        project.close()
        project=None
        de.close()
        de=None
        if report['status']=='complete':
            (directory/'completed.txt').write_text('SUCCESS')
        else:
            (directory/'failed.txt').write_text('native rebuild did not return success')
    except Exception as error:
        report['status']='incomplete'
        report['failure']=str(error)
        (directory/'failed.txt').write_text(str(error))
    finally:
        (directory/'native-report.json').write_text(json.dumps(report,indent=2))
        if project is not None:
            try:
                project.close()
            except Exception as error:
                report['close_error']=str(error)
        if de is not None:
            try:
                de.close()
            except Exception as error:
                report['environment_close_error']=str(error)
        (directory/'native-report.json').write_text(json.dumps(report,indent=2))
    return 0 if report.get('status')=='complete' else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--child',action='store_true')
    parser.add_argument('--directory',type=Path)
    args=parser.parse_args()
    if args.child:
        return child(args.directory)
    import subprocess
    from uuid import uuid4
    sys.path.insert(0,str(ROOT))
    from csttool.acceptance_session import exclusive_probe,wait_probe
    from csttool.configuration import write_json_atomic
    from csttool.result_reconciliation import file_hash
    from csttool.cst_process_env import cst_process_environment
    source=ROOT/'artifacts/hom-mesh-baseline-de2d6b90/cell-30/prepared.cst'
    before=file_hash(source)
    directory=ROOT/'artifacts'/('native-parameter-scope-'+uuid4().hex[:8])
    directory.mkdir(parents=True)
    print('PROBE_ROOT='+str(directory),flush=True)
    native_python='D:/Program Files (x86)/CST Studio Suite 2022/AMD64/python/python.exe'
    with exclusive_probe(ROOT):
        with (directory/'cst.log').open('wb') as log:
            process=subprocess.Popen([native_python,__file__,'--child','--directory',str(directory)],
                                     stdout=log,stderr=subprocess.STDOUT,env=cst_process_environment())
            session=wait_probe(process,directory)
        report={'session':session,'source_unchanged':file_hash(source)==before,'exit_code':process.returncode}
        write_json_atomic(directory/'report.json',report)
        print(report,flush=True)
    return process.returncode


if __name__=='__main__':
    raise SystemExit(main())
