"""Real single-simulation publication-gap recovery, no repeated Solver call."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.acceptance_session import exclusive_probe
from csttool.application_service import ApplicationService
from csttool.execution_contract import StopIntent
from csttool.configuration import write_json_atomic
import csttool.application_service as service_module


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--cst-exe',type=Path,required=True)
    parser.add_argument('--run-cst',action='store_true')
    args=parser.parse_args()
    if not args.run_cst:parser.error('requires --run-cst')
    source=args.source.resolve(strict=True)
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    with exclusive_probe(ROOT):
        root=ROOT/'artifacts'/('single-recovery-'+uuid4().hex[:8]);root.mkdir()
        print('RECOVERY_ROOT='+str(root),flush=True)
        service=ApplicationService(root,'single-recovery',installations={'local':args.cst_exe})
        definition=service.stage_definition('pillbox',source,'local')
        service.verify_definition('pillbox',definition['definition_revision'])
        payload=dict(kind='simulation',document_id='pillbox',definition_revision=definition['definition_revision'])
        original_write=service_module.write_json_atomic
        def fail_publication(path,value):
            if Path(path).name=='simulation-result.json':raise OSError('controlled publication gap after adoption')
            return original_write(path,value)
        execution=service.execute_simulation(payload,run_id='recover-one',stop=StopIntent(),update=lambda **values:None)
        service_module.write_json_atomic=fail_publication
        injected=False
        try:
            execution.run(payload)
        except OSError as error:
            if 'controlled publication gap' not in str(error):raise
            injected=True
        finally:service_module.write_json_atomic=original_write
        if not injected:raise RuntimeError('fault injection did not reach intended point')
        store=root/'control/runs/recover-one'
        journal=store/'events.jsonl'
        before=journal.read_bytes()
        service.reconcile_simulation('recover-one')
        result=service.get_simulation_results('recover-one')
        service.reconcile_simulation('recover-one')
        if journal.read_bytes()!=before:raise RuntimeError('reconciliation duplicated journal/adoption')
        lifecycle=list(store.glob('workers/*/*/lifecycle.log'))
        starts=sum(path.read_text(errors='replace').count('calling EigenmodeSolver.Start') for path in lifecycle)
        if starts!=1:raise RuntimeError('unexpected Solver start count')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=original:raise RuntimeError('source changed')
        write_json_atomic(root/'acceptance.json',dict(case='publication-after-adoption',real_cst=True,
            solver_start_calls=starts,recovery_solver_calls=0,duplicate_adoption=False,
            source_sha256=original,result=result))
        print('RECOVERY_ACCEPTED',flush=True)

if __name__=='__main__':main()
