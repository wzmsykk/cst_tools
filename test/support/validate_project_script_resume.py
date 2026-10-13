"""No-solver smoke check: a saved Model.run must not replay its old session."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.acceptance_session import exclusive_probe
from csttool.configuration import read_json,write_json_atomic
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.result_reconciliation import file_hash
from test.managed_hom_ten_modes_fault_resume_integration_test import _config


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cst-exe',required=True)
    parser.add_argument('--source-report',required=True,type=Path)
    args=parser.parse_args()
    source=Path(read_json(args.source_report)['result']['ProjectSnapshot'])
    before=file_hash(source)
    directory=ROOT/'artifacts'/('project-script-resume-'+uuid4().hex[:8])
    directory.mkdir(parents=True)
    config=_config(directory,'0',Path(args.cst_exe),source)
    config['postProcess']=[]
    print(f'RESUME_ROOT={directory}',flush=True)
    report={'source':str(source),'solver_run':False}
    worker=None
    with exclusive_probe(ROOT):
        try:
            worker=ManagedCSTWorker('0',config)
            report['fresh_session_ready']=worker.marker_path.read_text().strip()=='ready'
            report['session_id']=worker.session_id
            report['script_matches']=worker.batch_script_path.read_bytes()==worker.macro_path.read_bytes()
        except Exception as error:
            report['failure']=str(error)
            raise
        finally:
            if worker is not None:
                report['stop_returned']=worker.stop()
                report['stop_ack']=worker.protocol.read_stop_ack(worker.session_id) is not None
                report['exit_code']=worker._process.poll()
            report['source_unchanged']=file_hash(source)==before
            write_json_atomic(directory/'report.json',report)
    assert report['fresh_session_ready'] and report['script_matches'],report
    assert report['stop_returned'] and report['stop_ack'] and report['exit_code']==0,report
    assert report['source_unchanged'],report
    print(report,flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
