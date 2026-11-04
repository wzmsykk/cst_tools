"""Serial owned GEO calibration. Explicit --run-cst; never touches user models."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from csttool.acceptance_session import exclusive_probe
from csttool.configuration import write_json_atomic,read_json
from csttool.definition_editing import changed_spec,prepare_candidate_artifacts,validate_candidate_completion
from csttool.native_definition_builder import run_new_definition
from csttool.saved_project_source import read_saved_source
from csttool.settings_projection import GEOMETRY_PROFILE,HISTORY
from csttool.winwrap_checks import generator_fingerprint


def construct(root,label,spec,executable,*,prelude=False):
    from csttool.definition_verifier import NativeDefinitionVerifier
    from csttool.managed_history import verify_saved_program
    directory=root/label
    if (directory/'acceptance.json').exists():
        record=read_json(directory/'acceptance.json');saved_dir=directory/'constructed'
        source=read_saved_source(saved_dir/'definition.cst',scope='root')
        if (read_json(saved_dir/'spec.json')!=spec or record['source_sha256']!=source.sha256
                or record['status']!='verified' or record['proof'].get('status')!='verified'):
            raise RuntimeError('cached native candidate evidence differs; not re-executed')
        _all_closed(directory);verify_saved_program(source,spec)
        print('RECONCILED '+label,flush=True)
        return dict(model_path=saved_dir/'definition.cst',directory=saved_dir),record
    directory.mkdir();nonce=uuid4().hex
    bundle=prepare_candidate_artifacts(directory/'constructed',spec,nonce)
    macro=bundle['macro']
    if prelude:
        macro=macro.replace('    CSTToolsStage = "parameters"\n',
            '    WCS.ActivateWCS "local"\n    WCS.SetOrigin 17, 23, 31\n    WCS.RotateWCS "w", 30\n    CSTToolsStage = "parameters"\n',1)
        (directory/'trusted-local-wcs-probe.bas').write_text(macro,encoding='ascii')
    closure=run_new_definition(executable,bundle['model_path'],bundle['directory'],macro,
        generated_profile=None if prelude else GEOMETRY_PROFILE)
    source=validate_candidate_completion(bundle,spec,closure);verify_saved_program(source,spec)
    proof=NativeDefinitionVerifier().verify_geometry(bundle['model_path'],spec,executable)
    record=dict(status='verified',source_sha256=source.sha256,closure=closure,proof=proof,
        workspace=str(directory.relative_to(ROOT)),spec_sha256=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest())
    write_json_atomic(directory/'acceptance.json',record)
    print('CASE '+label+' verified',flush=True)
    return bundle,record


def matrix_specimen():
    base=specimen();rows=[dict(op='set_parameters',values=base['parameters']),dict(op='ensure_component',component_id='vacuum'),
        dict(op='create_brick',object_id='brick',component_id='vacuum',material_id='Vacuum',
            bounds_mm=dict(x=['20-R','20+R'],y=['-R','R'],z=['-H/2','H/2']))]
    index=1
    for axis in 'xyz':
        for hollow in (False,True):
            center=dict(x=str(100*index),y='5',z='-3');index+=1
            rows.append(dict(op='create_cylinder',object_id='cyl_'+axis+str(int(hollow)),component_id='vacuum',material_id='Vacuum',
                axis=axis,transverse_center_mm=[center[a] for a in 'xyz' if a!=axis],
                axial_range_mm=[center[axis]+'-H/2',center[axis]+'+H/2'],outer_radius_mm='R',inner_radius_mm='R/2' if hollow else '0'))
    rows.append(dict(op='create_sphere',object_id='sphere',component_id='vacuum',material_id='Vacuum',center_mm=['1000','5','-3'],radius_mm='R/2'))
    return changed_spec({},dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=rows))


def _all_closed(directory):
    from csttool.acceptance_session import cst_processes
    states=list(directory.rglob('session-status.json'))
    if not states or any(read_json(p).get('exit_confirmed') is not True for p in states) or cst_processes():
        raise RuntimeError('serial acceptance stops: owned closure not confirmed')


def controlled_failure(root,spec,executable,*,stop=False):
    from csttool.history_program import partition
    from csttool.winwrap_checks import execution_definition_map
    from csttool.winwrap_emitter import String
    directory=root/('stop-between-blocks' if stop else 'second-step-failure')
    if directory.exists():
        _all_closed(directory)
        if not (directory/'candidate-diagnostic.json').exists() or not (directory/'failed.txt').exists():
            raise RuntimeError('partial fault probe without receipt; retained, not re-executed')
        diag=read_json(directory/'candidate-diagnostic.json');context=diag['context']
        if context is None or diag['context_error'] is not None:raise RuntimeError('fault receipt not reconcilable')
        return dict(status='verified',fault='reconciled prior explicit runtime fault',closure=read_json(directory/'session-status.json'),
            context=context,published=False)
    bundle=prepare_candidate_artifacts(directory,spec,uuid4().hex)
    program=bundle['program'];macro=bundle['macro']
    # First feature is complete, the following feature is the controlled fault
    # point. No unknown CST command or UI dialog is used to manufacture failure.
    first=next(i for i,b in enumerate(program) if ' GEO f_' in b['caption']);second=first+1
    anchor='    CSTToolsLastApplied = '+str(first)+'\n'
    if macro.count(anchor)!=1:raise RuntimeError('fault injection anchor differs')
    if stop:
        injection='    f = FreeFile\n    Open '+String(str(directory/'cancel.request')).render()+' For Output As #f\n    Print #f, "stop"\n    Close #f\n'
    else:
        injection=('    CSTToolsBlockIndex = '+str(second)+'\n    CSTToolsCaption = '+String(program[second]['caption']).render()+
            '\n    CSTToolsStage = "history-apply"\n    Err.Raise vbObjectError + 2960, "controlled GEO probe", "injected second feature failure"\n')
    macro=macro.replace(anchor,anchor+injection,1)
    bundle['macro']=macro;bundle['mapping']=execution_definition_map(spec,program,macro)
    write_json_atomic(directory/'source-map.json',bundle['mapping'])
    closure=run_new_definition(executable,bundle['model_path'],directory,macro,generated_profile=GEOMETRY_PROFILE)
    try:validate_candidate_completion(bundle,spec,closure)
    except ValueError as error:reason=str(error)
    else:raise RuntimeError('controlled GEO failure was adopted')
    _all_closed(directory)
    context=read_json(directory/'candidate-diagnostic.json')['context']
    if context['last_applied']!=first or context['block_index']!=second:
        raise RuntimeError('failed block diagnostic differs')
    return dict(status='verified',fault='controlled stop' if stop else 'explicit runtime Err.Raise, not a natural CST/solver failure',
        closure=closure,context=context,reason=reason,published=False)


def replay_parameters(root,bundle,spec,executable):
    from copy import deepcopy
    from csttool.definition_verifier import run_definition_probe,render_managed_probe
    from csttool.managed_history import verify_saved_program
    from csttool.definition_geometry import verify_managed_geometry_observation
    import shutil
    changed=deepcopy(spec);changed['parameters']['R']['expression']='12'
    directory=root/'parameter-rebuild';model=directory/'definition.cst'
    if directory.exists():
        _all_closed(directory)
        closure=read_json(directory/'session-status.json')
        nonce=dict(line.split('\t') for line in (directory/'identity.tsv').read_text(encoding='ascii').splitlines())['nonce']
        verify_saved_program(read_saved_source(model,scope='root'),changed)
        observed=verify_managed_geometry_observation(directory/'geometry.tsv',changed,model,nonce)
        return dict(status='verified',closure=closure,geometry=observed,preserved_expression=changed['parameters']['H']['expression'],reconciled=True)
    directory.mkdir()
    shutil.copyfile(bundle['model_path'],model);nonce=uuid4().hex
    macro=render_managed_probe(model,directory,nonce,changed)
    macro=macro.replace('    Dim f As Integer, message As String','    Dim f As Integer, message As String, names(0) As String, expressions(0) As String',1)
    macro=macro.replace('    Save\n','    names(0) = "R"\n    expressions(0) = "12"\n    StoreParameters(names, expressions)\n'+
        '    If Not Rebuild Then Err.Raise vbObjectError + 2993, "GEO replay", "rebuild failed"\n    Save\n',1)
    closure=run_definition_probe(executable,model,directory,macro)
    if closure.get('exit_confirmed') is not True or closure.get('exit_code')!=0 or (directory/'failed.txt').exists():
        raise RuntimeError('GEO parameter rebuild/close failed')
    verify_saved_program(read_saved_source(model,scope='root'),changed)
    observed=verify_managed_geometry_observation(directory/'geometry.tsv',changed,model,nonce)
    return dict(status='verified',closure=closure,geometry=observed,preserved_expression=changed['parameters']['H']['expression'])


def run_matrix(root,executable,reuse_simulation=None):
    from copy import deepcopy
    from csttool.definition_verifier import run_definition_probe,render_managed_probe
    from csttool.geometry_contract import native_solid_name
    import shutil
    cases={};multi=matrix_specimen();multi_bundle,c1=construct(root,'primitives',multi,executable)
    cases['C1']=dict(status='verified',primitives=c1)
    base=specimen()
    base=changed_spec(dict(spec=base),dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=[
        dict(op='define_selection_set',selection_id='volume',entity_kind='solid',members=['body'])]))
    baseline,base_record=construct(root,'baseline',base,executable)
    translated=changed_spec(dict(spec=base),dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=[
        dict(op='translate_solid',target_id='body',translation_mm=['3*R','-R','R/2'])]))
    _,c2=construct(root,'translated-local-wcs',translated,executable,prelude=True)
    cases['C2']=dict(status='verified',preexisting_wcs=dict(mode='local',origin_mm=[17,23,31],rotation_w_degrees=30),explicit_global=True,translation=c2)
    booleans=[]
    for operation,volume in (('union',10000),('difference',2000),('intersection',6000)):
        rows=[dict(op='set_parameters',values=base['parameters']),dict(op='ensure_component',component_id='vacuum')]
        for name,lo,hi in (('target','-R','R'),('tool','-R/2','3*R/2')):
            rows.append(dict(op='create_brick',object_id=name,component_id='vacuum',material_id='Vacuum',bounds_mm=dict(x=[lo,hi],y=['-R','R'],z=['-H/2','H/2'])))
        rows.append(dict(op='boolean_solids',operation=operation,target_id='target',tool_id='tool'))
        spec=changed_spec({},dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=rows))
        _,record=construct(root,'boolean-'+operation,spec,executable)
        facts=record['proof']['observations'][-1]['geometry']['objects']
        actual=next(o['volume_mm3'] for o in facts if o['object_id']=='target')
        if abs(actual-volume)>1e-4 or next(o['exists'] for o in facts if o['object_id']=='tool'):
            raise RuntimeError('analytic Boolean volume/tool consumption differs')
        booleans.append(dict(operation=operation,volume_mm3=actual,record=record))
    cases['C3']=dict(status='verified',overlap_cases=booleans,
        limits='Empty/disconnected/tangent outputs are not certified as a general CAD equivalence; positive-solid/readback gates still apply.')
    edge_cases=[]
    for label,operation,shift,wanted in (('disjoint-union','union',40,16000),('tangent-union','union',20,16000),
        ('disjoint-intersection','intersection',40,None),('tangent-intersection','intersection',20,None),('complete-subtraction','difference',0,None)):
        rows=[dict(op='set_parameters',values=base['parameters']),dict(op='ensure_component',component_id='vacuum')]
        for name,lo,hi in (('target','-R','R'),('tool',str(shift)+'-R',str(shift)+'+R')):
            rows.append(dict(op='create_brick',object_id=name,component_id='vacuum',material_id='Vacuum',bounds_mm=dict(x=[lo,hi],y=['-R','R'],z=['-H/2','H/2'])))
        rows.append(dict(op='boolean_solids',operation=operation,target_id='target',tool_id='tool'))
        edge=changed_spec({},dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=rows))
        try:
            _,record=construct(root,'edge-'+label,edge,executable)
        except ValueError as error:
            _all_closed(root/('edge-'+label))
            edge_cases.append(dict(case=label,outcome='rejected-before-publication',error=str(error),standard_closed=True))
        else:
            volume=next(o['volume_mm3'] for o in record['proof']['observations'][-1]['geometry']['objects'] if o['object_id']=='target')
            if wanted is None or abs(volume-wanted)>1e-4:raise RuntimeError('empty/tangent Boolean incorrectly verified')
            edge_cases.append(dict(case=label,outcome='verified-positive-solid',volume_mm3=volume,record=record))
    cases['C3']['edge_cases']=edge_cases
    original_hash=hashlib.sha256(baseline['model_path'].read_bytes()).hexdigest()
    fid=base['geometry']['features'][0]['feature_id'];replacement={k:deepcopy(v) for k,v in base['geometry']['features'][0].items() if k!='feature_id'}
    replacement['bounds_mm']['x']=['-2*R','2*R']
    edited=changed_spec(dict(spec=base),dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=[
        dict(op='update_feature',feature_id=fid,replacement=replacement)]))
    _,edit_record=construct(root,'edited-declaration',edited,executable)
    if edited['geometry']['features'][0]['feature_id']!=fid or hashlib.sha256(baseline['model_path'].read_bytes()).hexdigest()!=original_hash:
        raise RuntimeError('GEO edit damaged prior candidate or feature identity')
    cases['C4']=dict(status='verified',edited=edit_record,old_sha256=original_hash,same_caption_append='rejected offline; never used for edit')
    replay=replay_parameters(root,baseline,base,executable)
    replay_root=root/'primitives-replay';replay_root.mkdir(exist_ok=True)
    cases['C1']['parameter_rebuild']=replay_parameters(replay_root,multi_bundle,multi,executable)
    cases['C5']=dict(status='verified',selection_sets=edited['selection_sets'],parameter_rebuild=replay,
        removal_consumption='shared declaration/preflight fault suite; no native Group export')
    cases['C6']=dict(status='verified',legal_queries='post-history saved/reopened Model.run observers; existence/material/count/body type/volume/whole-structure and calculation box',
        per_solid_loose_bounds='unsupported; never called in structural macro',volume_units='mm^3, checked against analytic primitives',
        enumeration='production uses total count and exact names; no index-base assumption or public enumeration API')
    fault_spec=changed_spec(dict(spec=base),dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=[
        dict(op='create_sphere',object_id='second',component_id='vacuum',material_id='Vacuum',center_mm=['100','0','0'],radius_mm='R')]))
    failed=controlled_failure(root,fault_spec,executable)
    stopped=controlled_failure(root,fault_spec,executable,stop=True)
    cases['C7']=dict(status='verified',runtime_failure=failed,stage_stop=stopped,
        transaction_matrix='offline shared production tests cover response gaps, unknown exit and no replay; explicit runtime injection is not a natural solver failure')
    if reuse_simulation:
        path=Path(reuse_simulation).resolve(strict=True)
        if not path.is_relative_to(ROOT/'artifacts'):raise ValueError('reuse evidence must be an owned artifact')
        previous=read_json(path)
        if previous.get('accepted') is not True or previous.get('sources')!=generator_fingerprint() or previous.get('simulation',{}).get('status')!='verified':
            raise ValueError('simulation evidence source or acceptance differs')
        from csttool.application_service import ApplicationService
        definition=previous['simulation']['definition']
        app=ApplicationService(path.parent/'project',definition['project_id'],installations={'local':executable})
        if app.get_simulation_results('geo-solve')!=previous['simulation']['result']:
            raise ValueError('adopted real simulation result changed')
        app.inspect_definition('geo-pillbox',definition['definition_revision'])
        _all_closed(path.parent)
        cases['GEO-4']=dict(status='verified',evidence=str(path.relative_to(ROOT)),
            evidence_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),simulation=previous['simulation'])
        variants=[]
        for axis in 'xy':
            axis_root=root/('simulation-'+axis);axis_root.mkdir(exist_ok=True)
            spec=simulation_specimen();spec['geometry']['features'][0]['axis']=axis
            next(p for p in spec['postprocess'] if p['method_id']=='R_over_Q')['settings']['integration_line']['axis']=axis
            bundle=prepare_candidate_artifacts(axis_root/'constructed',spec,uuid4().hex)
            closure=run_new_definition(executable,bundle['model_path'],bundle['directory'],bundle['macro'],generated_profile=GEOMETRY_PROFILE)
            validate_candidate_completion(bundle,spec,closure)
            value=simulate(axis_root,bundle,spec,executable)
            write_json_atomic(axis_root/'acceptance.json',dict(status='verified',axis=axis,closure=closure,simulation=value,sources=generator_fingerprint()))
            variants.append(dict(axis=axis,closure=closure,simulation=value))
        cases['GEO-4']['axis_variants']=variants
        baseline_metrics={m['method_id']:m['value'] for m in previous['simulation']['result']['metrics']}
        for variant in variants:
            metrics={m['method_id']:m['value'] for m in variant['simulation']['result']['metrics']}
            if any(abs(metrics[k]-baseline_metrics[k])/abs(baseline_metrics[k])>.05 for k in ('Frequency','R_over_Q')):
                raise RuntimeError('rotated XYZ Pillbox operator agreement exceeds 5%')
        cases['GEO-4']['xyz_operator_relative_tolerance']=.05
    return cases


def specimen():
    return changed_spec({},dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=[
        dict(op='set_parameters',values=dict(R=dict(expression='10',description='radius',quantity='length'),
            H=dict(expression='2*R',description='height expression',quantity='length'))),
        dict(op='ensure_component',component_id='vacuum'),
        dict(op='create_brick',object_id='body',component_id='vacuum',material_id='Vacuum',
            bounds_mm=dict(x=['-R','R'],y=['-R','R'],z=['-H/2','H/2']))]))


def simulation_specimen():
    from test.definition_editing_test import configuration
    model=changed_spec({},dict(operation='apply_model_changes',geometry_profile='geometry-v1',changes=[
        dict(op='set_parameters',values=dict(R=dict(expression='100',description='radius',quantity='length'),
            H=dict(expression='2*R',description='height expression',quantity='length'))),
        dict(op='ensure_component',component_id='vacuum'),
        dict(op='create_cylinder',object_id='pillbox',component_id='vacuum',material_id='Vacuum',axis='z',
            transverse_center_mm=['0','0'],axial_range_mm=['-H/2','H/2'],outer_radius_mm='R',inner_radius_mm='0'),
        dict(op='set_background',material='PEC',padding_mm=[0]*6),
        dict(op='set_boundaries',faces=['electric']*6,symmetry=['none']*3)]))
    config=configuration();config['simulation']['mesh']['cells_per_wavelength']=2
    return changed_spec(dict(spec=model),dict(operation='configure_simulation',**config))


def simulate(root,bundle,spec,executable):
    import math
    from csttool.application_service import ApplicationService
    from csttool.definition_verifier import NativeDefinitionVerifier
    from csttool.execution_contract import StopIntent
    app=ApplicationService(root/'project','geo-acceptance-'+uuid4().hex,installations={'local':executable},
        definition_verifier=NativeDefinitionVerifier())
    definition=app.stage_definition('geo-pillbox',bundle['model_path'],'local',geometry_spec=spec,postprocess=spec['postprocess'])
    definition=app.verify_definition('geo-pillbox',definition['definition_revision'])
    if not definition['ready']:raise RuntimeError('GEO native simulation proof not ready')
    command=dict(kind='simulation',document_id='geo-pillbox',definition_revision=definition['definition_revision'])
    execution=app.execute_simulation(command,run_id='geo-solve',stop=StopIntent(),
        update=lambda **event:print('SIMULATION '+json.dumps(event,ensure_ascii=True),flush=True))
    execution.run(command)
    result=app.get_simulation_results('geo-solve')
    traces=list((app.project/'control/runs/geo-solve').glob('workers/*/*/lifecycle.log'))
    starts=sum(p.read_text(errors='replace').count('calling EigenmodeSolver.Start') for p in traces)
    metrics={m['method_id']:m['value'] for m in result['metrics']}
    expected=2.404825557695773*299792458/(2*math.pi*.1)/1e6
    if (abs(metrics['Frequency']-expected)/expected>.05 or not math.isfinite(metrics['R_over_Q'])
            or metrics['R_over_Q']<=0 or starts!=1 or execution.session_safety()!='confirmed-closed'):
        raise RuntimeError('GEO solver/metric/closure acceptance differs')
    return dict(status='verified',definition=definition,result=result,analytic_frequency_mhz=expected,
                frequency_tolerance=.05,solver_start_calls=starts,solver_trace_files=[str(p) for p in traces],session_safety=execution.session_safety())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-cst',action='store_true')
    parser.add_argument('--cst-exe',required=True,type=Path)
    parser.add_argument('--simulate',action='store_true',help='Owned small-mesh Pillbox solve through the shared service')
    parser.add_argument('--matrix',action='store_true',help='Serial C1-C7 owned native calibration')
    parser.add_argument('--reuse-simulation',type=Path,help='Revalidate a same-source Z receipt without repeating it, then solve X/Y variants')
    parser.add_argument('--publish-gate',action='store_true',help='Only after C1-C7, bind accepted target(s) to native evidence')
    parser.add_argument('--resume',type=Path,help='Reconcile same-source owned matrix receipts; never replay a partial native attempt')
    args=parser.parse_args()
    if not args.run_cst:parser.error('--run-cst required')
    if args.matrix and args.simulate:parser.error('--matrix and --simulate are separate acceptance paths')
    if args.resume and not args.matrix:parser.error('--resume requires --matrix')
    with exclusive_probe(ROOT):
        root=args.resume.resolve(strict=True) if args.resume else ROOT/'artifacts'/('geo234-native-'+uuid4().hex[:8])
        if args.resume:
            if not root.is_relative_to(ROOT/'artifacts') or not root.name.startswith('geo234-native-'):
                raise ValueError('resume requires an owned GEO matrix artifact')
            intent=read_json(root/'intent.json')
            if intent.get('operation')!='C1-C7' or intent.get('sources')!=generator_fingerprint():raise ValueError('resume source/intent differs')
        else:root.mkdir()
        print('PROBE_ROOT='+str(root),flush=True)
        (root/('tool-source-resume.py' if args.resume else 'tool-source.py')).write_bytes(Path(__file__).read_bytes())
        if args.publish_gate and not args.matrix:parser.error('--publish-gate requires --matrix')
        if args.matrix:
            fingerprint=generator_fingerprint()
            if not args.resume:
                write_json_atomic(root/'intent.json',dict(sources=fingerprint,operation='C1-C7',solver_start_calls_requested=2 if args.reuse_simulation else 0,
                    tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
            else:write_json_atomic(root/'resume.json',dict(sources=fingerprint,tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
            cases=run_matrix(root,args.cst_exe,args.reuse_simulation)
            if generator_fingerprint()!=fingerprint:raise RuntimeError('sources changed during native acceptance')
            evidence=dict(date='2026-11-04',sources=fingerprint,cases=cases,scope='CST2022 owned generated geometry; bounded native observations',
                tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),artifact_root=str(root.relative_to(ROOT)))
            write_json_atomic(root/'matrix-acceptance.json',evidence)
            if args.publish_gate:
                from csttool.winwrap_checks import GEO_NATIVE_PROFILE
                name='knowledge-base/geometry-calibration-20261104.json';write_json_atomic(ROOT/name,evidence)
                digest=hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
                write_json_atomic(ROOT/'data/geometry-calibration.json',dict(profile=GEO_NATIVE_PROFILE,accepted=True,sources=fingerprint,
                    targets=['geometry']+(['simulation'] if 'GEO-4' in cases else []),evidence_file=name,evidence_sha256=digest))
            print('MATRIX verified; targets='+str(['geometry']+(['simulation'] if 'GEO-4' in cases else [])),flush=True)
            return
        fingerprint=generator_fingerprint();nonce=uuid4().hex;spec=simulation_specimen() if args.simulate else specimen()
        write_json_atomic(root/'intent.json',dict(sources=fingerprint,profile=GEOMETRY_PROFILE,solver_start_calls_requested=1 if args.simulate else 0,
            tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
        bundle=prepare_candidate_artifacts(root/'constructed',spec,nonce)
        result=run_new_definition(args.cst_exe,bundle['model_path'],bundle['directory'],bundle['macro'],generated_profile=GEOMETRY_PROFILE)
        source=validate_candidate_completion(bundle,spec,result)
        from csttool.managed_history import verify_saved_program
        from csttool.definition_verifier import NativeDefinitionVerifier
        verify_saved_program(source,spec)
        simulation=simulate(root,bundle,spec,args.cst_exe) if args.simulate else None
        geometry=simulation['definition']['verification'] if simulation else NativeDefinitionVerifier().verify_geometry(bundle['model_path'],spec,args.cst_exe)
        text=source.text(HISTORY)
        (root/'saved-history.txt').write_text(text,encoding='utf-8')
        accepted=result.get('exit_confirmed') is True and result.get('exit_code')==0 and generator_fingerprint()==fingerprint
        write_json_atomic(root/'acceptance.json',dict(accepted=accepted,sources=fingerprint,source_sha256=source.sha256,
            closure=result,geometry=geometry,simulation=simulation,solver_start_calls=1 if simulation else 0,history_bytes=len(text.encode('utf-8'))))
        print(json.dumps(dict(accepted=accepted,closure=result,history=text[:5000]),ensure_ascii=True),flush=True)
        if not accepted:raise RuntimeError('GEO construction/standard close not confirmed')


if __name__=='__main__':main()
