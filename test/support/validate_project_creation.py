"""G02 native-runtime empty-project controlled acceptance, no solver."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.acceptance_session import exclusive_probe
from csttool.application_service import ApplicationService
from csttool.configuration import write_json_atomic


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cst-exe',type=Path,required=True)
    parser.add_argument('--run-cst',action='store_true')
    args=parser.parse_args()
    if not args.run_cst:parser.error('requires --run-cst')
    with exclusive_probe(ROOT):
        root=ROOT/'artifacts'/('project-create-'+uuid4().hex[:8]);root.mkdir()
        print('CREATION_ROOT='+str(root),flush=True)
        app=ApplicationService(root,'g02-project',installations={'local':args.cst_exe})
        request=dict(kind='definition',operation='create_project',name='empty-mws',installation_ref='local',module='mws',
                     units=dict(length='mm',frequency='MHz'))
        record=app.create_project(request,operation_id='g02-create')
        assert app.inspect_model(record['document_id'],record['document_revision'])==record
        assert app.create_project(request,operation_id='g02-create')==record
        write_json_atomic(root/'acceptance.json',dict(gate='G02-empty-subset',record=record,real_cst=True,solver_calls=0))
        print('CREATION_ACCEPTED',flush=True)

if __name__=='__main__':main()
