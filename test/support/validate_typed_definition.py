"""Explicit public modern-stdio A1 acceptance; serial new copies, optional solve.

This is an SDK client, not evidence that Codex desktop has reloaded new tools.
"""
import argparse
import asyncio
import hashlib
import json
import math
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.configuration import read_json,write_json_atomic
from csttool.acceptance_session import exclusive_probe


async def run(root,solve,resume=False):
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
    trace=[]
    previous_trace=read_json(root/'public-calls.json') if resume else None
    trace_path=root/('public-calls-'+uuid4().hex[:8]+'.json' if resume else 'public-calls.json')
    params=StdioServerParameters(command=sys.executable,args=['-m','csttool.mcp_server','--project',str(root)],cwd=ROOT)
    async with Client(params,mode='2026-07-28',read_timeout_seconds=30) as client:
        async def call(name,arguments):
            result=await client.call_tool(name,arguments)
            if result.is_error:
                raise RuntimeError(name+': '+str(result.content))
            value=result.structured_content
            trace.append(dict(tool=name,result={k:v for k,v in value.items() if k!='control_handle'}))
            write_json_atomic(trace_path,trace)
            return value
        connection=await call('connect_project',dict(client_id='typed-acceptance',launch=True))
        handle=connection['control_handle']
        async def control(operation):
            return await call('control_project',dict(control_handle=handle,operation=operation,request_id=uuid4().hex))
        async def execute(name,args):
            await control('claim')
            args=dict(args,control_handle=handle,request_id=uuid4().hex)
            receipt=await call(name,args)
            repeat=await call(name,args)
            if repeat!=receipt:raise AssertionError('request replay changed operation identity')
            last=None
            while True:
                status=await call('get_project_status',{})
                if status.get('phase')!=last:
                    print(json.dumps(dict(operation=name,state=status['state'],phase=status['phase']),ensure_ascii=False),flush=True)
                    last=status.get('phase')
                if not status.get('execution_active'):break
                await asyncio.sleep(1)
            if status['state']!='COMPLETED':raise RuntimeError(json.dumps(status,ensure_ascii=False))
            if name=='submit_run':return await call('get_simulation_results',dict(run_id=receipt['run_id']))
            return await call('get_operation_result',dict(run_id=receipt['run_id']))
        installations=await call('list_installations',{})
        refs=[i['installation_ref'] for i in installations['installations'] if '2022' in i['name']]
        if len(refs)!=1:raise RuntimeError('one authorized CST2022 installation required')
        empty=None if resume else await execute('create_project',dict(name='typed-pillbox',installation_ref=refs[0]))
        def revision(record):
            return dict(document_id=record['document_id'],expected_document_revision=record['document_revision'])
        changes=[dict(op='set_parameters',values={
            'R':dict(expression='100',quantity='length',description='radius in mm'),
            'L':dict(expression='R',quantity='length',description='preserved expression: length equals radius')}),
            dict(op='ensure_component',component_id='cavity'),
            dict(op='create_cylinder',object_id='pillbox',component_id='cavity',axis='z',center=['0']*3,
                axial_range=['-L/2','L/2'],outer_radius='R',inner_radius='0',material='Vacuum',segments=0),
            dict(op='set_background',material='PEC',padding_mm=[0]*6),
            dict(op='set_boundaries',faces=['electric']*6,symmetry=['none']*3)]
        if resume:
            await control('claim');await control('recover')
            while True:
                recovered=await call('get_project_status',{})
                if not recovered.get('execution_active'):break
                await asyncio.sleep(1)
            if recovered['state']!='IDLE':raise RuntimeError('previous acceptance recovery is not complete')
            draft=next(row['result'] for row in reversed(previous_trace) if row['tool']=='get_operation_result' and row['result'].get('state')=='draft' and row['result'].get('spec',{}).get('simulation'))
        else:
            draft=await execute('apply_model_changes',dict(**revision(empty),changes=changes))
            draft=await execute('configure_simulation',dict(**revision(draft),simulation=dict(
            solver='eigenmode',method='default',mesh=dict(type='tet',cells_per_wavelength=4,adaptive=False),
            frequency_range_mhz=dict(min=500,max=2000),frequency_lower_target_mhz=500,requested_modes=1,losses='postprocess_only'),
            postprocess=[dict(metric_id='frequency',method_id='Frequency',settings={'mode':dict(selection='one',index=1)}),
                dict(metric_id='rq',method_id='R_over_Q',settings={'mode':dict(selection='one',index=1),
                    'integration_line':dict(axis='z',offset_mm=[0]*3,beta=1,range='full')})]))
        saved=await execute('save_project',dict(**revision(draft),verify_reopen=True))
        observed=await call('inspect_model',dict(document_id=saved['document_id'],document_revision=saved['document_revision']))
        if observed!=saved or not saved['ready']:raise AssertionError('immutable saved definition not ready')
        report=dict(gate='G02/G03-public-sdk',real_cst=True,desktop_host=False,model=saved,solver_start_calls=0,
            resumed_existing_public_draft=resume,public_trace=str(trace_path))
        if solve:
            result=await execute('submit_run',dict(document_id=saved['document_id'],definition_revision=saved['definition_revision']))
            if result['postprocess_definition']['r_over_q']['integration_line']['axis']!='z':raise AssertionError('RQ context missing')
            if result['postprocess_definition']['generated_macro_evidence']!='archived':raise AssertionError('macro evidence missing')
            analytic=299792458*2.404825557695773/(2*math.pi*.1)/1e6
            relative=abs(result['frequency_mhz']/analytic-1)
            if relative>.05:raise AssertionError('Pillbox frequency error exceeds 5%')
            await control('claim')
            request=dict(control_handle=handle,run_id=result['run_id'],result_revision=result['result_revision'],
                formats=['json','csv'],request_id=uuid4().hex)
            exported=await call('export_simulation_results',request)
            if await call('export_simulation_results',request)!=exported:raise AssertionError('export retry differs')
            for artifact in exported['artifacts']:
                path=(root/artifact['path']).resolve()
                if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=artifact['sha256']:
                    raise AssertionError('export artifact identity mismatch')
            lifecycle=list((root/'control/runs'/result['run_id']).glob('workers/*/*/lifecycle.log'))
            starts=sum(path.read_text(errors='replace').count('calling EigenmodeSolver.Start') for path in lifecycle)
            if starts!=1:raise AssertionError('actual Solver.Start trace count must be one')
            report.update(gate='G01-G08-public-sdk-normal-subset',result=result,exports=exported,
                solver_start_calls=starts,solver_trace_files=[str(path) for path in lifecycle],
                analytic_tm010_mhz=analytic,frequency_relative_error=relative)
        await execute('close_project',dict(**revision(saved),disposition='save'))
        await control('claim');await control('shutdown')
        from csttool.runner_ownership import RunnerOwnership
        deadline=asyncio.get_running_loop().time()+10
        while True:
            try:
                lease=RunnerOwnership(root/'control/runner.lock').acquire();lease.close();break
            except RuntimeError:
                if asyncio.get_running_loop().time()>deadline:raise
                await asyncio.sleep(.1)
        report['runner_exit_confirmed']=True
        write_json_atomic(root/'acceptance.json',report)
        print('TYPED_ACCEPTED',flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-cst',action='store_true');parser.add_argument('--solve',action='store_true')
    parser.add_argument('--resume-project',type=Path)
    args=parser.parse_args()
    if not args.run_cst:parser.error('requires explicit --run-cst')
    with exclusive_probe(ROOT):
        if args.resume_project:
            root=args.resume_project.resolve(strict=True)
            if not root.is_relative_to(ROOT/'artifacts'):parser.error('acceptance resume must be inside artifacts')
        else:
            root=ROOT/'artifacts'/('typed-public-'+uuid4().hex[:8]);root.mkdir()
        print('TYPED_ROOT='+str(root),flush=True)
        asyncio.run(run(root,args.solve,bool(args.resume_project)))


if __name__=='__main__':main()
