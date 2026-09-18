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


class BackendState(Enum):
    CREATED = auto()
    INITIALIZED = auto()
    PREPARED = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    FAILED = auto()


class BackendLifecycleError(RuntimeError):
    """The requested operation is invalid for the current backend state."""


class BackendInitializationError(RuntimeError):
    """CST environment initialization failed."""


class BackendPreparationError(RuntimeError):
    """Project or execution preparation failed."""


class CstApplicationBackend:
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
        self.worker_count = 2
        self.start_from_existing = False
        self.safe_mode = False
        self.jm = None
        self._manager_stop_requested = False

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
        start_from_existing: bool,
        safe_mode: bool,
        worker_count: int,
    ) -> None:
        self._require_state(
            "initialize run",
            BackendState.CREATED,
            BackendState.STOPPED,
            BackendState.FAILED,
        )
        worker_count = int(worker_count)
        if worker_count < 1:
            raise ValueError("worker_count must be at least 1")

        self.start_from_existing = bool(start_from_existing)
        self.safe_mode = bool(safe_mode)
        self.worker_count = worker_count
        self.logger.info(
            "BACKEND: start_from_existing=%s, safe_mode=%s, worker_count=%d",
            self.start_from_existing,
            self.safe_mode,
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
            self.pconfman.prepareProject(
                self.start_from_existing,
                self.safe_mode,
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
        except Exception as exc:
            failure = exc
            self._set_state(BackendState.FAILED)
            raise
        finally:
            try:
                self._stop_manager_once()
            except Exception:
                self._set_state(BackendState.FAILED)
                if failure is None:
                    raise
                self.logger.exception("算法失败后的 Manager 清理也失败")
            finally:
                self._clear_manager()
                self._update_task_status(projectconfmanager.TaskStatus.DONE)

        self._set_state(BackendState.STOPPED)
        return result

    def request_stop(self) -> None:
        with self._lifecycle_lock:
            if self.jm is None:
                self.logger.info("Stop requested before a manager was created")
                return
            if self.state is BackendState.RUNNING:
                self.state = BackendState.STOPPING
        try:
            self._stop_manager_once()
        except Exception:
            self._set_state(BackendState.FAILED)
            raise

    def _create_manager(self) -> None:
        if not self.pconfman.isReady():
            raise BackendPreparationError("pconfman 未准备完成")
        if self.jm is not None:
            raise BackendLifecycleError("Manager 已存在")
        project_params = self.pconfman.getParamsList()
        manager_options = {}
        if self._uses_default_manager:
            manager_options["worker_factory"] = ManagedCSTWorker.create
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
