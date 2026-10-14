"""Safe CST-side preprocessing for the standard HOM scan parameters."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import psutil
from .cst_process_env import cst_process_environment
import tempfile
from typing import Callable

from csttool import projectutil
from .acceptance_session import wait_probe
from .configuration import write_json_atomic


REQUIRED_HOM_PARAMETERS = frozenset({"fmin", "fmax", "nmodes", "cell"})


class CstPreprocessError(RuntimeError):
    """CST could not prepare and save the project copy."""


@dataclass(frozen=True)
class CstPreprocessResult:
    project_path: Path
    parameters: tuple[dict, ...]


class CstProjectPreprocessor:
    """Preserve failed copies; bound loading/exit, not geometry reconstruction."""

    def __init__(
        self,
        executable: str | Path,
        macro_template: str | Path,
        *,
        timeout: float = 180.0,
        runner: Callable | None = None,
        logger: logging.Logger | None = None,
        run_in_background: bool = True,
    ) -> None:
        self.executable = Path(executable)
        self.macro_template = Path(macro_template)
        self.timeout = float(timeout)
        self.runner = runner
        self.logger = logger or logging.getLogger(__name__)
        self.run_in_background = bool(run_in_background)

    def _run(self, command, working):
        if self.runner is not None:
            return self.runner(command, env=cst_process_environment(),
                               capture_output=True, text=True, errors="replace",
                               timeout=None, check=False, **self._startup_options())
        with (working / "cst.log").open("wb") as stream:
            process = subprocess.Popen(command, env=cst_process_environment(),
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       **self._startup_options())
            try:
                identity = {"pid": process.pid,
                            "create_time": psutil.Process(process.pid).create_time()}
                write_json_atomic(working / "session-status.json",
                                  {"launcher_pid": process.pid, "owned": [identity],
                                   "exit_confirmed": False})
            except psutil.NoSuchProcess:
                pass
            diagnostic = wait_probe(
                process, working, stage_timeout=self.timeout, exit_timeout=60,
                completion_names=("completion.txt",),
                unbounded_stages=("bind-history", "rebuild", "save"),
            )
        if diagnostic['foreign_processes']:
            raise CstPreprocessError("发现未确认归属的 CST 进程，不能确认安全退出")
        return subprocess.CompletedProcess(command, process.returncode,
                                           (working / "cst.log").read_text(errors="replace"), "")

    def _startup_options(self) -> dict:
        """Start CST minimized without activating its main window on Windows."""
        if os.name != "nt":
            return {}
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if not self.run_in_background:
            return options
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 7  # SW_SHOWMINNOACTIVE
        options["startupinfo"] = startupinfo
        return options

    @staticmethod
    def _vb_path(path: Path) -> str:
        return str(path.resolve()).replace("\\", "\\\\")

    def render_macro(
        self,
        project_path: Path,
        parameter_output: Path,
        status_output: Path,
        mesh_cells_per_wavelength: int,
    ) -> str:
        source = self.macro_template.read_text(encoding="utf-8-sig")
        replacements = {
            "%CSTPROJFILE%": self._vb_path(project_path),
            "%PARAMDSTPATH%": self._vb_path(parameter_output),
            "%STATUSPATH%": self._vb_path(status_output),
            "%STAGEPATH%": self._vb_path(status_output.parent / "stage.txt"),
            "%MESHCELLSPERWAVELENGTH%": str(int(mesh_cells_per_wavelength)),
        }
        for marker, value in replacements.items():
            if marker not in source:
                raise CstPreprocessError(f"preprocess template is missing {marker}")
            source = source.replace(marker, value)
        return source

    def preprocess(
        self,
        source_project_path: str | Path,
        output_project_path: str | Path,
        parameter_json_path: str | Path,
        temp_directory: str | Path,
        *,
        mesh_cells_per_wavelength: int = 20,
    ) -> CstPreprocessResult:
        source_project_path = Path(source_project_path).resolve()
        output_project_path = Path(output_project_path).resolve()
        parameter_json_path = Path(parameter_json_path).resolve()
        temp_directory = Path(temp_directory).resolve()
        if (
            source_project_path.suffix.casefold() != ".cst"
            or not source_project_path.is_file()
        ):
            raise FileNotFoundError(source_project_path)
        if output_project_path.suffix.casefold() != ".cst":
            raise ValueError("prepared project path must use the .cst suffix")
        if source_project_path == output_project_path:
            raise ValueError("preprocessing requires a distinct output project path")
        if output_project_path.exists():
            raise FileExistsError(output_project_path)
        if not self.executable.is_file():
            raise FileNotFoundError(self.executable)
        temp_directory.mkdir(parents=True, exist_ok=True)
        parameter_json_path.parent.mkdir(parents=True, exist_ok=True)

        # A previous interrupted run may still own a live CST process. Do not
        # silently launch a second copy or delete its evidence.
        for receipt in temp_directory.glob("cst-preprocess-*/session-status.json"):
            previous = json.loads(receipt.read_text(encoding="utf-8"))
            for identity in previous.get("owned", []) + previous.get("foreign_processes", []):
                try:
                    process = psutil.Process(identity['pid'])
                    if process.create_time() == identity['create_time'] and process.is_running():
                        raise CstPreprocessError(f"上次预处理进程仍活跃，先正常关闭并检查 {receipt.parent}")
                except psutil.NoSuchProcess:
                    pass
        working = Path(tempfile.mkdtemp(prefix="cst-preprocess-", dir=temp_directory))
        manifest = {"source": str(source_project_path), "output": str(output_project_path),
                    "parameter_json": str(parameter_json_path), "state": "preparing"}
        write_json_atomic(working / "preprocess-report.json", manifest)
        try:
            working_project = working / source_project_path.name
            macro_path = working_project.with_suffix('') / 'Model' / '3D' / 'Model.run'
            macro_path.parent.mkdir(parents=True, exist_ok=True)
            parameter_output = working / "parameters.txt"
            status_output = working / "completion.txt"
            shutil.copy2(source_project_path, working_project)
            working_project.chmod(working_project.stat().st_mode | stat.S_IWRITE)
            macro_path.write_text(
                self.render_macro(
                    working_project,
                    parameter_output,
                    status_output,
                    mesh_cells_per_wavelength,
                ),
                encoding="utf-8",
            )
            command = [str(self.executable), "-m", "-b", str(working_project)]
            self.logger.info("启动 CST 工程参数预处理 | source=%s diagnostics=%s", source_project_path, working)
            try:
                completed = self._run(command, working)
            except subprocess.TimeoutExpired as exc:
                raise CstPreprocessError("CST 工程参数预处理超时") from exc
            (working / "runner-output.txt").write_text(
                (completed.stdout or '') + (completed.stderr or ''), encoding="utf-8")
            if completed.returncode != 0:
                raise CstPreprocessError(
                    f"CST 工程参数预处理异常退出: {completed.returncode}"
                )
            if 'Error in macro execution' in ((completed.stdout or '') + (completed.stderr or '')):
                raise CstPreprocessError('CST 工程参数预处理出现宏求值错误，即使退出码为0也不能接收')
            if not status_output.is_file():
                raise CstPreprocessError("CST 工程参数预处理未返回完成状态")
            status = status_output.read_text(encoding="utf-8-sig").strip()
            if status != "SUCCESS":
                raise CstPreprocessError(f"CST 工程参数预处理失败: {status}")
            if not parameter_output.is_file():
                raise CstPreprocessError("CST 工程参数预处理未导出参数清单")
            projectutil.custom_ascii_2_json(parameter_output, parameter_json_path)
            parameters = tuple(projectutil.get_parameters(parameter_json_path))
            names = {item["name"] for item in parameters}
            missing = REQUIRED_HOM_PARAMETERS - names
            if missing:
                raise CstPreprocessError(
                    "CST 工程参数预处理缺少参数: "
                    + ", ".join(sorted(missing))
                )
            output_project_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(working_project, output_project_path)
        except Exception as exc:
            manifest.update(state="failed", error=str(exc))
            write_json_atomic(working / "preprocess-report.json", manifest)
            self.logger.error("CST 预处理失败，副本及诊断已保留 | diagnostics=%s", working)
            raise CstPreprocessError(f"{exc}；诊断目录: {working}") from exc
        manifest.update(state="success", raw_copy_removed=True)
        shutil.copy2(macro_path, working / "Model.run")
        working_project.unlink()
        shutil.rmtree(working_project.with_suffix(''))
        write_json_atomic(working / "preprocess-report.json", manifest)
        return CstPreprocessResult(output_project_path, parameters)
