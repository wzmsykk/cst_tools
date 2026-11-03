"""Shared project-definition and single-simulation services; no alternate worker loop."""
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import math
import os
from uuid import uuid4
from pathlib import Path
import re
import shutil

from .configuration import read_json, write_json_atomic
from .execution_snapshot import (ExecutionConfig,ExecutionBinding,ExecutionExpectation,
                                 read_snapshot_record,verify_execution_artifact)
from .project_run_lock import ProjectRunLock
from .run_store import RunStore
from .saved_project_source import read_saved_source
from .settings_projection import project_saved_settings


class ServiceError(ValueError):
    def __init__(self,code,reason):
        self.code=code
        super().__init__(code+': '+reason)


def validate_simulation_submission(payload):
    if (not isinstance(payload,dict) or set(payload)!={'kind','document_id','definition_revision'}
            or payload.get('kind')!='simulation'):
        raise ServiceError('INVALID_ARGUMENT','simulation accepts only document_id and definition_revision')
    for key in ('document_id','definition_revision'):
        if not isinstance(payload[key],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',payload[key]):
            raise ServiceError('INVALID_ARGUMENT','invalid '+key)


def _sha(path):
    if path.stat().st_size>256*1024*1024:
        raise ServiceError('RESOURCE_LIMIT','definition too large')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _proof_ready(proof,source_hash):
    return (isinstance(proof,dict) and proof.get('source_sha256')==source_hash
            and proof.get('scope')=='root' and proof.get('status')=='verified'
            and isinstance(proof.get('gates'),list) and all(isinstance(item,str) for item in proof['gates'])
            and set(proof['gates'])=={'saved-reopened','identity','settings','standard-close'})


def validate_project_creation(payload):
    if (not isinstance(payload,dict) or set(payload)!={'kind','operation','name','installation_ref','module','units'}
            or payload.get('kind')!='definition' or payload.get('operation')!='create_project'
            or payload.get('module')!='mws' or payload.get('units')!={'length':'mm','frequency':'MHz'}):
        raise ServiceError('INVALID_ARGUMENT','unsupported create_project definition')
    for key in ('name','installation_ref'):
        if not isinstance(payload[key],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',payload[key]):
            raise ServiceError('INVALID_ARGUMENT','invalid '+key)


class ApplicationService:
    def __init__(self,project,project_id,*,installations=None,definition_verifier=None,worker_factory=None,project_creator=None,definition_editor=None):
        self.project=Path(project).resolve()
        self.project_id=project_id
        self.catalog=self.project/'control/definitions'
        from .definition_verifier import NativeDefinitionVerifier
        self.definition_verifier=definition_verifier if definition_verifier is not None else NativeDefinitionVerifier()
        self.worker_factory=worker_factory
        self.project_creator=project_creator
        self.definition_editor=definition_editor
        if installations is None:
            from .cst_installations import discover_cst_installations
            installations={'cst-'+str(item.version)+'-'+hashlib.sha256(str(item.executable).encode()).hexdigest()[:12]:item.executable
                           for item in discover_cst_installations()}
        self.installations={key:Path(value).resolve() for key,value in installations.items()}

    def preflight_definition_operation(self,payload):
        if payload.get('operation')!='create_project':
            from .definition_editing import preflight_edit
            return preflight_edit(self,payload)
        return self.preflight_creation(payload)

    def execute_definition_operation(self,payload,*,operation_id,cancel_check=None,progress=None):
        if payload.get('operation')!='create_project':
            from .definition_editing import edit_document
            return edit_document(self,payload,operation_id=operation_id,cancel_check=cancel_check,progress=progress)
        return self.create_project(payload,operation_id=operation_id,cancel_check=cancel_check,progress=progress)

    def preflight_creation(self,payload):
        validate_project_creation(payload)
        if payload['installation_ref'] not in self.installations:
            raise ServiceError('INSTALLATION_NOT_FOUND','unknown authorized installation')
        str(self.project).encode('ascii')

    def create_project(self,payload,*,operation_id,cancel_check=None,progress=None):
        self.preflight_creation(payload)
        # The transaction owns the same project lock as simulation/verification.
        lock=ProjectRunLock(self.project);lock.acquire()
        try:
            from .definition_verifier import assert_definition_sessions_closed
            assert_definition_sessions_closed(self.catalog)
            operation=self._run_directory(operation_id)
            result_path=operation/'definition-result.json'
            if result_path.exists():
                if read_snapshot_record(operation/'definition-intent.json')['payload']!=payload:
                    raise ServiceError('REQUEST_CONFLICT','operation identity reused with different payload')
                return self.definition_operation_result(operation_id)
            if (operation/'definition-intent.json').exists():
                raise ServiceError('RUN_RECONCILIATION_REQUIRED','creation intent exists; do not recreate')
            name_path=(self.project/'control/document-names'/(payload['name']+'.json')).resolve()
            if not name_path.is_relative_to(self.project/'control/document-names'):
                raise ServiceError('INVALID_ARGUMENT','name catalog escapes project')
            if name_path.exists():raise ServiceError('DOCUMENT_EXISTS','project name already registered')
            document_id=uuid4().hex
            write_json_atomic(operation/'definition-intent.json',dict(payload=payload,document_id=document_id))
            directory=(self.catalog/document_id/operation_id/'verification-bootstrap'/'created').resolve()
            if not directory.is_relative_to(self.project/'control/definitions'):
                raise ServiceError('INVALID_ARGUMENT','bootstrap candidate escapes catalog')
            from .project_creation import NativeProjectCreator
            if cancel_check:cancel_check()
            proof=(self.project_creator or NativeProjectCreator(on_progress=progress))(directory,self.installations[payload['installation_ref']])
            if cancel_check:cancel_check()
            if proof.get('closure',{}).get('exit_confirmed') is not True or proof['closure'].get('exit_code')!=0:
                raise ServiceError('SETTING_UNVERIFIED','bootstrap closure unverified')
            source=read_saved_source(directory/'definition.cst',scope='root')
            history=source.text('Model/3D/Model.mod',encoding='utf-8')
            compact=re.sub(r'\s+','',history or '').lower()
            if compact.count('withunits.geometry"mm".frequency"mhz"endwith')!=1:
                raise ServiceError('SETTING_UNVERIFIED','generated units history was not saved exactly')
            # Only our empty-project unit block is checked here. Full settings,
            # live identity and publication readiness still require G03.

            descriptor=dict(document_id=document_id,name=payload['name'],installation_ref=payload['installation_ref'],
                source_sha256=source.sha256,units=payload['units'],state='empty',project_id=self.project_id)
            revision=hashlib.sha256(json.dumps(descriptor,sort_keys=True).encode()).hexdigest()
            record=dict(schema_version=1,**descriptor,document_revision=revision,
                model_path=str(directory/'definition.cst'),bootstrap=proof,ready=False)
            target=(self.project/'control/documents'/document_id).resolve()
            if not target.is_relative_to(self.project/'control/documents'):
                raise ServiceError('INVALID_ARGUMENT','document catalog escapes project')
            write_json_atomic(target/(revision+'.json'),record)
            write_json_atomic(target/'current.json',dict(document_revision=revision))
            write_json_atomic(name_path,dict(document_id=document_id))
            write_json_atomic(result_path,record)
            return record
        finally:lock.release()

    def inspect_model(self,document_id,document_revision):
        validate_simulation_submission(dict(kind='simulation',document_id=document_id,definition_revision=document_revision))
        directory=(self.project/'control/documents'/document_id).resolve()
        if not directory.is_relative_to(self.project/'control/documents'):
            raise ServiceError('INVALID_ARGUMENT','document escapes catalog')
        record=read_snapshot_record(directory/(document_revision+'.json'))
        if record.get('schema_version')==2:
            from .definition_editing import inspect_typed
            return inspect_typed(self,record,document_id,document_revision)
        required={'schema_version','ready','state','document_id','document_revision','name','installation_ref','source_sha256','units','project_id','model_path','bootstrap'}
        if (not required<=set(record) or type(record.get('schema_version')) is not int or record['schema_version']!=1
                or record.get('ready') is not False or record.get('state')!='empty' or not isinstance(record.get('model_path'),str)):
            raise ServiceError('DOCUMENT_INVALID','invalid empty document record')
        descriptor={key:record[key] for key in ('document_id','name','installation_ref','source_sha256','units','state','project_id')}
        if (record.get('project_id')!=self.project_id or record.get('document_id')!=document_id
                or record.get('document_revision')!=document_revision
                or hashlib.sha256(json.dumps(descriptor,sort_keys=True).encode()).hexdigest()!=document_revision):
            raise ServiceError('STALE_DOCUMENT','document metadata changed')
        path=Path(record['model_path']).resolve()
        if not path.is_relative_to(self.catalog) or _sha(path)!=record['source_sha256']:
            raise ServiceError('STALE_DOCUMENT','document model changed')
        return record

    def definition_operation_result(self,run_id):
        if (self._run_directory(run_id)/'definition-abandoned.json').exists():
            raise ServiceError('OPERATION_ABANDONED','uncommitted definition retained as diagnostics; no model was published')
        try:result=read_snapshot_record(self._run_directory(run_id)/'definition-result.json')
        except FileNotFoundError as error:raise ServiceError('OPERATION_NOT_READY','definition operation has no published result') from error
        return self.inspect_model(result['document_id'],result['document_revision'])

    def reconcile_project_creation(self,run_id):
        """Repair a committed document's response gap, never repeat bootstrap."""
        intent=read_snapshot_record(self._run_directory(run_id)/'definition-intent.json')
        if intent.get('payload',{}).get('operation')!='create_project':
            from .definition_editing import reconcile_edit
            return reconcile_edit(self,run_id)
        lock=ProjectRunLock(self.project);lock.acquire()
        try:
            directory=self._run_directory(run_id)
            if (directory/'definition-result.json').exists():return self.definition_operation_result(run_id)
            intent=read_snapshot_record(directory/'definition-intent.json')
            validate_project_creation(intent['payload'])
            document_id=intent['document_id']
            validate_simulation_submission(dict(kind='simulation',document_id=document_id,definition_revision='pending'))
            name_path=self.project/'control/document-names'/(intent['payload']['name']+'.json')
            if not name_path.exists() or read_snapshot_record(name_path).get('document_id')!=document_id:
                raise ServiceError('RUN_RECONCILIATION_REQUIRED','unpublished candidate retained; creation is not repeated')
            current=read_snapshot_record(self.project/'control/documents'/document_id/'current.json')
            record=self.inspect_model(document_id,current['document_revision'])
            if (record['name']!=intent['payload']['name'] or record['installation_ref']!=intent['payload']['installation_ref']
                    or record['bootstrap']['closure'].get('exit_confirmed') is not True
                    or record['bootstrap']['closure'].get('exit_code')!=0):
                raise ServiceError('SETTING_UNVERIFIED','committed bootstrap proof mismatch')
            write_json_atomic(directory/'definition-result.json',record)
            return record
        finally:lock.release()

    def _directory(self,document,revision):
        validate_simulation_submission(dict(kind='simulation',document_id=document,definition_revision=revision))
        directory=(self.catalog/document/revision).resolve()
        if not self.catalog.resolve().is_relative_to(self.project) or not directory.is_relative_to(self.catalog.resolve()):
            raise ServiceError('INVALID_ARGUMENT','definition escapes catalog')
        return directory

    def _run_directory(self,run_id):
        if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',run_id):
            raise ServiceError('INVALID_ARGUMENT','invalid run identity')
        directory=(self.project/'control/runs'/run_id).resolve()
        if not directory.is_relative_to(self.project):
            raise ServiceError('INVALID_ARGUMENT','run directory escapes project')
        return directory

    def stage_definition(self,document_id,source_project,installation_ref,*,postprocess=None):
        """Owner-side candidate registration, NOT a public arbitrary-path tool.

        The trusted definition backend must supply G03 proof. Missing backend leaves
        a pending definition; no request field can assert ready or replace proof.
        """
        if installation_ref not in self.installations:
            raise ServiceError('INSTALLATION_NOT_FOUND','unknown authorized installation')
        source=read_saved_source(source_project,scope='root')
        projection=project_saved_settings(source)
        if projection.status!='resolved' or projection.missing_fields:
            raise ServiceError('SETTING_UNVERIFIED','incomplete or unsupported saved definition')
        values=projection.fields
        if (values['solver.selected_mesh']!='Tet' or values['solver.selected_method']!='Default'
                or values['solver.mesh_adaptation.tet'] is not False or not values['solver.losses_postprocess_only']
                or values['mesh.tet.version']!=1 or values['mesh.tet.policy']!='cellsperwavelength'
                or not values['solver.frequency_target.enabled']
                or Decimal(projection.exact_values['solver.frequency_target.value_mhz'])
                   !=Decimal(projection.exact_values['solver.frequency_range.min_mhz'])):
            raise ServiceError('UNSUPPORTED_CAPABILITY','not an A1 single-simulation definition')
        config=ExecutionConfig(values['solver.selected_method'],values['solver.selected_mesh'],
             values['solver.frequency_target.enabled'],projection.exact_values['solver.frequency_target.value_mhz'],
             values['solver.mesh_adaptation.tet'],values['solver.requested_modes'])
        if config.requested_modes!=1:
            raise ServiceError('UNSUPPORTED_CAPABILITY','A1 capture currently requires one mode')
        if postprocess is None:
            postprocess=[dict(metric_id='frequency',method_id='Frequency',settings=dict(mode=dict(selection='one',index=1))),
                dict(metric_id='rq',method_id='R_over_Q',settings=dict(mode=dict(selection='one',index=1),
                    integration_line=dict(axis=values['geometry.cylinder.axis'],offset_mm=[0,0,0],beta=1,range='full')))]
        from .definition_editing import SCHEMA
        from jsonschema import Draft202012Validator
        validator=Draft202012Validator({'$defs':SCHEMA['$defs'],'$ref':'#/$defs/PPS'})
        if (next(validator.iter_errors(postprocess),None) or len({p['metric_id'] for p in postprocess})!=2
                or {p['method_id'] for p in postprocess}!={'Frequency','R_over_Q'}
                or next(p for p in postprocess if p['method_id']=='R_over_Q')['settings']['integration_line']['axis']!=values['geometry.cylinder.axis']):
            raise ServiceError('INVALID_ARGUMENT','unsupported definition postprocess')
        descriptor=dict(document_id=document_id,source_sha256=source.sha256,installation_ref=installation_ref,
                        config=asdict(config),axis=values['geometry.cylinder.axis'],postprocess=postprocess)
        revision=hashlib.sha256(json.dumps(descriptor,sort_keys=True).encode()).hexdigest()
        directory=self._directory(document_id,revision)
        lock=ProjectRunLock(self.project);lock.acquire()
        try:
            if (directory/'definition.json').exists():
                return self.inspect_definition(document_id,revision)
            directory.mkdir(parents=True,exist_ok=True)
            candidate=directory/'definition.cst'
            shutil.copyfile(source.path,candidate)
            if _sha(candidate)!=source.sha256:
                raise ServiceError('STALE_DOCUMENT','source changed while staging')
            proof=None
            if self.definition_verifier is not None and getattr(self.definition_verifier,'verify_on_stage',True):
                proof=self.definition_verifier(candidate,projection,self.installations[installation_ref])
            if _sha(candidate)!=source.sha256:
                raise ServiceError('STALE_DOCUMENT','verifier modified the frozen candidate')
            ready=_proof_ready(proof,source.sha256)
            record=dict(schema_version=2,project_id=self.project_id,definition_revision=revision,
                        **descriptor,verification=proof,ready=ready)
            write_json_atomic(directory/'definition.json',record)
            return record
        finally:
            lock.release()

    def inspect_definition(self,document_id,revision):
        directory=self._directory(document_id,revision)
        try:
            record=read_snapshot_record(directory/'definition.json')
        except FileNotFoundError as exc:
            raise ServiceError('DEFINITION_NOT_FOUND','definition not registered') from exc
        except ValueError as exc:
            raise ServiceError('DEFINITION_INVALID','definition metadata cannot be decoded') from exc
        required={'schema_version','project_id','document_id','definition_revision','source_sha256',
                  'installation_ref','config','axis','postprocess','verification','ready'}
        if (not required<=set(record) or type(record.get('schema_version')) is not int or record['schema_version']!=2
                or type(record.get('ready')) is not bool or not isinstance(record.get('config'),dict)):
            raise ServiceError('DEFINITION_INVALID','definition metadata schema invalid')
        if (record.get('project_id')!=self.project_id or record.get('document_id')!=document_id
                or record.get('definition_revision')!=revision or _sha(directory/'definition.cst')!=record['source_sha256']):
            raise ServiceError('STALE_DOCUMENT','definition identity/hash changed')
        descriptor={key:record[key] for key in ('document_id','source_sha256','installation_ref','config','axis','postprocess')}
        if hashlib.sha256(json.dumps(descriptor,sort_keys=True).encode()).hexdigest()!=revision:
            raise ServiceError('STALE_DOCUMENT','definition metadata changed')
        return record

    def verify_definition(self,document_id,revision):
        """Explicit owner operation, not a read query; no default fake G03 proof."""
        if self.definition_verifier is None:
            raise ServiceError('SETTING_UNVERIFIED','native definition verifier not registered')
        lock=ProjectRunLock(self.project);lock.acquire()
        try:
            record=self.inspect_definition(document_id,revision)
            candidate=self._directory(document_id,revision)/'definition.cst'
            projection=project_saved_settings(read_saved_source(candidate,scope='root'))
            record.update(ready=False,verification=None)
            write_json_atomic(candidate.parent/'definition.json',record)
            proof=self.definition_verifier(candidate,projection,self.installations[record['installation_ref']])
            if _sha(candidate)!=record['source_sha256']:
                raise ServiceError('STALE_DOCUMENT','verifier modified the frozen definition')
            record.update(verification=proof,ready=_proof_ready(proof,record['source_sha256']))
            write_json_atomic(candidate.parent/'definition.json',record)
            return record
        finally:lock.release()

    def preflight(self,payload):
        validate_simulation_submission(payload)
        try:str(self.project).encode('ascii')
        except UnicodeEncodeError as exc:
            raise ServiceError('UNSUPPORTED_CAPABILITY','native capture currently requires ASCII project paths') from exc
        from .definition_verifier import assert_definition_sessions_closed
        try:assert_definition_sessions_closed(self.catalog)
        except ValueError as exc:raise ServiceError('RECOVERY_REQUIRED',str(exc)) from exc
        record=self.inspect_definition(payload['document_id'],payload['definition_revision'])
        if not record['ready'] or not _proof_ready(record.get('verification'),record['source_sha256']):
            raise ServiceError('DEFINITION_NOT_READY','G03 verification backend has not confirmed this definition')
        if record['installation_ref'] not in self.installations:
            raise ServiceError('INSTALLATION_NOT_FOUND','authorized installation no longer available')
        return record

    def execute_simulation(self,payload,*,run_id,stop,update):
        if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',run_id):
            raise ServiceError('INVALID_ARGUMENT','invalid owner run identity')
        record=self.preflight(payload)
        directory=self._directory(record['document_id'],record['definition_revision'])
        execution=SingleSimulationExecution(self,record,directory,run_id,stop,update)
        return execution

    def get_simulation_results(self,run_id,result_revision=None):
        if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',run_id):
            raise ServiceError('INVALID_ARGUMENT','invalid run identity')
        path=self._run_directory(run_id)/'simulation-result.json'
        if not path.exists():
            raise ServiceError('RESULT_NOT_READY','no adopted single-simulation result')
        result=read_json(path)
        if result.get('run_id')!=run_id:
            raise ServiceError('RESULT_INVALID','result run identity mismatch')
        if (result['capture']['binding']['project_id']!=self.project_id
                or result['capture']['task_id']!=result['task_id']):
            raise ServiceError('RESULT_INVALID','result capture identity mismatch')
        if _sha(path.parent/'simulation-received.json')!=result['received_sha256']:
            raise ServiceError('RESULT_INVALID','received results changed after adoption')
        if result.get('schema_version')==2:
            from .result_provenance import read_postprocess_provenance
            provenance=read_postprocess_provenance(path.parent,result['postprocess_provenance_sha256'])
            if provenance!=result['postprocess_definition']:
                raise ServiceError('RESULT_INVALID','result operator context differs from frozen provenance')
        snapshot=Path(result['snapshot']).resolve()
        if not snapshot.is_relative_to(self.project) or _sha(snapshot)!=result['snapshot_sha256']:
            raise ServiceError('RESULT_INVALID','result snapshot missing or changed')
        revision=_sha(path)
        if result_revision is not None and result_revision!=revision:
            raise ServiceError('RESULT_CHANGED','requested result revision does not match')
        return dict(result,result_revision=revision)

    def export_simulation_results(self,run_id,result_revision,formats):
        """Owner-side deterministic export of adopted data; never executes CST."""
        if (not isinstance(formats,list) or not formats
                or any(not isinstance(item,str) or item not in ('json','csv') for item in formats)
                or len(set(formats))!=len(formats)):
            raise ServiceError('INVALID_ARGUMENT','formats must be a unique nonempty json/csv array')
        lock=ProjectRunLock(self.project);lock.acquire()
        try:
            result=self.get_simulation_results(run_id,result_revision)
            directory=(self.project/'result/exports'/run_id/result['result_revision']).resolve()
            if not directory.is_relative_to(self.project/'result/exports'):
                raise ServiceError('INVALID_ARGUMENT','export escapes project')
            directory.mkdir(parents=True,exist_ok=True)
            artifacts=[]
            for format in sorted(formats):
                path=directory/('results.'+format)
                if format=='json':
                    content=json.dumps(result,ensure_ascii=False,sort_keys=True,allow_nan=False,indent=2)+'\n'
                else:
                    import csv,io
                    stream=io.StringIO(newline='')
                    writer=csv.writer(stream,lineterminator='\n')
                    writer.writerow(['run_id','definition_revision','result_revision','task_id','mode_index','metric_id','value','unit','status'])
                    for metric in result['metrics']:
                        writer.writerow([run_id,result['definition_revision'],result['result_revision'],result['task_id'],1,
                            metric['metric_id'],metric['value'],metric['unit'],metric['status']])
                    content=stream.getvalue()
                raw=content.encode('utf-8')
                if path.is_symlink() or not path.resolve().is_relative_to(directory):
                    raise ServiceError('INVALID_ARGUMENT','export file escapes directory')
                if path.exists():
                    if path.read_bytes()!=raw:raise ServiceError('RESULT_CHANGED','existing export changed')
                else:
                    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
                    try:
                        with temporary.open('xb') as stream:stream.write(raw)
                        os.replace(temporary,path)
                    finally:
                        temporary.unlink(missing_ok=True)
                artifacts.append(dict(path=str(path.relative_to(self.project)),relative_to='project',
                    sha256=hashlib.sha256(raw).hexdigest(),size_bytes=len(raw),format=format))
            return dict(run_id=run_id,result_revision=result['result_revision'],artifacts=artifacts)
        finally:lock.release()

    def reconcile_simulation(self,run_id):
        """Owner-only reconciliation of ACKed, closed, captured data; no CST calls."""
        if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',run_id):
            raise ServiceError('INVALID_ARGUMENT','invalid run identity')
        lock=ProjectRunLock(self.project);lock.acquire()
        try:
            run_directory=self._run_directory(run_id)
            intent=read_snapshot_record(run_directory/'simulation-intent.json')
            manifest=read_snapshot_record(run_directory/'run.json')
            if manifest.get('run_id')!=run_id or Path(manifest.get('project','')).resolve()!=self.project:
                raise ServiceError('RESULT_INVALID','RunStore owner identity mismatch')
            store=RunStore(self.project,run_directory)
            if intent['run_id']!=run_id:
                raise ServiceError('RESULT_INVALID','run identity mismatch')
            published=self.get_simulation_results(run_id) if (store.directory/'simulation-result.json').exists() else None
            received=read_snapshot_record(store.directory/'simulation-received.json')
            closed=read_snapshot_record(store.directory/'simulation-closure.json')
            identity=intent['execution_identity'];task=identity['task_id']
            definition=self.inspect_definition(intent['document_id'],intent['definition_revision'])
            if (closed.get('standard_closed') is not True or closed.get('task_id')!=task
                    or received.get('task_id')!=task or received.get('run_id')!=run_id
                    or received.get('definition_revision')!=intent['definition_revision']):
                raise ServiceError('RUN_RECONCILIATION_REQUIRED','matching ACK/close evidence missing')
            task_root=store.directory/'tasks'/task
            state=read_snapshot_record(task_root/'attempt.json')
            if state.get('event') not in ('acknowledged','algorithm_adopted'):
                raise ServiceError('RUN_RECONCILIATION_REQUIRED','ACK not confirmed')
            native=read_snapshot_record(task_root/'execution/intent.json')
            capture=read_snapshot_record(task_root/'execution/receipt.json')
            snapshot=read_snapshot_record(task_root/'execution/snapshot.json')
            if (capture.get('task_id')!=task or capture.get('nonce')!=native['nonce']
                    or native['project_id']!=self.project_id or native['definition_revision']!=identity['definition_revision']
                    or native['definition_sha256']!=identity['definition_sha256']
                    or native['definition_sha256']!=definition['source_sha256']
                    or native['config']!=definition['config']
                    or capture['binding']['project_id']!=self.project_id
                    or capture['binding']['attempt_id']!=task
                    or capture['binding']['definition_revision']!=native['definition_revision']):
                raise ServiceError('RESULT_INVALID','native attempt binding mismatch')
            digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if digest!=capture['snapshot_sha256']:
                raise ServiceError('RESULT_INVALID','native snapshot changed')
            expected=ExecutionExpectation(ExecutionBinding(**capture['binding']),ExecutionConfig(**native['config']),
                native['created_utc'],snapshot['observed_at'],capture['result_success'])
            report=verify_execution_artifact(expected,snapshot,database_path=task_root/'execution/native-Model.db')
            if not report.database_verified or report.status!='execution-snapshot-match' or not report.fields['result_success']:
                raise ServiceError('RESULT_INVALID','archived execution evidence unverified')
            if published is not None:
                self._mark_received_adopted(store,received,intent)
                return published
            self._publish_result(store,received,capture)
            # Recovery has the same public DTO on first repair and later reads.
            return self.get_simulation_results(run_id)
        finally:lock.release()

    def _mark_received_adopted(self,store,received,intent):
        """Same adoption barrier as HOM/batch, after durable single-result commit."""
        task=received['task_id']
        artifacts=read_snapshot_record(store.directory/'tasks'/task/'artifacts.json')
        reference=artifacts.get('received',{})
        if reference.get('relative_to')!='project' or not isinstance(reference.get('path'),str):
            raise ServiceError('RESULT_INVALID','registered protocol receipt missing')
        path=(self.project/reference['path']).resolve()
        if not path.is_relative_to(self.project):
            raise ServiceError('RESULT_INVALID','protocol receipt escapes project')
        receipt=read_snapshot_record(path)
        if (receipt.get('task_id')!=task or receipt.get('session_id')!=intent['execution_identity']['session_id']
                or receipt.get('status')!='Success' or receipt.get('phase') not in ('acknowledged','algorithm_adopted')
                or receipt.get('postprocess')!=received['postprocess']
                or receipt.get('snapshot_sha256')!=received['snapshot_sha256']):
            raise ServiceError('RESULT_INVALID','protocol adoption identity/value/hash mismatch')
        from .checkpoint_adoption import mark_adopted
        mark_adopted(path,store,task)

    def _publish_result(self,store,received,capture):
        if (received.get('status')!='Success' or not isinstance(received.get('postprocess'),list) or len(received['postprocess'])!=2
                or any(not isinstance(item,dict) or 'value' not in item or item.get('resultName') not in ('frequency','rq')
                       for item in received['postprocess'])):
            raise ServiceError('RESULT_INVALID','expected exactly Frequency and RQ')
        metrics={item['resultName']:item['value'] for item in received['postprocess']}
        path=Path(received['snapshot']).resolve()
        if (received['status']!='Success' or set(metrics)!={'frequency','rq'}
                or any(type(v) not in (float,int) or not math.isfinite(v) or v<=0 for v in metrics.values())
                or not path.is_relative_to(self.project/'result/simulation'/received['run_id'])
                or _sha(path)!=received['snapshot_sha256']):
            raise ServiceError('RESULT_INVALID','required Frequency/RQ/snapshot unavailable')
        intent=read_json(store.directory/'simulation-intent.json')
        from .result_provenance import read_postprocess_provenance
        provenance=read_postprocess_provenance(store.directory,intent['postprocess_provenance_sha256'])
        if provenance['source_sha256']!=intent['execution_identity']['definition_sha256']:
            raise ServiceError('RESULT_INVALID','operator source differs from execution definition')
        result=dict(schema_version=2,run_id=received['run_id'],definition_revision=received['definition_revision'],
            task_id=received['task_id'],status='success',frequency_mhz=metrics['frequency'],rq_ohm=metrics['rq'],
            snapshot=str(path),snapshot_sha256=received['snapshot_sha256'],capture=capture,
            received_sha256=_sha(store.directory/'simulation-received.json'),
            mode_index=1,session_id=intent['execution_identity']['session_id'],
            postprocess_definition=provenance,postprocess_provenance_sha256=intent['postprocess_provenance_sha256'],
            execution_active=False,session_safety='confirmed-closed',metrics=[dict(metric_id=item['metric_id'],method_id=item['method_id'],
                value=metrics['frequency' if item['method_id']=='Frequency' else 'rq'],unit='MHz' if item['method_id']=='Frequency' else 'ohm',
                status='success') for item in provenance['requested_postprocess']])
        store.ensure_adopted(received['task_id'],definition_revision=received['definition_revision'])
        write_json_atomic(store.directory/'simulation-result.json',result)
        self._mark_received_adopted(store,received,intent)
        return result


class SingleSimulationExecution:
    """Adapter over ManagedCSTWorker, RunStore and the existing project lock."""
    def __init__(self,service,definition,directory,run_id,stop,update):
        self.service,self.definition,self.directory=service,definition,directory
        self.project=service.project
        self.run_id,self.stop,self.update=run_id,stop,update
        self.worker=None
        self._recovery=False
        self._safety='confirmed-closed'
        self._log=None
        self._overview_handler=None

    def run(self,payload):
        self.service.preflight(payload)
        lock=ProjectRunLock(self.project);lock.acquire()
        try:self._run_locked(payload)
        finally:
            try:
                if self._log is not None:
                    try:
                        if self._overview_handler is not None:
                            self._log.logger.removeHandler(self._overview_handler)
                            self._overview_handler.close()
                    finally:self._log.close()
            finally:lock.release()

    def _run_locked(self,payload):
        from .managed_cstworker import ManagedCSTWorker
        from .worker_models import WorkerConfig
        from .project_session_recovery import project_runtime_directory
        store=RunStore(self.project,self.service._run_directory(self.run_id),run_id=self.run_id)
        outcome=store.directory/'simulation-result.json'
        if outcome.exists() or (store.directory/'simulation-intent.json').exists():
            raise ServiceError('RUN_RECONCILIATION_REQUIRED','query/reconcile the existing run; never replay Solver')
        write_json_atomic(store.directory/'simulation-intent.json',dict(document_id=self.definition['document_id'],
            definition_revision=self.definition['definition_revision'],run_id=self.run_id,dispatch_intent=False))
        from .logging_config import ApplicationLogSession,ContextLogger
        from .run_overview import RunOverview,RunOverviewHandler
        self.overview=RunOverview(self.project,self.run_id,'单次仿真',settings=dict(
            kind='simulation',document_id=self.definition['document_id'],definition_revision=self.definition['definition_revision']))
        self._log=ApplicationLogSession(self.overview.directory/'application.log',console=False)
        self._overview_handler=RunOverviewHandler(self.overview)
        self._log.logger.addHandler(self._overview_handler)
        logger=ContextLogger(self._log.logger,dict(project=str(self.project),run_id=self.run_id,
            document_id=self.definition['document_id'],definition_revision=self.definition['definition_revision']))
        write_json_atomic(self.overview.directory/'execution-index.json',dict(run_store=store.reference(store.directory),
            definition=store.reference(self.directory/'definition.json')))
        self.update(log_directory=str(self.overview.directory))
        logger.info('单次仿真执行已开始',extra={'event':'SIMULATION_START','phase':'prepare'})
        error=None
        dispatched=False
        try:
            self.stop.check()
            self.update(state='PREPARING',phase='simulation-worker',total_tasks=1)
            config=WorkerConfig(project_runtime_directory(self.project)/('worker_single_'+self.run_id),self.project/'result/simulation'/self.run_id,
                self.service.installations[self.definition['installation_ref']],self.directory/'definition.cst',(),
                postprocess=(dict(resultName='frequency',method='Frequency',params=dict(iModeNumber=1)),
                    dict(resultName='rq',method='R_over_Q',params=dict(iModeNumber=1,axis=self.definition['axis'],
                         xoffset=0,yoffset=0,zoffset=0))),
                run_directory=store.directory,project_directory=self.project,
                execution_config=ExecutionConfig(**self.definition['config']),execution_project_id=self.service.project_id,
                execution_definition_revision=self.definition['definition_revision'],
                execution_definition_sha256=self.definition['source_sha256'])
            self._safety='unknown';self._recovery=True
            self.worker=(self.service.worker_factory or ManagedCSTWorker)('single',config,logger=logger)
            identity=self.worker.execution_identity
            if identity['definition_sha256']!=self.definition['source_sha256'] or identity['project_id']!=self.service.project_id:
                raise ServiceError('STALE_DOCUMENT','worker definition identity mismatch')
            from .result_provenance import freeze_postprocess_provenance
            provenance_hash=freeze_postprocess_provenance(self.directory/'definition.cst',self.definition['axis'],self.worker,store.directory,
                self.definition['postprocess'])
            write_json_atomic(store.directory/'simulation-intent.json',dict(document_id=self.definition['document_id'],
                definition_revision=self.definition['definition_revision'],run_id=self.run_id,execution_identity=identity,
                dispatch_intent=False,postprocess_provenance_sha256=provenance_hash))
            self._safety='running'
            if self.stop.is_set():
                self.worker.request_stop();self.stop.check()
            self.update(state='RUNNING',phase='single-simulation')
            write_json_atomic(store.directory/'simulation-intent.json',dict(document_id=self.definition['document_id'],
                definition_revision=self.definition['definition_revision'],run_id=self.run_id,execution_identity=identity,
                dispatch_intent=True,postprocess_provenance_sha256=provenance_hash))
            dispatched=True
            result=self.worker.run_task('single-simulation',params={})
            receipt_path=Path(result.receipt_path).resolve() if result.receipt_path else None
            if receipt_path is None or not receipt_path.is_relative_to(self.project):
                raise ServiceError('RESULT_INVALID','protocol receipt missing')
            protocol_receipt=read_snapshot_record(receipt_path)
            if (protocol_receipt.get('task_id')!=result.task_id or protocol_receipt.get('phase')!='acknowledged'
                    or protocol_receipt.get('status')!=result.status or protocol_receipt.get('postprocess')!=result.postprocess
                    or protocol_receipt.get('session_id')!=identity['session_id']):
                raise ServiceError('RESULT_INVALID','protocol result does not match acknowledged task')
            if result.status != 'Success':
                from .runtime_protocol import ErrorCode
                failure = str(result.failure or protocol_receipt.get('failure') or
                    'CST task failed; inspect the preserved completion and lifecycle evidence')
                code = failure.partition(':')[0]
                if code not in {item.value for item in ErrorCode}: code = 'TASK_FAILED'
                raise ServiceError(code, failure)
            expected_snapshot=protocol_receipt.get('snapshot_sha256')
            if result.status=='Success' and (not result.snapshot or _sha(Path(result.snapshot))!=expected_snapshot):
                raise ServiceError('RESULT_INVALID','snapshot differs from the acknowledged receipt')
            received=dict(schema_version=1,run_id=self.run_id,definition_revision=self.definition['definition_revision'],
                task_id=result.task_id,status=result.status,postprocess=result.postprocess,
                snapshot=str(result.snapshot) if result.snapshot else None,
                snapshot_sha256=expected_snapshot)
            write_json_atomic(store.directory/'simulation-received.json',received)
        except Exception as exc:
            error=exc
        finally:
            try:
                if self.worker is not None:
                    self.worker.stop()
                    self._safety='confirmed-closed'
                    self._recovery=False
                    write_json_atomic(store.directory/'simulation-closure.json',dict(run_id=self.run_id,
                        task_id=self.worker.execution_identity['task_id'],standard_closed=True))
            except Exception as exc:
                self._recovery=True;self._safety='unknown'
                if error is None:error=exc
            try:
                if self.worker is not None and dispatched:
                    capture=self.worker.finalize_execution_capture()
                    if error is None:
                        if (capture['status']!='execution-snapshot-match' or not capture['result_success']
                                or capture['task_id']!=result.task_id or capture['binding']['attempt_id']!=result.task_id
                                or capture['binding']['project_id']!=self.service.project_id
                                or capture['binding']['definition_revision']!=identity['definition_revision']):
                            raise ServiceError('MODEL_VALIDATION_FAILED','execution configuration or solver failed')
                        self.service._publish_result(store,received,capture)
                        logger.info('单次仿真结果已核验并采用',extra={'event':'SIMULATION_ADOPTED','phase':'adoption',
                            'task':result.task_id})
                        self.update(completed_tasks=1,total_tasks=1,artifacts=[store.reference(outcome)])
            except Exception as exc:
                self._recovery=True
                if error is None:error=exc
            if error is not None and dispatched:self._recovery=True
        self.overview.update(status='RECOVERY_REQUIRED' if self._recovery else ('FAILED' if error else 'STOPPED'))
        if error is not None:
            logger.error('单次仿真未完成，保留协议与结果证据',exc_info=(type(error),error,error.__traceback__),
                extra={'event':'SIMULATION_FAILED','phase':'single-simulation','error_code':getattr(error,'code',None)})
            raise error

    def request_stop(self):
        self.stop.request()
        if self.worker is not None:self.worker.request_stop()

    def lifecycle_facts(self):
        from .lifecycle_diagnostics import project_lifecycle
        return project_lifecycle(self.service.project)
    def recovery_required(self):return self._recovery
    def session_safety(self):return self._safety
    def close(self):pass  # run() already follows the normal worker stop protocol.


class SimulationRecoveryExecution:
    def __init__(self,service,stop,update):
        self.service,self.stop,self.update=service,stop,update
        self._recovery=True
    def request_stop(self):self.stop.request()
    def recover(self):
        from .project_session_recovery import recover_project_sessions
        from .recovery_control import RecoveryPaused
        def pause():
            if self.stop.is_set():raise RecoveryPaused('单次计算恢复已暂停')
        # A committed single result may still have an acknowledged receipt.
        # Repair its adoption before generic session recovery considers that
        # receipt an unconsumed HOM/batch result. Never repair while a session
        # is live/unknown, and never invoke Solver from reconciliation.
        facts=self.lifecycle_facts()
        if all(item.get('process_state')=='exited' for item in facts.get('sessions',[])):
            for path in sorted((self.service.project/'control/runs').glob('*/simulation-intent.json')):
                pause()
                received=path.parent/'simulation-received.json'
                if ((path.parent/'simulation-result.json').exists() or
                        (received.exists() and read_json(received).get('status')=='Success'
                         and (path.parent/'simulation-closure.json').exists())):
                    self.service.reconcile_simulation(path.parent.name)
        recover_project_sessions(self.service.project,pause_check=pause,
            progress=lambda event:self.update(recovery_progress=event))
        for path in sorted((self.service.project/'control/runs').glob('*/simulation-intent.json')):
            pause()
            intent=read_json(path)
            outcome=read_json(path.parent/'outcome.json') if (path.parent/'outcome.json').exists() else {}
            if (intent.get('dispatch_intent') is False and outcome.get('run_id')==path.parent.name
                    and outcome.get('state') in ('INTERRUPTED','FAILED') and outcome.get('session_safety')=='confirmed-closed'):
                continue
            if not (path.parent/'simulation-result.json').exists():
                self.service.reconcile_simulation(path.parent.name)
        from .lifecycle_diagnostics import project_lifecycle
        facts=project_lifecycle(self.service.project)
        if facts.get('recovery_required') or facts.get('session_safety') in ('running','unknown'):
            raise ServiceError('RUN_RECONCILIATION_REQUIRED','project session safety still unresolved')
        self._recovery=False
    def lifecycle_facts(self):
        from .lifecycle_diagnostics import project_lifecycle
        return project_lifecycle(self.service.project)
    def recovery_required(self):return self._recovery
    def session_safety(self):return self.lifecycle_facts()['session_safety']
    def close(self):pass


class DefinitionOperationExecution:
    """Existing Runner slot for one explicit create/edit/verify operation."""
    def __init__(self,service,run_id,stop,update):
        self.service,self.run_id,self.stop,self.update=service,run_id,stop,update
    def run(self,payload):
        self.stop.check()
        self.update(phase=payload['operation'])
        record=self.service.execute_definition_operation(payload,operation_id=self.run_id,cancel_check=self.stop.check,
            progress=lambda event:self.update(phase=event['stage'],last_progress=event))
        self.update(completed_tasks=1,total_tasks=1,artifacts=[dict(path=record['model_path'],sha256=record['source_sha256'])])
    def request_stop(self):self.stop.request()
    def close(self):pass
    def lifecycle_facts(self):
        from .lifecycle_diagnostics import project_lifecycle
        return project_lifecycle(self.service.project)
    def recovery_required(self):return self.lifecycle_facts()['recovery_required']
    def session_safety(self):return self.lifecycle_facts()['session_safety']
    def recover(self):
        from .project_session_recovery import recover_project_sessions
        from .recovery_control import RecoveryPaused
        def pause():
            if self.stop.is_set():raise RecoveryPaused('创建操作恢复已暂停')
        lock=ProjectRunLock(self.service.project);lock.acquire()
        try:
            recover_project_sessions(self.service.project,pause_check=pause,
                progress=lambda event:self.update(recovery_progress=event))
        finally:lock.release()
        for path in sorted((self.service.project/'control/runs').glob('*/definition-intent.json')):
            pause()
            if (path.parent/'definition-abandoned.json').exists():continue
            if not (path.parent/'definition-result.json').exists():
                try:self.service.reconcile_project_creation(path.parent.name)
                except ServiceError as error:
                    # Explicit recovery may retire an uncommitted, non-solving
                    # definition operation once all owned sessions are dead.
                    # Committed gaps must reconcile; they must not be discarded.
                    facts=self.lifecycle_facts()
                    if (error.code!='RUN_RECONCILIATION_REQUIRED' or (path.parent/'definition-commit.json').exists()
                            or facts.get('recovery_required') or facts.get('session_safety') in ('unknown','running')):
                        raise
                    write_json_atomic(path.parent/'definition-abandoned.json',dict(schema_version=1,
                        run_id=path.parent.name,intent_sha256=_sha(path),disposition='uncommitted-candidate-retained',
                        reason=str(error),published=False,native_replayed=False))
        # No failed candidate is promoted or recreated by recovery.
