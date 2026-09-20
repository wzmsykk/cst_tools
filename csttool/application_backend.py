"""Production application orchestration independent from GUI and CLI concerns."""

from __future__ import annotations

from enum import Enum, auto
import os
import threading
import time
from typing import Callable

from install_compat import resource_path

from csttool import cstmanager, globalconfmanager, logger, myAlgorithm_pop
from csttool.managed_cstworker import ManagedCSTWorker
from csttool import projectconfmanager
from csttool.hom_scan import ScanInterrupted
from csttool.project_session_recovery import (
    discover_managed_sessions,
    recover_project_sessions,
)


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
    ) -> None:
        self._lifecycle_lock = threading.RLock()
        self.state = BackendState.CREATED
        self.worker_count = 1
        self.resume = False
        self.jm = None
        self._manager_stop_requested = False
        self._progress_listeners = []

        if application_logger is None:
            timestamp = time.strftime("%Y-%m-%d-%H_%M_%S", time.localtime())
            os.makedirs(r".\log", exist_ok=True)
            self.log_path = rf"log\base_{timestamp}.log"
            self._log_owner = logger.Logger(self.log_path, level="debug")
            self.logger = self._log_owner.getLogger()
            self.logger.info("日志已输出到%s", self.log_path)
        else:
            self.log_path = None
            self._log_owner = None
            self.logger = application_logger

        self.logger.info("数据路径%s", resource_path("."))
        self.gconfman = global_config_manager or globalconfmanager.GlobalConfmanager(
            Logger=self.logger
        )
        self.pconfman = project_config_manager or projectconfmanager.ProjectConfmanager(
            GlobalConfigManager=self.gconfman,
            Logger=self.logger,
        )
        self.alg = algorithm or myAlgorithm_pop.myAlg01(manager=None, params=None)
        self._uses_default_manager = manager_factory is None
        self._manager_factory = manager_factory or cstmanager.CSTManager

        default_pps_path = resource_path("data/defaultPPS.json")
        default_pps = self.pconfman.readPPSListFromFile(default_pps_path)
        self.pconfman.setCurrPPSList(default_pps)

    def select_project_directory(self, path: str) -> None:
        self._require_configurable("select project directory")
        self.pconfman.assignProjectDir(path)

    def get_project_directory(self):
        return self.pconfman.currProjectDir

    def select_cst_file(self, path: str) -> None:
        self._require_configurable("select CST file")
        self.pconfman.assignInputCSTFilePath(path)

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
        return self.pconfman.currCSTFilePath

    def get_postprocess_settings(self):
        return self.pconfman.getCurrPPSList()

    def update_postprocess_settings(self, values) -> None:
        self._require_configurable("update postprocess settings")
        self.pconfman.setCurrPPSList(values)

    def read_postprocess_settings(self, path):
        return self.pconfman.readPPSListFromFile(path)

    def get_algorithm_settings(self):
        return self.alg.getEditableAttrs()

    def update_algorithm_settings(self, values) -> None:
        self._require_configurable("update algorithm settings")
        self.alg.setEditableAttrs(values)
        self.logger.info("ALG参数设置完毕")

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
        self.alg.set_resume(self.resume)
        self.logger.info(
            "BACKEND: resume=%s, worker_count=%d",
            self.resume,
            self.worker_count,
        )

        try:
            if self.gconfman.checkCSTENVConfig() is False:
                raise BackendInitializationError("CST 环境初始化失败")
            self.gconfman.saveconf()
        except BackendInitializationError:
            self._set_state(BackendState.FAILED)
            raise
        except Exception as exc:
            self._set_state(BackendState.FAILED)
            raise BackendInitializationError("CST 环境初始化失败") from exc

        self.logger.info("开始使用project目录:%s", self.get_project_directory())
        self._set_state(BackendState.INITIALIZED)

    def prepare_run(self) -> None:
        self._require_state("prepare run", BackendState.INITIALIZED)
        try:
            self.pconfman.prepareProject(self.resume)
            unresolved = self.get_recovery_sessions()
            if unresolved:
                self._set_state(BackendState.RECOVERY_REQUIRED)
                raise BackendPreparationError(
                    f"发现 {len(unresolved)} 个未闭合 CST 会话，请先执行会话恢复"
                )
            validate_postprocess = getattr(
                self.alg,
                "validate_postprocess_settings",
                None,
            )
            if validate_postprocess is not None:
                validate_postprocess(self.pconfman.getCurrPPSList())
            self.gconfman.printconf()
            self.logger.info("-----------------------------------")
            self._create_manager()
            algorithm_params = self.pconfman.getParamsList()
            self.alg.setJobManager(self.jm)
            self.alg.setCSTParams(algorithm_params)
        except Exception as exc:
            self.logger.exception("项目配置出错")
            if self.state is not BackendState.RECOVERY_REQUIRED:
                self._set_state(BackendState.FAILED)
            self._stop_manager_once()
            self._clear_manager()
            if isinstance(exc, BackendPreparationError):
                raise
            raise BackendPreparationError("运行配置准备失败") from exc
        self._set_state(BackendState.PREPARED)

    def execute_run(self):
        self._require_state("execute run", BackendState.PREPARED)
        self._set_state(BackendState.RUNNING)
        self._update_task_status(projectconfmanager.TaskStatus.RUNNING)
        failure = None
        result = None
        try:
            if self.alg is None:
                raise BackendLifecycleError("未指定计算方法")
            result = self.alg.start()
        except ScanInterrupted as exc:
            failure = exc
            self._set_state(BackendState.INTERRUPTED)
            raise
        except KeyboardInterrupt as exc:
            failure = exc
            self._set_state(BackendState.INTERRUPTED)
            manager = self.jm
            if manager is not None and hasattr(manager, "request_stop"):
                manager.request_stop()
            raise
        except Exception as exc:
            failure = exc
            self._set_state(BackendState.FAILED)
            raise
        finally:
            try:
                self._stop_manager_once()
            except Exception:
                self._set_state(BackendState.RECOVERY_REQUIRED)
                if failure is None:
                    raise
                self.logger.exception("算法失败后的 Manager 清理也失败")
            finally:
                self._clear_manager()
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

        self._set_state(BackendState.STOPPED)
        return result

    def request_stop(self) -> None:
        accepted = False
        with self._lifecycle_lock:
            if self.jm is None:
                self.logger.info("Stop requested before a manager was created")
                return
            if self.state is BackendState.RUNNING:
                self.state = BackendState.STOPPING
                accepted = True
        if accepted:
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
        recovered = recover_project_sessions(project_directory)
        self.logger.info("已恢复并关闭 %d 个 CST 会话", len(recovered))
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
        if not self.pconfman.isReady():
            raise BackendPreparationError("pconfman 未准备完成")
        if self.jm is not None:
            raise BackendLifecycleError("Manager 已存在")
        project_params = self.pconfman.getParamsList()
        manager_options = {}
        if self._uses_default_manager:
            manager_options["worker_factory"] = ManagedCSTWorker.create
            manager_options["progress_callback"] = self._publish_cst_progress
        self.jm = self._manager_factory(
            params=project_params,
            pconfm=self.pconfman,
            gconfm=self.gconfman,
            logger=self.logger,
            maxTask=self.worker_count,
            **manager_options,
        )
        self._manager_stop_requested = False
        self.logger.info("JOB MANAGER 创建完成")

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

    def _update_task_status(self, status) -> None:
        self.status = status
        self.pconfman.updateTaskStatus(status)

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
