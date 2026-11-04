"""W3 owned serial no-solver XYZ, compiler and injected-failure acceptance.

--publish-gate writes the local source-version gate only after every native
check and normal close succeeds. It does not publish a release or run a solver.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from csttool.acceptance_session import exclusive_probe,cst_processes
from csttool.configuration import read_json,write_json_atomic
from csttool.definition_editing import render_history,render_edit_macro,build_candidate
from csttool.definition_verifier import NativeDefinitionVerifier
from csttool.native_definition_builder import run_new_definition
from csttool.saved_project_source import read_saved_source
from csttool.winwrap_checks import (PROFILE,generator_fingerprint,check_module,execution_definition_map,map_native_error)
from csttool.history_program import partition
from csttool.managed_history import extract_program,verify_saved_program,_canonical
from csttool.winwrap_emitter import assign_string,Variable,String
from csttool.application_service import ServiceError
from test.support.calibrate_cst_macrocheck import cases,render,evaluate
from test.support.calibrate_winwrap_calls import definition


def spec_for(axis):
    spec=definition();spec['cylinder']['axis']=axis
    spec['postprocess'][1]['settings']['integration_line']['axis']=axis
    spec['parameters']['L']['expression']='(R^2)/R + R'
    spec['parameters']['R']['description']=('长说明 "R" '*20).rstrip()
    spec['cylinder']['axial_range']=['-(L+R)/2','(L+R)/2']
    return spec


def compile_cases(directory):
    rows=cases(directory)
    for axis in 'xyz':
        spec=spec_for(axis);history=render_history(spec)[0]
        rows.append(('outer-'+axis,render_edit_macro(directory,spec,'0'*32),True))
        rows.append(('history-'+axis,'\'#Language "WWB-COM"\nOption Explicit\nSub Main\n'+history+'\nEnd Sub\n',True))
    outer=rows[-2][1]
    # CST2022.5 accepts this exact unterminated-string sample in MacroCheckThis.
    # Keep it observational; offline generation intentionally requires closure.
    rows.append(('outer-unclosed-quote-observed',outer.replace('"batch-return"','"batch-return'),None))
    rows.append(('outer-unbalanced-expression',outer.replace('    f = FreeFile','    f = (',1),False))
    rows.append(('outer-duplicate-procedure',outer+'\nPrivate Sub ReportStage\nEnd Sub\n',False))
    return rows


def require_closed(closure):
    if (closure.get('exit_confirmed') is not True or type(closure.get('exit_code')) is not int
            or closure['exit_code']!=0):
        raise RuntimeError('owned standard closure not confirmed; stop this serial probe')


def verify_rejected_prefix(source,spec):
    """The invalid geometry block and every later block must remain unapplied."""
    program=partition(spec)
    index=next(i for i,b in enumerate(program) if b['caption']=='CST Tools A1 geometry-cylinder')
    actual=extract_program(source);expected=program[:index]
    if (len(actual)!=len(expected) or any(a['caption']!=b['caption'] or
            _canonical(a['history'])!=_canonical(b['history']) for a,b in zip(actual,expected))):
        raise RuntimeError('syntax rejection did not preserve exactly the pre-geometry saved prefix')
    return [b['caption'] for b in actual]


def injected_syntax_diagnostic(directory):
    """Bind deliberate probe changes, without rewriting the production diagnostic."""
    production=read_json(directory/'native-diagnostic.json')
    mapping=read_json(directory/'source-map.json');index=production.get('block_index')
    blocks=mapping['block_hashes']
    if (type(index) is not int or not 0<=index<len(blocks)
            or blocks[index]['caption']!='CST Tools A1 geometry-cylinder'
            or hashlib.sha256((directory/'probe.bas').read_text(encoding='ascii').encode('ascii')).hexdigest()!=mapping['hashes']['final_outer']
            or hashlib.sha256((directory/'history.vb').read_text(encoding='ascii').encode('ascii')).hexdigest()!=blocks[index]['history_sha256']):
        raise RuntimeError('injected source artifacts differ from recorded source map')
    diagnostic=map_native_error((directory/'history-syntax-error.txt').read_text(),mapping,block_index=index)
    if (diagnostic.get('origin') or {}).get('input_field')!='cylinder.axial_range':
        raise RuntimeError('native history error not mapped to injected input')
    diagnostic['provenance']='trusted-calibration-injection; production original-source diagnostic preserved'
    diagnostic['production_mapping_status']=production.get('mapping_status')
    write_json_atomic(directory/'injected-native-diagnostic.json',diagnostic)
    return diagnostic


def write_bundle(directory,spec,history,macro,program=None):
    (directory/'history.vb').write_text(history,encoding='ascii',newline='\n')
    (directory/'edit.bas').write_text(macro,encoding='ascii',newline='\n')
    write_json_atomic(directory/'source-map.json',execution_definition_map(spec,partition(spec) if program is None else program,macro))


def negative(root,executable,kind):
    """Trusted probe injection, not an API accepting caller-provided VB."""
    spec=spec_for('z');history=render_history(spec)[0]
    closures=[]
    def editor(exe,model,directory,macro):
        program=deepcopy(list(partition(spec)))
        block=next(b for b in program if b['caption']=='CST Tools A1 geometry-cylinder')
        original=block['history']
        if kind=='syntax':
            line=next(s for s in original.splitlines() if s.startswith(' .Zrange '))
            altered=original.replace(line,' .Zrange ((-RestoreDoubleParameter("L"))/2), (RestoreDoubleParameter("L")/2)')
        else:altered='WCS.ActivateWCS "global"'
        block['history']=altered
        old='\n'.join(assign_string(Variable('history'),original))
        if old not in macro:raise RuntimeError('fault history assignment anchor missing')
        macro=macro.replace(old,'\n'.join(assign_string(Variable('history'),altered)),1)
        if kind=='partial':
            q=lambda p:String(str(p)).render()
            injection=f'''    f = FreeFile
    Open {q(directory/'partial-step.txt')} For Output As #f
    Print #f, "required steps before geometry executed"
    Close #f
    Err.Raise vbObjectError + 2960, "W3 injected required step", "controlled failure after partial history"
'''
            anchor='    CSTToolsStage = "rebuild"\n'
            assert macro.count(anchor)==1
            macro=macro.replace(anchor,anchor+injection,1)
        # Outer code is valid; intentional invalid inner text must be caught by
        # the in-session MacroCheckThis before AddToHistory, not by executing it.
        check_module(macro,spec['parameters'])
        write_bundle(directory,spec,altered,macro,program)
        closure=run_new_definition(exe,model,directory,macro,generated_profile='cst-a1-history-v2')
        require_closed(closure);closures.append(closure)
        return closure
    catalog=root/'project'/'control'/'definitions'
    old=root/'project'/'control'/'documents'/'old.json';old.parent.mkdir(parents=True,exist_ok=True)
    old.write_text('{"document_revision":"unchanged"}',encoding='ascii');before=old.read_bytes()
    service=SimpleNamespace(catalog=catalog,definition_editor=editor,installations={'local':executable})
    parent=dict(document_id='fault-'+kind,document_revision='unchanged',installation_ref='local')
    error=None
    try:build_candidate(service,parent,spec,'attempt',None,None)
    except ServiceError as exc:error=str(exc)
    if error is None or not closures or old.read_bytes()!=before:
        raise RuntimeError('failed candidate was not rejected or old state changed')
    directory=catalog/parent['document_id']/'attempt'/'verification-edit'/'saved'
    if (directory/'completed.txt').exists():raise RuntimeError('failure published completion')
    if kind=='syntax':
        diagnostic=injected_syntax_diagnostic(directory)
        source=read_saved_source(directory/'definition.cst',scope='root')
        diagnostic['saved_prefix']=verify_rejected_prefix(source,spec)
    else:
        if not (directory/'partial-step.txt').exists():raise RuntimeError('partial history stage not reached')
        diagnostic=None
    return dict(kind=kind,expected_failure=True,error=error,old_state_unchanged=True,
                closures=closures,diagnostic=diagnostic,workspace=str(directory))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-cst',action='store_true')
    parser.add_argument('--publish-gate',action='store_true')
    parser.add_argument('--cst-exe',type=Path,default=Path('D:/Program Files (x86)/CST Studio Suite 2022/CST DESIGN ENVIRONMENT.exe'))
    args=parser.parse_args()
    if not args.run_cst:parser.error('--run-cst required')
    with exclusive_probe(ROOT):
        fingerprint=generator_fingerprint()
        root=ROOT/'artifacts'/('winwrap-w23-'+uuid4().hex[:8]);root.mkdir()
        write_json_atomic(root/'intent.json',dict(sources=fingerprint,profile=PROFILE,
            tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),solver_start_calls=0))
        print('PROBE_ROOT='+str(root),flush=True)
        directory=root/'compile';directory.mkdir();nonce=uuid4().hex;rows=compile_cases(directory)
        for name,code,_ in rows:(directory/(name+'.bas')).write_text(code,encoding='utf-8')
        closure=run_new_definition(args.cst_exe,directory/'definition.cst',directory,render(directory,rows,nonce))
        require_closed(closure)
        compilation=evaluate(directory,rows,closure,nonce)
        write_json_atomic(directory/'acceptance.json',compilation)
        if not compilation['acceptance_passed']:raise RuntimeError('outer/history compile corpus failed')
        print('COMPILE_CONFIRMED',flush=True)
        failures=[]
        for kind in ('syntax','partial'):
            failures.append(negative(root,args.cst_exe,kind));print('FAULT_CONFIRMED='+kind,flush=True)
        positive=[]
        for axis in 'xyz':
            spec=spec_for(axis);directory=root/'project'/axis/'candidate';directory.mkdir(parents=True)
            history,projection=render_history(spec);nonce=uuid4().hex;macro=render_edit_macro(directory,spec,nonce)
            write_bundle(directory,spec,history,macro)
            closure=run_new_definition(args.cst_exe,directory/'definition.cst',directory,macro,generated_profile='cst-a1-history-v2')
            require_closed(closure)
            if (directory/'failed.txt').exists() or (directory/'completed.txt').read_text().strip()!=nonce:
                raise RuntimeError('positive generated candidate failed')
            source=read_saved_source(directory/'definition.cst',scope='root')
            verify_saved_program(source,spec)
            parameters=source.json('Model/Parameters.json')['parameters']
            if {r['name']:(r['expr'],r.get('descr')) for r in parameters}!={k:(v['expression'],v['description']) for k,v in spec['parameters'].items()}:
                raise RuntimeError('parameter expressions/descriptions changed')
            proof=NativeDefinitionVerifier()(directory/'definition.cst',projection,args.cst_exe)
            if proof['status']!='verified':raise RuntimeError('G03 failed')
            positive.append(dict(axis=axis,closure=closure,proof=proof,source_sha256=source.sha256))
            print('AXIS_CONFIRMED='+axis,flush=True)
        if generator_fingerprint()!=fingerprint:raise RuntimeError('generator changed during acceptance; no stamp')
        acceptance=dict(accepted=True,profile=PROFILE,sources=fingerprint,axes=['x','y','z'],solver_start_calls=0,
            standard_closed=True,compilation=compilation,failures=failures,positive=positive,after_cst=cst_processes())
        report=dict(date=datetime.now(timezone(timedelta(hours=8))).isoformat(),native_acceptance=acceptance,
                    raw_root=str(root),raw_artifacts_migration_guaranteed=False,
                    limits='Sub-only sampled A1/CST2022.5. Partial failure is deliberate Err.Raise injection, not a naturally failing CST setter.')
        write_json_atomic(root/'acceptance.json',report)
        if args.publish_gate:
            name='knowledge-base/winwrap-w23-'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')+'.json'
            write_json_atomic(ROOT/name,report)
            digest=hashlib.sha256(json.dumps(acceptance,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
            gate=dict(profile=PROFILE,accepted=True,sources=fingerprint,axes=['x','y','z'],solver_start_calls=0,
                      standard_closed=True,evidence_file=name,evidence_sha256=digest)
            write_json_atomic(ROOT/'data/winwrap-a1-calibration.json',gate)
        print(json.dumps(dict(root=str(root),accepted=True,published_gate=args.publish_gate,solver_start_calls=0)),flush=True)


if __name__=='__main__':main()
