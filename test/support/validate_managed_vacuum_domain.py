"""Opt-in real Manager/Managed domain registration, one small-mesh doublet."""
import argparse
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from test.support.validate_pillbox_full_domain import prepare_ideal,GEOMETRY,RADIUS,LENGTH
from test.managed_hom_ten_modes_fault_resume_integration_test import _config
from csttool.configuration import GlobalSettings,ProjectSettings,write_json_atomic,read_json
from csttool.cstmanager import CSTManager,SimulationTask
from csttool.managed_cstworker import ManagedCSTWorker
from csttool.field_artifacts import SamplingSpec,read_field
from csttool.vacuum_mode_tracking import VacuumTrackingDomain,load_tracking_snapshot,VacuumModeTracker
from csttool.mode_matching import MatchPolicy
from csttool.result_reconciliation import file_hash


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cst-exe',type=Path,required=True)
    parser.add_argument('--matching',action='store_true',help='Two small tasks and fixed-anchor matching')
    args=parser.parse_args()
    root=ROOT/'artifacts'/('managed-vacuum-domain-'+uuid4().hex[:8]);root.mkdir()
    print(f'ACCEPTANCE_ROOT={root}',flush=True)
    source=ROOT/'test/data/Pillbox/Pillbox.cst';before=file_hash(source)
    manager=None
    report={'source_sha256':before,'mesh':8,'nmodes':2}
    try:
        prepared=prepare_ideal(args.cst_exe,source,root/'prepare')
        pps=[{'method':'Frequency','resultName':f'frequency_{i}','params':{'iModeNumber':i}} for i in (1,2)]
        pconf=SimpleNamespace(currProjectDir=prepared.parent,
            settings=ProjectSettings(name='Pillbox domain acceptance',cst_filename=Path('input.cst')),
            get_postprocess_settings=lambda:pps)
        gconf=SimpleNamespace(settings=GlobalSettings().with_cst('2022',str(args.cst_exe)))
        params=_config(root/'unused','0',args.cst_exe,prepared)['paramList']+[{'name':'cell','type':'double'}]
        spec=SamplingSpec((-RADIUS,RADIUS,-RADIUS,RADIUS,-LENGTH/2,LENGTH/2),(64,64,64),'specified-domain')
        domain_options={'geometry_id':GEOMETRY,'sampling':spec.to_mapping(),'modes':[1,2]}
        if args.matching:
            domain_options['matching']={'reference_strategy':'first-valid',
                'policy':{'minimum_mac':.9,'minimum_margin':.05,'minimum_subspace_overlap':.99,
                          'maximum_frequency_change':.01},'sampling_evidence':'previous full-cylinder sampling study'}
        manager=CSTManager(gconf,pconf,params,maxTask=1,worker_factory=ManagedCSTWorker.create,
                           vacuum_domain=domain_options)
        result=manager.execute(SimulationTask({'nmodes':2,'fmin':780,'fmax':850,'cell':8},'domain-doublet'))
        report['result']=result
        assert result['TaskStatus']=='Success'
        assert result['DomainRegistration']['status']=='pending-after-stop'
        if args.matching:
            second=manager.execute(SimulationTask({'nmodes':2,'fmin':780,'fmax':850,'cell':8},'matching-doublet'))
            report['second_result']=second
            assert second['TaskStatus']=='Success'
        manager.stop();manager=None
        if args.matching:
            report['matching']=[read_json(r['DomainRegistration']['matching_report']) for r in (result,second)]
            assert [m['status'] for m in report['matching']]==['reference-established','matched']
        registration_path=Path(result['DomainRegistration']['path'])
        report['registration']=read_json(registration_path)
        assert report['registration']['status']=='registered'
        descriptor=read_json(result['DomainRegistration']['tracking_input'])
        domain=VacuumTrackingDomain(GEOMETRY,'PEC','Vacuum',True,'native preflight','native full bounds','prior sampling evidence')
        snapshot=load_tracking_snapshot(descriptor,domain,base=root)
        assert len(snapshot.fields)==2
        for field in snapshot.fields: read_field(field)
        report['tracking']=VacuumModeTracker(snapshot,domain,MatchPolicy(.9,.05,.99,
            maximum_frequency_change=.01)).evaluate(snapshot,root/'self-tracking.json')
        assert report['tracking']['status']=='matched'
        report['gate_passed']=True
        print('MANAGED_DOMAIN_GATE_PASSED=True',flush=True)
    except BaseException as error:
        report['failure']=f'{type(error).__name__}: {error}'
        raise
    finally:
        if manager is not None: manager.stop()
        report['source_unchanged']=file_hash(source)==before
        write_json_atomic(root/'report.json',report)
    assert report['source_unchanged']


if __name__=='__main__': main()
