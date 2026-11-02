"""Shared single-simulation service. No Qt/MCP imports or alternate worker loop."""
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import math
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


class ApplicationService:
    def __init__(self,project,project_id,*,installations=None,definition_verifier=None,worker_factory=None):
        self.project=Path(project).resolve()
        self.project_id=project_id
        self.catalog=self.project/'control/definitions'
        from .definition_verifier import NativeDefinitionVerifier
        self.definition_verifier=definition_verifier if definition_verifier is not None else NativeDefinitionVerifier()
        self.worker_factory=worker_factory
        if installations is None:
            from .cst_installations import discover_cst_installations
            installations={'cst-'+str(item.version)+'-'+hashlib.sha256(str(item.executable).encode()).hexdigest()[:12]:item.executable
                           for item in discover_cst_installations()}
        self.installations={key:Path(value).resolve() for key,value in installations.items()}

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

    def stage_definition(self,document_id,source_project,installation_ref):
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
        descriptor=dict(document_id=document_id,source_sha256=source.sha256,installation_ref=installation_ref,
                        config=asdict(config),axis=values['geometry.cylinder.axis'])
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
            record=dict(schema_version=1,project_id=self.project_id,definition_revision=revision,
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
                  'installation_ref','config','axis','verification','ready'}
        if (not required<=set(record) or type(record.get('schema_version')) is not int or record['schema_version']!=1
                or type(record.get('ready')) is not bool or not isinstance(record.get('config'),dict)):
            raise ServiceError('DEFINITION_INVALID','definition metadata schema invalid')
        if (record.get('project_id')!=self.project_id or record.get('document_id')!=document_id
                or record.get('definition_revision')!=revision or _sha(directory/'definition.cst')!=record['source_sha256']):
            raise ServiceError('STALE_DOCUMENT','definition identity/hash changed')
        descriptor={key:record[key] for key in ('document_id','source_sha256','installation_ref','config','axis')}
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
        snapshot=Path(result['snapshot']).resolve()
        if not snapshot.is_relative_to(self.project) or _sha(snapshot)!=result['snapshot_sha256']:
            raise ServiceError('RESULT_INVALID','result snapshot missing or changed')
        revision=_sha(path)
        if result_revision is not None and result_revision!=revision:
            raise ServiceError('RESULT_CHANGED','requested result revision does not match')
        return dict(result,result_revision=revision)

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
            if (store.directory/'simulation-result.json').exists():
                return self.get_simulation_results(run_id)
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
            return self._publish_result(store,received,capture)
        finally:lock.release()

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
        result=dict(schema_version=1,run_id=received['run_id'],definition_revision=received['definition_revision'],
            task_id=received['task_id'],status='success',frequency_mhz=metrics['frequency'],rq_ohm=metrics['rq'],
            snapshot=str(path),snapshot_sha256=received['snapshot_sha256'],capture=capture,
            received_sha256=_sha(store.directory/'simulation-received.json'))
        store.ensure_adopted(received['task_id'],definition_revision=received['definition_revision'])
        write_json_atomic(store.directory/'simulation-result.json',result)
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
            write_json_atomic(store.directory/'simulation-intent.json',dict(document_id=self.definition['document_id'],
                definition_revision=self.definition['definition_revision'],run_id=self.run_id,execution_identity=identity,
                dispatch_intent=False))
            self._safety='running'
            if self.stop.is_set():
                self.worker.request_stop();self.stop.check()
            self.update(state='RUNNING',phase='single-simulation')
            write_json_atomic(store.directory/'simulation-intent.json',dict(document_id=self.definition['document_id'],
                definition_revision=self.definition['definition_revision'],run_id=self.run_id,execution_identity=identity,
                dispatch_intent=True))
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
    def recovery_required(self):return self._recovery
    def session_safety(self):return 'unknown' if self._recovery else 'confirmed-closed'
    def close(self):pass
