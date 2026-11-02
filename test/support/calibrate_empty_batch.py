"""Controlled empty-MWS batch precondition: explicit solver identity, no solve."""
from pathlib import Path
import argparse
import json
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from csttool.acceptance_session import exclusive_probe
from csttool.configuration import write_json_atomic
from csttool.definition_verifier import run_definition_probe
from csttool.vb_codec import quote_vb_string
import csttool.project_creation as module


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-cst',action='store_true');args=parser.parse_args()
    if not args.run_cst:parser.error('--run-cst required')
    with exclusive_probe(ROOT):
        root=ROOT/'artifacts'/('empty-batch-'+uuid4().hex[:8]);root.mkdir()
        print('CALIBRATION_ROOT='+str(root),flush=True)
        old=module.BRIDGE
        marker="    stage('save')"
        assert old.count(marker)==1
        module.BRIDGE=old.replace(marker,"    project.modeler.add_to_history('Explicit MWS solver identity','ChangeSolverType \"HF Eigenmode\"')\n"+marker)
        try:
            proof=module.NativeProjectCreator()(root/'created',Path(r'D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe'))
        finally:module.BRIDGE=old
        import shutil
        directory=root/'probe';directory.mkdir();model=directory/'definition.cst';shutil.copyfile(root/'created/definition.cst',model)
        nonce=uuid4().hex
        macro="'#Language \"WWB-COM\"\nOption Explicit\nSub Main\n Dim f As Integer\n Save\n f=FreeFile\n Open \""+quote_vb_string(directory/'completed.txt')+'" For Output As #f\n Print #f, "'+nonce+'"\n Close #f\nEnd Sub\n'
        closure=run_definition_probe(Path(r'D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe'),model,directory,macro)
        report=dict(hypothesis='explicit-solver-identity-enables-empty-batch',creation=proof,batch=closure,
            macro_executed=(directory/'completed.txt').exists() and (directory/'completed.txt').read_text().strip()==nonce,
            solver_start_calls=0)
        write_json_atomic(root/'acceptance.json',report)
        print(json.dumps(dict(macro_executed=report['macro_executed'],closure=closure)),flush=True)


if __name__=='__main__':main()
