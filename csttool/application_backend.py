"""Production application orchestration independent from GUI and CLI concerns."""

from __future__ import annotations

from enum import Enum, auto
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Callable
from uuid import uuid4

from install_compat import resource_path

from csttool import cstmanager, globalconfmanager, hom_scan_algorithm
from csttool.logging_config import ApplicationLogSession, ContextLogger, log_failure
from csttool.run_overview import RunOverview, RunOverviewHandler
from csttool.managed_cstworker import ManagedCSTWorker
from csttool import projectconfmanager
from csttool.hom_scan import ScanInterrupted
from csttool.hom_run_manifest import HomRunManifest
from csttool.configuration import read_json
from csttool.mesh_convergence import (
    MeshConvergenceAnalyzer,
    MeshConvergenceSettings,
    scalar_postprocess_values,
)
from csttool.project_session_recovery import (
    discover_managed_sessions,
    recover_project_sessions,
)
from csttool.project_run_lock import ProjectRunBusyError, ProjectRunLock


class BackendState(Enum):
    CREATED = auto()
    INITIALIZED = auto()
    PREPARED = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    INTERRUPTED = auto()
    RECOVERY_REQUIRED = auto()
    FAILED = auto()


class BackendLifecycleError(RuntimeError):
    """The requested operation is invalid for the current backend state."""


class BackendInitializationError(RuntimeError):
    """CST environment initialization failed."""


class BackendPreparationError(RuntimeError):
    """Project or execution preparation failed."""


