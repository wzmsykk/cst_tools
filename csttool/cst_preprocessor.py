"""Safe CST-side preprocessing for the standard HOM scan parameters."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Callable

from csttool import projectutil


REQUIRED_HOM_PARAMETERS = frozenset({"fmin", "fmax", "nmodes", "cell"})


class CstPreprocessError(RuntimeError):
    """CST could not prepare and save the project copy."""


@dataclass(frozen=True)
class CstPreprocessResult:
    project_path: Path
    parameters: tuple[dict, ...]


class CstProjectPreprocessor:
    """Run one bounded CST macro against an already-created project copy."""

    def __init__(
        self,
        executable: str | Path,
        macro_template: str | Path,
        *,
        timeout: float = 180.0,
        runner: Callable = subprocess.run,
        logger: logging.Logger | None = None,
        run_in_background: bool = True,
    ) -> None:
        self.executable = Path(executable)
        self.macro_template = Path(macro_template)
        self.timeout = float(timeout)
        self.runner = runner
        self.logger = logger or logging.getLogger(__name__)
        self.run_in_background = bool(run_in_background)

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

        with tempfile.TemporaryDirectory(
            prefix="cst-preprocess-", dir=temp_directory
        ) as working:
            working = Path(working)
            macro_path = working / "preprocess.bas"
            working_project = working / source_project_path.name
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
            command = [str(self.executable), "-m", str(macro_path)]
            self.logger.info("启动 CST 工程参数预处理: %s", source_project_path)
            try:
                completed = self.runner(
                    command,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=self.timeout,
                    check=False,
                    **self._startup_options(),
                )
            except subprocess.TimeoutExpired as exc:
                raise CstPreprocessError("CST 工程参数预处理超时") from exc
            if completed.returncode != 0:
                raise CstPreprocessError(
                    f"CST 工程参数预处理异常退出: {completed.returncode}"
                )
            if not status_output.is_file():
                raise CstPreprocessError("CST 工程参数预处理未返回完成状态")
            status = status_output.read_text(encoding="utf-8-sig").strip()
            if status != "SUCCESS":
                raise CstPreprocessError(f"CST 工程参数预处理失败: {status}")
            if not parameter_output.is_file():
                raise CstPreprocessError("CST 工程参数预处理未导出参数清单")
            projectutil.custom_ascii_2_json(parameter_output, parameter_json_path)
            parameters = tuple(projectutil.getParamsList(parameter_json_path))
            names = {item["name"] for item in parameters}
            missing = REQUIRED_HOM_PARAMETERS - names
            if missing:
                raise CstPreprocessError(
                    "CST 工程参数预处理缺少参数: "
                    + ", ".join(sorted(missing))
                )
            output_project_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(working_project, output_project_path)

        return CstPreprocessResult(output_project_path, parameters)
