"""Finish/reconcile an already-computed public acceptance; never submit a solve."""
import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from csttool.configuration import read_json,write_json_atomic


async def finish(root,run_id):
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
    store=root/'control/runs'/run_id
    journal=(store/'events.jsonl').read_bytes()
    traces=[]
    for path in sorted(root.glob('public-calls*.json')):traces.extend(read_json(path))
    params=StdioServerParameters(command=sys.executable,args=['-m','csttool.mcp_server','--project',str(root)],cwd=ROOT)
    calls=[]
    async with Client(params,mode='2026-07-28') as client:
        async def call(name,args):
            response=await client.call_tool(name,args)
            if response.is_error:raise RuntimeError(name+': '+str(response.content))
            value=response.structured_content
            calls.append(dict(tool=name,result={k:v for k,v in value.items() if k!='control_handle'}))
            write_json_atomic(root/'public-finish-calls.json',calls)
            return value
        connection=await call('connect_project',dict(client_id='public-finish',launch=True))
        handle=connection['control_handle']
        async def control(op):return await call('control_project',dict(control_handle=handle,operation=op,request_id=uuid4().hex))
        await control('claim');await control('recover')
        while True:
            status=await call('get_project_status',{})
            if not status['execution_active']:break
            await asyncio.sleep(1)
        if status['state']!='IDLE':raise AssertionError(json.dumps(status))
        result=await call('get_simulation_results',dict(run_id=run_id))
        saved=next(row['result'] for row in reversed(traces) if row['tool']=='get_operation_result'
            and row['result'].get('state')=='saved' and row['result'].get('definition_revision')==result['definition_revision'])
        inspect=await call('inspect_model',dict(document_id=saved['document_id'],document_revision=saved['document_revision']))
        if inspect!=saved:raise AssertionError('saved public definition changed')
        analytic=299792458*2.404825557695773/(2*math.pi*.1)/1e6
        relative=abs(result['frequency_mhz']/analytic-1)
        if relative>.05:raise AssertionError('analytic gate failed')
        await control('claim')
        request=dict(control_handle=handle,run_id=run_id,result_revision=result['result_revision'],formats=['json','csv'],request_id=uuid4().hex)
        exported=await call('export_simulation_results',request)
        if await call('export_simulation_results',request)!=exported:raise AssertionError('export replay changed')
        for artifact in exported['artifacts']:
            path=(root/artifact['path']).resolve()
            if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=artifact['sha256']:
                raise AssertionError('export hash/path mismatch')
        lifecycle=list(store.glob('workers/*/*/lifecycle.log'))
        starts=sum(p.read_text(errors='replace').count('calling EigenmodeSolver.Start') for p in lifecycle)
        if starts!=1 or (store/'events.jsonl').read_bytes()!=journal:
            raise AssertionError('reconciliation repeated Solver/adoption journal')
        await control('claim')
        close=await call('close_project',dict(control_handle=handle,document_id=saved['document_id'],expected_document_revision=saved['document_revision'],disposition='save',request_id=uuid4().hex))
        while True:
            status=await call('get_project_status',{})
            if not status['execution_active']:break
            await asyncio.sleep(1)
        if status['state']!='COMPLETED':raise AssertionError(json.dumps(status))
        closed=await call('get_operation_result',dict(run_id=close['run_id']))
        if closed['state']!='closed':raise AssertionError('logical document not closed')
        await control('claim');await control('shutdown')
        from csttool.runner_ownership import RunnerOwnership
        deadline=asyncio.get_running_loop().time()+10
        while True:
            try:
                lease=RunnerOwnership(root/'control/runner.lock').acquire();lease.close();break
            except RuntimeError:
                if asyncio.get_running_loop().time()>deadline:raise
                await asyncio.sleep(.1)
        from csttool.lifecycle_diagnostics import project_lifecycle
        facts=project_lifecycle(root)
        if facts['physical_pending_count'] or facts['recovery_required']:raise AssertionError('lifecycle not reconciled')
        write_json_atomic(root/'acceptance.json',dict(gate='G01-G08-public-sdk-with-adoption-recovery',date='2026-11-03',
            real_cst=True,desktop_host=False,model=saved,result=result,exports=exported,solver_start_calls=starts,
            recovery_solver_calls=0,adoption_journal_unchanged=True,runner_exit_confirmed=True,lifecycle=facts,
            analytic_tm010_mhz=analytic,frequency_relative_error=relative))
        print(json.dumps(dict(accepted=True,frequency_mhz=result['frequency_mhz'],rq_ohm=result['rq_ohm'],solver_calls=starts)),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True,type=Path);parser.add_argument('--run-id',required=True)
    args=parser.parse_args();root=args.project.resolve(strict=True)
    if not root.is_relative_to(ROOT/'artifacts'):parser.error('requires acceptance artifacts root')
    asyncio.run(finish(root,args.run_id))


if __name__=='__main__':main()