class CstApplicationBackend:
    supports_cst_backend_selection = True

    """Coordinate configuration, algorithm execution, and Manager lifecycle."""

    def __init__(
        self,
        *,
        global_config_manager=None,
        project_config_manager=None,
        algorithm=None,
        manager_factory: Callable[..., object] | None = None,
        application_logger=None,
        logging_level: str = "info",
        mesh_convergence_evaluator=None,
    ) -> None:
        self._lifecycle_lock = threading.RLock()
        self.state = BackendState.CREATED
        self.worker_count = 1
        self.resume = False
        self.jm = None
        self._manager_stop_requested = False
        self._progress_listeners = []
        self._project_run_lock = None
        self._mesh_convergence_evaluator = mesh_convergence_evaluator

        if application_logger is None:
            timestamp = datetime.now().strftime("%Y-%m-%d-%H_%M_%S_%f")
            os.makedirs(r".\log", exist_ok=True)
            self.log_path = rf"log\base_{timestamp}.log"
            self._log_owner = ApplicationLogSession(
                self.log_path,
                level=logging_level,
            )
            self.logger = self._log_owner.logger
            self.logger.info("日志已输出到%s", self.log_path)
        else:
            self.log_path = None
            self._log_owner = None
            self.logger = application_logger

        self._base_logger = self.logger
        self.run_id = None
        self._run_overview = None
        self._overview_handler = None
        self.logger.debug("运行资源目录 | path=%s", resource_path("."))
        self.gconfman = global_config_manager or globalconfmanager.GlobalConfigManager(
            logger=self.logger
        )
        self.pconfman = project_config_manager or projectconfmanager.ProjectConfigManager(
            GlobalConfigManager=self.gconfman,
            logger=self.logger,
        )
        self.alg = algorithm or hom_scan_algorithm.HomScanAlgorithm(manager=None, params=None)
        self._vacuum_domain_settings = {}
        self._uses_default_manager = manager_factory is None
        self._manager_factory = manager_factory or cstmanager.CSTManager

        default_pps_path = resource_path("data/defaultPPS.json")
        default_pps = self.pconfman.read_postprocess_settings(default_pps_path)
        self.pconfman.set_postprocess_settings(default_pps)

    def select_project_directory(self, path: str) -> None:
        self._require_configurable("select project directory")
        self.pconfman.select_project_directory(path)

    def get_project_directory(self):
        return self.pconfman.currProjectDir

    def select_cst_file(self, path: str) -> None:
        self._require_configurable("select CST file")
        self.pconfman.select_input_project(path)

    def get_cst_installations(self):
        return self.gconfman.list_cst_installations()

    def get_selected_cst_installation(self):
        try:
            return self.gconfman.get_selected_cst_installation()
        except (FileNotFoundError, TypeError, ValueError):
            return None

    def select_cst_installation(self, version: int, executable: str):
        self._require_configurable("select CST installation")
        return self.gconfman.select_cst_installation(version, executable)

    def get_cst_file(self):
        return (
            getattr(self.pconfman, "inputCSTFilePath", None)
            or self.pconfman.currCSTFilePath
        )

    def get_postprocess_settings(self):
        return self.pconfman.get_postprocess_settings()

    def update_postprocess_settings(self, values) -> None:
        self._require_configurable("update postprocess settings")
        self.pconfman.set_postprocess_settings(values)

    def read_postprocess_settings(self, path):
        return self.pconfman.read_postprocess_settings(path)

    def get_algorithm_settings(self):
        return {**self.alg.get_editable_attributes(), **self._vacuum_domain_settings}

    def update_algorithm_settings(self, values) -> None:
        self._require_configurable("update algorithm settings")
        self.alg.set_editable_attributes(values)
        self._vacuum_domain_settings.update({key:values[key] for key in
            ('vacuum_domain_enabled','vacuum_domain_config') if key in values})
        self.logger.info("算法设置已更新 | project=%s algorithm=%s", self.get_project_directory(), type(self.alg).__name__)

    def initialize_run(
        self,
        resume: bool,
        worker_count: int,
    ) -> None:
        self._require_state(
            "initialize run",
            BackendState.CREATED,
            BackendState.STOPPED,
            BackendState.INTERRUPTED,
            BackendState.RECOVERY_REQUIRED,
            BackendState.FAILED,
        )
        worker_count = int(worker_count)
        if worker_count < 1:
            raise ValueError("worker_count must be at least 1")

        self.resume = bool(resume)
        self.worker_count = worker_count
        self.run_id = uuid4().hex
        if self._log_owner is not None:
            name = self._base_logger.name
            level = self._base_logger.level
            self._log_owner.close()
            if self._overview_handler is not None:
                self._base_logger.removeHandler(self._overview_handler)
                self._overview_handler.close()
            settings = self.alg.get_editable_attributes()
            naming_settings = dict(settings)
            source_hint = getattr(self.pconfman, 'inputCSTFilePath', getattr(self.pconfman, 'currCSTFilePath', None))
            if self.resume:
                try:
                    original = read_json(Path(self.get_project_directory())/'save/csv/scan_manifest.json')
                    naming_settings.update(fmin=original['frequency_start'], endfreq=original['frequency_stop'])
                    source_hint = original.get('source_project', source_hint)
                except (OSError, ValueError, KeyError, TypeError):
                    naming_settings = {}
            purpose = (f"HOM-{naming_settings.get('fmin','?')}-{naming_settings.get('endfreq',naming_settings.get('fmax','?'))}MHz"
                       if 'fmin' in naming_settings else ('续跑-原配置待确认' if self.resume else '批量优化'))
            self._run_overview = RunOverview(self.get_project_directory(), self.run_id, purpose,
                                            resume=self.resume, settings=settings)
            self._run_overview.update(source_project=str(source_hint) if source_hint else '未知')
            self.log_path = self._run_overview.directory / 'application.log'
            self._log_owner = ApplicationLogSession(self.log_path, level=level, name=name)
            self._base_logger = self._log_owner.logger
            self._overview_handler = RunOverviewHandler(self._run_overview)
            self._base_logger.addHandler(self._overview_handler)
        self.logger = ContextLogger(self._base_logger, {
            "run_id": self.run_id,
            "project": self.get_project_directory(),
        })
        self.gconfman.logger = self.logger
        self.pconfman.logger = self.logger
        self.alg.set_resume(self.resume)
        if self.resume:
            try:
                self._restore_resume_configuration()
                if self._run_overview is not None:
                    self._run_overview.update(settings=self.alg.get_editable_attributes())
            except Exception as exc:
                self.logger.exception("读取原项目续算配置失败")
                self._set_state(BackendState.FAILED)
                raise BackendInitializationError(f"读取原项目续算配置失败：{exc}") from exc
        self.logger.info(
            "初始化运行 | RUN_INITIALIZE project=%s resume=%s workers=%d",
            self.get_project_directory(),
            self.resume,
            self.worker_count, extra={"event": "RUN_INITIALIZE", "phase": "lifecycle", "project": self.get_project_directory(), "resume": self.resume, "workers": self.worker_count})

        try:
            if self.gconfman.validate_environment() is False:
                raise BackendInitializationError("CST 环境初始化失败")
            self.gconfman.saveconf()
        except BackendInitializationError:
            self.logger.exception("运行初始化失败 | state=FAILED")
            self._set_state(BackendState.FAILED)
            raise
        except Exception as exc:
            self._set_state(BackendState.FAILED)
            self.logger.exception("运行初始化失败 | state=FAILED")
            raise BackendInitializationError("CST 环境初始化失败") from exc

        self.logger.debug("项目已选择 | project=%s", self.get_project_directory())
        self._set_state(BackendState.INITIALIZED)

    def _restore_resume_configuration(self):
        project_settings = self.pconfman.load_resume_configuration()
        if project_settings is None:
            return
        settings = dict(self.alg.get_editable_attributes())
        settings["mesh_cells_per_wavelength"] = project_settings.cells_per_wavelength
        if "population_size" not in settings:
            settings["preprocess_modify_mesh"] = project_settings.fixed_mesh
        settings["mesh_convergence_enabled"] = False
        manifest_path = Path(self.get_project_directory()) / "save" / "csv" / "scan_manifest.json"
        if manifest_path.is_file():
            manifest = HomRunManifest(**read_json(manifest_path))
            if manifest.schema_version != 3:
                raise ValueError("不支持的原项目运行清单版本")
            if manifest.mesh_cells_per_wavelength != project_settings.cells_per_wavelength:
                raise ValueError("原项目配置与运行清单的网格设置不一致")
            if manifest.preprocess_modify_mesh != project_settings.fixed_mesh:
                raise ValueError("原项目配置与运行清单的预处理mesh策略不一致")
            settings.update({
                "fmin": manifest.frequency_start,
                "fmax": manifest.frequency_start + manifest.initial_window,
                "endfreq": manifest.frequency_stop,
            })
            if manifest.worker_count < 1:
                raise ValueError("原项目 Worker 数量无效")
            self.worker_count = manifest.worker_count
            if manifest.cst_executable:
                self.gconfman.select_cst_installation(manifest.cst_version, manifest.cst_executable)
        self.alg.set_editable_attributes(settings)
        self.logger.info(
            "RESUME_CONFIG_LOADED 已读取原项目配置：mesh=%d workers=%d algorithm=%s",
            project_settings.cells_per_wavelength, self.worker_count, settings,
        )

    def prepare_run(self) -> None:
        self._require_state("prepare run", BackendState.INITIALIZED)
        try:
            self._acquire_project_run_lock()
            checkpoint = Path(self.get_project_directory()) / 'save' / 'csv' / 'hom_scan_checkpoint.json'
            manifest = checkpoint.with_name('scan_manifest.json')
            if (checkpoint.exists() or manifest.exists()) and not self.resume:
                raise BackendPreparationError("已有HOM检查点，禁止从头覆盖；请使用继续运行或新项目目录")
            self.logger.info("准备运行 | RUN_PREPARE project=%s", self.get_project_directory(), extra={"event": "RUN_PREPARE", "phase": "lifecycle", "project": self.get_project_directory()})
            unresolved = self.get_recovery_sessions()
            if unresolved:
                self._set_state(BackendState.RECOVERY_REQUIRED)
                raise BackendPreparationError(
                    f"发现 {len(unresolved)} 个未闭合 CST 会话，请先执行会话恢复"
                )
            if self.resume:
                self.pconfman.recover_failed_project()
            settings = self.alg.get_editable_attributes()
            if not settings.get('preprocess_modify_mesh', True) and settings.get('mesh_convergence_enabled', False):
                raise BackendPreparationError("保留原mesh时不能启用Mesh收敛分析")
            validate_postprocess = getattr(
                self.alg,
                "validate_postprocess_settings",
                None,
            )
            if validate_postprocess is not None:
                validate_postprocess(self.pconfman.get_postprocess_settings())
            if not self.resume and settings.get("mesh_convergence_enabled", False):
                recommended = self._run_mesh_convergence(settings)
                settings["mesh_cells_per_wavelength"] = recommended
                self.alg.set_editable_attributes(settings)
            self.pconfman.prepare_project(
                self.resume,
                mesh_cells_per_wavelength=settings[
                    "mesh_cells_per_wavelength"
                ],
                **({"modify_mesh": False} if not settings.get('preprocess_modify_mesh', True) else {}),
            )
            self.gconfman.printconf()
            self.logger.debug("项目配置校验完成 | project=%s", self.get_project_directory())
            self._create_manager()
            algorithm_params = self.pconfman.get_parameters()
            self.alg.set_job_manager(self.jm)
            self.alg.set_cst_parameters(algorithm_params)
        except Exception as exc:
            log_failure(self.logger, "运行准备未完成，本次未开始正式扫描", exc,
                        extra={'phase':'prepare','project':self.get_project_directory(),
                               'resume':self.resume,'recovery_hint':'检查首个异常及诊断目录，再决定恢复或重试'})
            if self.state is not BackendState.RECOVERY_REQUIRED:
                self._set_state(BackendState.FAILED)
            try:
                self._stop_manager_once()
            finally:
                self._clear_manager()
                self._release_project_run_lock()
            if isinstance(exc, BackendPreparationError):
                raise
            raise BackendPreparationError("运行配置准备失败") from exc
        self._set_state(BackendState.PREPARED)
        self.logger.info("运行已就绪 | RUN_PREPARED project=%s workers=%d", self.get_project_directory(), self.worker_count, extra={"event": "RUN_PREPARED", "phase": "lifecycle", "project": self.get_project_directory(), "workers": self.worker_count})

    def _run_mesh_convergence(self, settings) -> int:
        convergence = MeshConvergenceSettings(
            enabled=True,
            start=int(settings["mesh_convergence_start"]),
            stop=int(settings["mesh_convergence_stop"]),
            step=int(settings["mesh_convergence_step"]),
            tolerance=float(settings["mesh_convergence_tolerance"]),
        )
        output_directory = Path(self.get_project_directory()) / "mesh_convergence"
        analyzer = MeshConvergenceAnalyzer(convergence)
        self.logger.info(
            "开始网格收敛分析 | MESH_CONVERGENCE_START levels=%s tolerance=%g",
            convergence.levels,
            convergence.tolerance, extra={"event": "MESH_CONVERGENCE_START", "phase": "lifecycle", "levels": convergence.levels, "tolerance": convergence.tolerance})
        evaluator = self._mesh_convergence_evaluator
        if evaluator is None:
            evaluator = lambda level: self._evaluate_mesh_level(
                level, settings, output_directory
            )
        try:
            report = analyzer.run(evaluator)
            json_path, csv_path = report.write(output_directory)
        except Exception as exc:
            output_directory.mkdir(parents=True, exist_ok=True)
            (output_directory / "mesh_convergence_error.json").write_text(
                json.dumps(
                    {"error": str(exc), "settings": settings},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            raise
        self.logger.info(
            "网格收敛分析完成 | MESH_CONVERGENCE_RESULT converged=%s recommended=%s json=%s csv=%s",
            report.converged,
            report.recommended_cells_per_wavelength,
            json_path,
            csv_path, extra={"event": "MESH_CONVERGENCE_RESULT", "phase": "lifecycle", "converged": report.converged, "recommended": report.recommended_cells_per_wavelength, "json": json_path, "csv": csv_path})
        if not report.converged:
            raise BackendPreparationError(
                "Mesh 在设定上限内未收敛；请查看 mesh_convergence 报告并提高上限"
            )
        return int(report.recommended_cells_per_wavelength)

    def _evaluate_mesh_level(self, level, settings, output_directory):
        source = self.get_cst_file()
        if source is None:
            raise BackendPreparationError("Mesh 收敛分析需要 CST 模板")
        output_directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f"cells-{level}-", dir=output_directory
        ) as temporary:
            level_directory = Path(temporary)
            config = projectconfmanager.ProjectConfigManager(
                GlobalConfigManager=self.gconfman,
                logger=self.logger,
            )
            config.select_project_directory(level_directory)
            config.select_input_project(source)
            config.set_postprocess_settings(self.pconfman.get_postprocess_settings())
            config.prepare_project(
                False, mesh_cells_per_wavelength=level
            )
            manager_options = {}
            if self._uses_default_manager:
                manager_options["worker_factory"] = ManagedCSTWorker.create
                manager_options["progress_callback"] = self._publish_cst_progress
            manager = self._manager_factory(
                params=config.get_parameters(),
                pconfm=config,
                gconfm=self.gconfman,
                logger=self.logger,
                maxTask=1,
                **manager_options,
            )
            with self._lifecycle_lock:
                self.jm = manager
                self._manager_stop_requested = False
            try:
                result = manager.execute(
                    cstmanager.SimulationTask(
                        {
                            "nmodes": 1,
                            "fmin": settings["fmin"],
                            "fmax": settings["fmax"],
                        },
                        f"mesh-convergence-{level}",
                        retry_count=1,
                    )
                )
                if result.get("TaskStatus") != "Success":
                    raise RuntimeError(
                        result.get("FailureReport", "Mesh 收敛 CST 任务失败")
                    )
                values = scalar_postprocess_values(result)
                self.logger.info(
                    "网格采样完成 | MESH_CONVERGENCE_POINT cells=%d values=%s", level, values, extra={"event": "MESH_CONVERGENCE_POINT", "phase": "lifecycle", "cells": level, "values": values})
                return values
            finally:
                try:
                    self._stop_manager_once()
                finally:
                    self._clear_manager()

    def execute_run(self):
        self._require_state("execute run", BackendState.PREPARED)
        self._set_state(BackendState.RUNNING)
        failure = None
        result = None
        started_at = time.monotonic()
        self.logger.info("运行开始 | RUN_EXECUTE_START project=%s", self.get_project_directory(), extra={"event": "RUN_EXECUTE_START", "phase": "lifecycle", "project": self.get_project_directory()})
        try:
            self._update_task_status(projectconfmanager.TaskStatus.RUNNING)
            if self.alg is None:
                raise BackendLifecycleError("未指定计算方法")
            result = self.alg.start()
        except ScanInterrupted as exc:
            failure = exc
            self.logger.warning("运行已中断，可从安全快照继续", extra={"event": "RUN_INTERRUPTED", "phase": "execute", "reason": str(exc)})
            self._set_state(BackendState.INTERRUPTED)
            raise
        except KeyboardInterrupt as exc:
            failure = exc
            self.logger.warning("用户中断运行，开始安全停止", extra={"event": "RUN_INTERRUPTED", "phase": "execute"})
            self._set_state(BackendState.INTERRUPTED)
            manager = self.jm
            if manager is not None and hasattr(manager, "request_stop"):
                manager.request_stop()
            raise
        except Exception as exc:
            failure = exc
            log_failure(self.logger, "运行中断于异常，正在按标准流程收尾", exc,
                        extra={"event": "RUN_EXECUTE_FAILED", "phase": "execute"})
            self._set_state(BackendState.FAILED)
            raise
        finally:
            try:
                self._stop_manager_once()
            except Exception as stop_error:
                self._set_state(BackendState.RECOVERY_REQUIRED)
                log_failure(self.logger, "安全停止未完成，后续运行前必须恢复会话", stop_error,
                            extra={"event": "RUN_SHUTDOWN_FAILED", "phase": "shutdown"})
                if failure is None:
                    raise
                self.logger.error("原运行异常与退出异常均已保留，请先恢复会话",
                                  extra={'phase':'shutdown','project':self.get_project_directory(),
                                         'run_error':str(failure),'shutdown_error':str(stop_error)})
            finally:
                self._clear_manager()
                try:
                    if self.state is BackendState.INTERRUPTED:
                        self._update_task_status(
                            projectconfmanager.TaskStatus.INTERRUPTED
                        )
                    elif self.state is BackendState.FAILED:
                        self._update_task_status(projectconfmanager.TaskStatus.FAILED)
                    elif self.state is BackendState.RECOVERY_REQUIRED:
                        self._update_task_status(
                            projectconfmanager.TaskStatus.RECOVERY_REQUIRED
                        )
                    else:
                        self._update_task_status(projectconfmanager.TaskStatus.DONE)
                finally:
                    self._release_project_run_lock()

        self._set_state(BackendState.STOPPED)
        self.logger.info(
            "运行完成 | RUN_EXECUTE_DONE elapsed_seconds=%.3f",
            time.monotonic() - started_at, extra={"event": "RUN_EXECUTE_DONE", "phase": "lifecycle", "elapsed_seconds": time.monotonic() - started_at})
        return result

    def request_stop(self) -> None:
        accepted = False
        with self._lifecycle_lock:
            if self.jm is None:
                self.logger.debug("停止请求无需执行：Manager 尚未创建 | project=%s", self.get_project_directory())
                return
            if self.state in {
                BackendState.INITIALIZED,
                BackendState.PREPARED,
                BackendState.RUNNING,
            }:
                self.state = BackendState.STOPPING
                accepted = True
        if accepted:
            self.logger.info("请求安全停止 | RUN_STOP_REQUESTED project=%s", self.get_project_directory(), extra={"event": "RUN_STOP_REQUESTED", "phase": "shutdown", "project": self.get_project_directory()})
            self._update_task_status(projectconfmanager.TaskStatus.STOP_REQUESTED)
        try:
            manager = self.jm
            if manager is not None and hasattr(manager, "request_stop"):
                manager.request_stop()
        except Exception:
            self._set_state(BackendState.RECOVERY_REQUIRED)
            raise

    def get_recovery_sessions(self):
        project_directory = self.get_project_directory()
        if project_directory is None:
            return []
        if self._project_owned_elsewhere():
            return []
        return [
            item
            for item in discover_managed_sessions(project_directory)
            if item.needs_recovery
        ]

    def is_recovery_required(self) -> bool:
        return self.state is BackendState.RECOVERY_REQUIRED or bool(
            self.get_recovery_sessions()
        )

    def recover_project_sessions(self):
        self._require_configurable("recover project sessions")
        project_directory = self.get_project_directory()
        if project_directory is None:
            raise BackendLifecycleError("project directory is not selected")
        try:
            self._acquire_project_run_lock()
        except BackendPreparationError as exc:
            raise BackendLifecycleError(str(exc)) from exc
        try:
            self.logger.info("开始会话恢复 | RECOVERY_START project=%s", project_directory, extra={"event": "RECOVERY_START", "phase": "recovery", "project": project_directory})
            recovered = recover_project_sessions(project_directory)
        except Exception:
            self.logger.exception("会话恢复失败 | project=%s status=RECOVERY_REQUIRED", project_directory, extra={"event": "RECOVERY_REQUIRED", "phase": "recovery", "project": project_directory})
            raise
        finally:
            self._release_project_run_lock()
        self.logger.info("会话恢复完成 | project=%s closed_sessions=%d", project_directory, len(recovered))
        self._update_task_status(projectconfmanager.TaskStatus.INTERRUPTED)
        self._set_state(BackendState.INTERRUPTED)
        return recovered

    def emergency_terminate(self) -> None:
        manager = self.jm
        if manager is None or not hasattr(manager, "emergency_terminate"):
            raise BackendLifecycleError("no managed CST session can be terminated")
        manager.emergency_terminate()
        self._manager_stop_requested = True
        self._set_state(BackendState.RECOVERY_REQUIRED)
        self._update_task_status(projectconfmanager.TaskStatus.RECOVERY_REQUIRED)

    def _create_manager(self) -> None:
        if not self.pconfman.is_ready():
            raise BackendPreparationError("pconfman 未准备完成")
        if self.jm is not None:
            raise BackendLifecycleError("Manager 已存在")
        project_params = self.pconfman.get_parameters()
        manager_options = {}
        settings = self.get_algorithm_settings()
        if settings.get('vacuum_domain_enabled',False):
            if self.worker_count != 1:
                raise BackendPreparationError('真空域登记第一版仅支持一个Worker')
            from .vacuum_domain_registry import validate_managed_domain_options
            config_path = Path(settings['vacuum_domain_config']).resolve()
            manager_options['vacuum_domain'] = validate_managed_domain_options(read_json(config_path))
        if self._uses_default_manager:
            manager_options["worker_factory"] = ManagedCSTWorker.create
            manager_options["progress_callback"] = self._publish_cst_progress
            manager_options['run_id'] = self.run_id
            if self._run_overview is not None:
                manager_options['run_directory'] = self._run_overview.directory
                manager_options['run_overview'] = self._run_overview
        self.jm = self._manager_factory(
            params=project_params,
            pconfm=self.pconfman,
            gconfm=self.gconfman,
            logger=self.logger,
            maxTask=self.worker_count,
            **manager_options,
        )
        self._manager_stop_requested = False
        self.logger.debug("Manager 已创建 | project=%s workers=%d", self.get_project_directory(), self.worker_count)

    def add_progress_listener(self, listener) -> None:
        with self._lifecycle_lock:
            if listener not in self._progress_listeners:
                self._progress_listeners.append(listener)

    def remove_progress_listener(self, listener) -> None:
        with self._lifecycle_lock:
            if listener in self._progress_listeners:
                self._progress_listeners.remove(listener)

    def _publish_cst_progress(self, event) -> None:
        with self._lifecycle_lock:
            listeners = tuple(self._progress_listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                self.logger.debug("CST progress listener failed", exc_info=True)

    def _stop_manager_once(self) -> None:
        with self._lifecycle_lock:
            manager = self.jm
            if manager is None or self._manager_stop_requested:
                return
            self._manager_stop_requested = True
        manager.stop()

    def _clear_manager(self) -> None:
        with self._lifecycle_lock:
            self.jm = None

    def _acquire_project_run_lock(self) -> None:
        if self._project_run_lock is not None:
            return
        project_directory = self.get_project_directory()
        if project_directory is None:
            raise BackendPreparationError("尚未选择项目目录")
        lease = ProjectRunLock(project_directory)
        try:
            lease.acquire()
        except ProjectRunBusyError as exc:
            self.logger.warning(
                "项目已被其他运行占用 | PROJECT_LOCK_BUSY project=%s reason=%s", project_directory, exc, extra={"event": "PROJECT_LOCK_BUSY", "phase": "lifecycle", "project": project_directory, "reason": exc})
            raise BackendPreparationError(str(exc)) from exc
        self._project_run_lock = lease
        self.logger.info(
            "已取得项目运行锁 | PROJECT_LOCK_ACQUIRED project=%s pid=%d",
            project_directory,
            lease.owner.process_id, extra={"event": "PROJECT_LOCK_ACQUIRED", "phase": "lifecycle", "project": project_directory, "pid": lease.owner.process_id})

    def _release_project_run_lock(self) -> None:
        lease = self._project_run_lock
        self._project_run_lock = None
        if lease is not None:
            lease.release()
            self.logger.info(
                "已释放项目运行锁 | PROJECT_LOCK_RELEASED project=%s", self.get_project_directory(), extra={"event": "PROJECT_LOCK_RELEASED", "phase": "lifecycle", "project": self.get_project_directory()})

    def close_logging(self) -> None:
        if self._overview_handler is not None:
            self._base_logger.removeHandler(self._overview_handler)
            self._overview_handler.close()
            self._overview_handler = None
        if self._log_owner is not None:
            self._log_owner.close()

    def _project_owned_elsewhere(self) -> bool:
        project_directory = self.get_project_directory()
        if project_directory is None:
            return False
        return (
            self._project_run_lock is None
            and ProjectRunLock.active_owner(project_directory) is not None
        )

    def _update_task_status(self, status) -> None:
        self.status = status
        self.pconfman.update_task_status(status)

    def _require_configurable(self, operation: str) -> None:
        self._require_state(
            operation,
            BackendState.CREATED,
            BackendState.STOPPED,
            BackendState.INTERRUPTED,
            BackendState.RECOVERY_REQUIRED,
            BackendState.FAILED,
        )

    def _require_state(self, operation: str, *allowed: BackendState) -> None:
        with self._lifecycle_lock:
            if self.state not in allowed:
                expected = ", ".join(state.name for state in allowed)
                raise BackendLifecycleError(
                    f"cannot {operation} while backend is {self.state.name}; "
                    f"expected one of: {expected}"
                )

    def _set_state(self, state: BackendState) -> None:
        with self._lifecycle_lock:
            self.state = state
        if getattr(self, '_run_overview', None) is not None:
            try:
                prepared = getattr(getattr(self.pconfman, 'settings', None), 'cst_filename', None)
                fields = {'prepared_project':str(Path(self.get_project_directory()) / prepared)} if prepared else {}
                self._run_overview.update(status=state.name, **fields)
            except (OSError, ValueError, TypeError, AttributeError):
                self.logger.warning("运行摘要更新失败，完整日志与控制状态不受影响", exc_info=True)
