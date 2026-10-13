"""Generate CST VBA post-processing code from declarative PPS settings."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from install_compat import resource_path
from . import postprocess_readers

from .hom_result_plan import IntegrationLine
from .postprocess_metrics import METRICS


Readout = Callable[[str | None], Any]


class CstPostProcessor:
    """Compile post-processing settings into VBA and read their results.

    Metrics are configured through the declarative registries and
    :meth:`configure`.
    """

    _SIMPLE_METRICS = {name: (metric.query, metric.token)
                       for name, metric in METRICS.items() if not metric.integration_line}
    _COMPLEX_METRICS = {name: (metric.query, metric.token)
                        for name, metric in METRICS.items() if metric.integration_line}

    def __init__(self) -> None:
        self.resultDir: Path | None = None
        self.cstRunResultDir: Path | None = None
        self.postProcessDataDir = Path(resource_path("data/postprocess"))
        self.postProcessDocList: list[dict[str, Any]] = []
        self.postProcessID = 0

    def set_result_directory(self, result_dir) -> None:
        self.resultDir = Path(result_dir)

    def set_cst_run_result_directory(self, result_dir) -> None:
        self.cstRunResultDir = Path(result_dir)

    def reset(self) -> None:
        self.resultDir = None
        self.cstRunResultDir = None
        self.postProcessDocList.clear()
        self.postProcessID = 0

    @classmethod
    def supported_methods(cls) -> tuple[str, ...]:
        simple = list(cls._SIMPLE_METRICS)
        simple_all = [f"{name}_All" for name in simple]
        complex_metrics = list(cls._COMPLEX_METRICS)
        complex_all = [f"{name}_All" for name in complex_metrics]
        return tuple(simple + simple_all + complex_metrics + complex_all + [
            "ModeRec_All",
            "Direct_PPS_0D",
            "ExportModeField",
        ])

    def configure(self, settings: Sequence[Mapping[str, Any]]) -> None:
        for index, setting in enumerate(settings):
            if not isinstance(setting, Mapping):
                raise TypeError(f"PPS entry {index} must be a mapping")
            method = setting.get("method")
            result_name = setting.get("resultName")
            params = setting.get("params", {})
            if not isinstance(method, str):
                raise ValueError(f"PPS entry {index} has no valid method")
            if not isinstance(result_name, str) or not result_name:
                raise ValueError(f"PPS entry {index} has no valid resultName")
            if not isinstance(params, Mapping):
                raise TypeError(f"PPS entry {index} params must be a mapping")
            self._append_configured_step(method, result_name, params)

    def _append_configured_step(
        self,
        method: str,
        result_name: str,
        params: Mapping[str, Any],
    ) -> None:
        if method == 'ExportModeField':
            from .field_artifacts import SamplingSpec, read_export_status
            import hashlib
            mode = self._required(params, 'iModeNumber', method)
            if isinstance(mode, bool) or not isinstance(mode, int) or mode < 1:
                raise ValueError('field export mode must be a positive integer')
            kind = params.get('field_kind', 'E')
            if kind not in ('E', 'H'):
                raise ValueError('field kind must be E or H')
            spec = SamplingSpec.from_mapping(params['sampling'])
            token = hashlib.sha256(result_name.encode()).hexdigest()[:12]
            filename = self._unique_filename(f'field_{mode}_{kind}_{token}.status')
            base = Path(filename).stem
            numbers = ','.join(format(float(v), '.17g') for v in spec.bounds_m)
            counts = ','.join(str(n) for n in spec.counts)
            self._register(import_file='ExportModeField.vb', result_name=result_name,
                result_filename=filename,
                function_call=f'ExportModeField_output {mode},"{kind}",{counts},{numbers},outFullDir,"{base}"\n',
                reader=lambda name: read_export_status(self._result_path(name), spec, mode, kind),
                params=dict(params))
            return
        if method in self._SIMPLE_METRICS:
            self._add_simple_metric(
                method,
                self._required(params, "iModeNumber", method),
                result_name,
            )
            return

        if method.endswith("_All") and method[:-4] in self._SIMPLE_METRICS:
            self._add_simple_metric_all(method[:-4], result_name)
            return

        if method in self._COMPLEX_METRICS:
            self._add_complex_metric(
                method,
                self._required(params, "iModeNumber", method),
                self._complex_integration_line(params, method),
                result_name,
            )
            return

        if method.endswith("_All") and method[:-4] in self._COMPLEX_METRICS:
            base_method = method[:-4]
            self._add_complex_metric_all(
                base_method,
                self._complex_integration_line(params, method),
                result_name,
            )
            return

        if method == "ModeRec_All":
            self.Mode_Rec(result_name)
            return

        if method == "Direct_PPS_0D":
            self.Direct_PPS_0D(result_name)
            return

        supported = ", ".join(self.supported_methods())
        raise ValueError(f"Unsupported PPS method {method!r}. Supported: {supported}")

    @staticmethod
    def _required(params: Mapping[str, Any], key: str, method: str) -> Any:
        try:
            return params[key]
        except KeyError as exc:
            raise ValueError(f"PPS method {method!r} requires parameter {key!r}") from exc

    @classmethod
    def _complex_integration_line(
        cls, params: Mapping[str, Any], method: str
    ) -> IntegrationLine:
        return IntegrationLine(
            axis=str(params.get("axis", "z")),
            xoffset_mm=cls._required(params, "xoffset", method),
            yoffset_mm=cls._required(params, "yoffset", method),
            zoffset_mm=params.get("zoffset", 0),
        )

    def _register(
        self,
        *,
        import_file: str | None,
        result_name: str,
        result_filename: str | None,
        function_call: str | None,
        reader: Readout,
        params: Mapping[str, Any] | None = None,
    ) -> None:
        self.postProcessDocList.append(
            {
                "id": self.postProcessID,
                "import": import_file,
                "resultName": result_name,
                "resultFilename": result_filename,
                "funcString": function_call,
                "readoutmethod": reader,
                "params": dict(params or {}),
            }
        )
        self.postProcessID += 1

    def getUsedFileNameList(self) -> list[str | None]:
        return [doc["resultFilename"] for doc in self.postProcessDocList]

    def _unique_filename(self, filename: str) -> str:
        used = set(self.getUsedFileNameList())
        if filename not in used:
            return filename
        path = Path(filename)
        counter = 0
        while True:
            candidate = f"{path.stem}_{counter}{path.suffix}"
            if candidate not in used:
                return candidate
            counter += 1

    @staticmethod
    def _vb_string(value: Any) -> str:
        return str(value).replace('"', '""')

    def _add_simple_metric(self, method: str, mode: int, result_name: str) -> None:
        query, token = self._SIMPLE_METRICS[method]
        filename = self._unique_filename(f"Mode_{mode}_{token}_{result_name}.txt")
        call = (
            f'EigenResult_Simple_output({mode},"{self._vb_string(query)}",'
            f'outFullDir,"{self._vb_string(filename)}")\n'
        )
        self._register(
            import_file="EigenResult_Simple.vb",
            result_name=result_name,
            result_filename=filename,
            function_call=call,
            reader=self._read_scalar,
            params={"iModeNumber": mode},
        )

    def _add_simple_metric_all(self, method: str, result_name: str) -> None:
        query, token = self._SIMPLE_METRICS[method]
        filename = self._unique_filename(f"{token}_All_{result_name}.txt")
        call = (
            f'EigenResult_Simple_All_output("{self._vb_string(query)}",'
            f'outFullDir,"{self._vb_string(filename)}")\n'
        )
        self._register(
            import_file="EigenResult_Simple.vb",
            result_name=result_name,
            result_filename=filename,
            function_call=call,
            reader=self.EigenResult_All_readout,
        )

    def _add_complex_metric(
        self,
        method: str,
        mode: int,
        line: IntegrationLine,
        result_name: str,
    ) -> None:
        query, token = self._COMPLEX_METRICS[method]
        filename = self._unique_filename(self._complex_filename(token, result_name, line, mode))
        call = (
            f'EigenResult_Complex_output({mode},"{self._vb_string(query)}",'
            f'{line.axis_number},{line.xoffset_mm:g},{line.yoffset_mm:g},'
            f'{line.zoffset_mm:g},outFullDir,"{self._vb_string(filename)}")\n'
        )
        self._register(
            import_file="EigenResult_Complex_All.vb",
            result_name=result_name,
            result_filename=filename,
            function_call=call,
            reader=self._read_scalar,
            params={
                "iModeNumber": mode,
                "axis": line.axis,
                "xoffset": line.xoffset_mm,
                "yoffset": line.yoffset_mm,
                "zoffset": line.zoffset_mm,
            },
        )

    def _add_complex_metric_all(
        self,
        method: str,
        line: IntegrationLine,
        result_name: str,
    ) -> None:
        query, token = self._COMPLEX_METRICS[method]
        filename = self._unique_filename(self._complex_filename(token, result_name, line))
        call = (
            f'EigenResult_Complex_All_output("{self._vb_string(query)}",'
            f'{line.axis_number},{line.xoffset_mm:g},{line.yoffset_mm:g},'
            f'{line.zoffset_mm:g},outFullDir,"{self._vb_string(filename)}")\n'
        )
        self._register(
            import_file="EigenResult_Complex_All.vb",
            result_name=result_name,
            result_filename=filename,
            function_call=call,
            reader=self.EigenResult_All_readout,
            params={
                "axis": line.axis,
                "xoffset": line.xoffset_mm,
                "yoffset": line.yoffset_mm,
                "zoffset": line.zoffset_mm,
            },
        )

    @staticmethod
    def _complex_filename(
        token: str,
        result_name: str,
        line: IntegrationLine,
        mode: int | None = None,
    ) -> str:
        prefix = f"Mode_{mode}_{token}" if mode is not None else f"{token}_All"
        if line.axis == "z" and line.zoffset_mm == 0:
            return (
                f"{prefix}_xoffset_{line.xoffset_mm:f}_"
                f"yoffset_{line.yoffset_mm:f}_{result_name}.txt"
            )
        return (
            f"{prefix}_axis_{line.axis}_xoffset_{line.xoffset_mm:f}_"
            f"yoffset_{line.yoffset_mm:f}_zoffset_{line.zoffset_mm:f}_"
            f"{result_name}.txt"
        )

    def render_vb(self) -> list[str]:
        lines: list[str] = []
        imports = dict.fromkeys(
            doc["import"] for doc in self.postProcessDocList if doc["import"]
        )
        for filename in imports:
            path = self.postProcessDataDir / filename
            with path.open("r", encoding="utf-8") as source:
                lines.extend(source.readlines())
            lines.append("\n")

        lines.append("\nSub CustomPostProcess\n")
        for doc in self.postProcessDocList:
            if doc["funcString"]:
                lines.append(f'    {doc["funcString"]}')
        lines.append("End Sub\n")
        return lines

    def read_all_results(self) -> list[dict[str, Any]]:
        results = []
        for doc in self.postProcessDocList:
            results.append(
                {
                    "id": doc["id"],
                    "resultName": doc["resultName"],
                    "value": doc["readoutmethod"](doc["resultFilename"]),
                    "params": doc["params"],
                }
            )
        return results

    @staticmethod
    def readFile(path) -> dict[str, str] | None:
        return postprocess_readers.read_key_values(path)

    def _result_path(self, filename: str | None) -> Path:
        if self.resultDir is None:
            raise RuntimeError("resultDir has not been configured")
        if filename is None:
            raise ValueError("This result has no output filename")
        return self.resultDir / filename

    def _read_scalar(self, filename: str | None) -> float:
        return postprocess_readers.read_scalar(self._result_path(filename))

    def EigenResult_All_readout(self, filename: str | None) -> dict[str, float]:
        return postprocess_readers.read_all_modes(self._result_path(filename))

    def Mode_Rec(self, resultName) -> None:
        self._register(
            import_file="ModeRec_All.vb",
            result_name=resultName,
            result_filename=None,
            function_call="ModeRec_All_output(outFullDir)\n",
            reader=self.Mode_Rec_readout,
        )

    def Mode_Rec_readout(self, resultFilename):
        if self.resultDir is None:
            raise RuntimeError("resultDir has not been configured")
        return postprocess_readers.read_mode_recognition(self.resultDir)

    def Direct_PPS_0D(self, resultName) -> None:
        self._register(
            import_file=None,
            result_name=resultName,
            result_filename=resultName,
            function_call=None,
            reader=self.Direct_PPS_0D_readout,
        )

    def Direct_PPS_0D_readout(self, resultName):
        if self.cstRunResultDir is None:
            raise RuntimeError("cstRunResultDir has not been configured")
        return self.cst0dreadout(
            self.cstRunResultDir / "Result" / f"{resultName}.rd0"
        )

    @staticmethod
    def cst0dreadout(path):
        return postprocess_readers.read_native_0d(path)
