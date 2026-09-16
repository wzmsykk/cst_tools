"""Generate CST VBA post-processing code from declarative PPS settings."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from install_compat import resource_path
from utils.mode_util_sample import allModesResult


Readout = Callable[[str | None], Any]


class VBPostProcessor:
    """Compile post-processing settings into VBA and read their results.

    The public wrapper methods are retained for compatibility.  New metrics
    should normally be added to one of the declarative registries instead of
    copying another builder method.
    """

    _SIMPLE_METRICS = {
        "Q_Factor": ("Q-Factor", "Q_Factor"),
        "Q_Ext": ("Q_Ext", "Q_Ext"),
        "Frequency": ("Frequency", "Frequency"),
        "Total_Loss": ("Total Loss", "Total_Loss"),
        "Loss_Enclosure": ("Loss_Enclosure", "Loss_Enclosure"),
        "Loss_Volume": ("Loss_Volume", "Loss_Volume"),
        "Loss_Surface": ("Loss_Surface", "Loss_Surface"),
        "Q_Enclosure": ("Q_Enclosure", "Q_Enclosure"),
        "Q_Volume": ("Q_Volume", "Q_Volume"),
        "Q_Surface": ("Q_Surface", "Q_Surface"),
        "Total_Energy": ("Total Energy", "Total_Energy"),
    }
    _COMPLEX_METRICS = {
        "R_over_Q": ("R over Q", "ROQ"),
        # Keep the historical spelling because it is part of the CST API call.
        "Shunt_Inpedence": ("Shunt Inpedence", "SI"),
    }

    def __init__(self) -> None:
        self.resultDir: Path | None = None
        self.cstRunResultDir: Path | None = None
        self.postProcessDataDir = Path(resource_path("data/postprocess"))
        self.postProcessDocList: list[dict[str, Any]] = []
        self.postProcessID = 0

    def setResultDir(self, result_dir) -> None:
        self.resultDir = Path(result_dir)

    def setCSTRunResultDir(self, result_dir) -> None:
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
        ])

    def appendPostProcessSteps(self, settings: Sequence[Mapping[str, Any]]) -> None:
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
                self._required(params, "xoffset", method),
                self._required(params, "yoffset", method),
                result_name,
            )
            return

        if method.endswith("_All") and method[:-4] in self._COMPLEX_METRICS:
            base_method = method[:-4]
            self._add_complex_metric_all(
                base_method,
                self._required(params, "xoffset", method),
                self._required(params, "yoffset", method),
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
        xoffset: float,
        yoffset: float,
        result_name: str,
    ) -> None:
        query, token = self._COMPLEX_METRICS[method]
        filename = self._unique_filename(
            f"Mode_{mode}_{token}_xoffset_{xoffset:f}_yoffset_{yoffset:f}_{result_name}.txt"
        )
        call = (
            f'EigenResult_Complex_output({mode},"{self._vb_string(query)}",3,'
            f'{xoffset},{yoffset},0,outFullDir,"{self._vb_string(filename)}")\n'
        )
        self._register(
            import_file="EigenResult_Complex_All.vb",
            result_name=result_name,
            result_filename=filename,
            function_call=call,
            reader=self._read_scalar,
            params={"iModeNumber": mode, "xoffset": xoffset, "yoffset": yoffset},
        )

    def _add_complex_metric_all(
        self,
        method: str,
        xoffset: float,
        yoffset: float,
        result_name: str,
    ) -> None:
        query, token = self._COMPLEX_METRICS[method]
        filename = self._unique_filename(
            f"{token}_All_xoffset_{xoffset:f}_yoffset_{yoffset:f}_{result_name}.txt"
        )
        call = (
            f'EigenResult_Complex_All_output("{self._vb_string(query)}",3,'
            f'{xoffset},{yoffset},0,outFullDir,"{self._vb_string(filename)}")\n'
        )
        self._register(
            import_file="EigenResult_Complex_All.vb",
            result_name=result_name,
            result_filename=filename,
            function_call=call,
            reader=self.EigenResult_All_readout,
            params={"xoffset": xoffset, "yoffset": yoffset},
        )

    def createPostProcessVBCodeLines(self) -> list[str]:
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

    def readAllResults(self) -> list[dict[str, Any]]:
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
        input_path = Path(path)
        if not input_path.exists():
            return None
        values: dict[str, str] = {}
        nonempty = [
            line.strip()
            for line in input_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for index in range(0, len(nonempty) - 1, 2):
            values[nonempty[index]] = nonempty[index + 1]
        return values

    def _result_path(self, filename: str | None) -> Path:
        if self.resultDir is None:
            raise RuntimeError("resultDir has not been configured")
        if filename is None:
            raise ValueError("This result has no output filename")
        return self.resultDir / filename

    def _read_scalar(self, filename: str | None) -> float:
        path = self._result_path(filename)
        values = self.readFile(path)
        if values is None:
            raise FileNotFoundError(path)
        return float(values["value"])

    def EigenResult_All_readout(self, filename: str | None) -> dict[str, float]:
        path = self._result_path(filename)
        values = self.readFile(path)
        if values is None:
            raise FileNotFoundError(path)
        return {
            key: float(value)
            for key, value in values.items()
            if "ModeIndex" in key
        }

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
        return allModesResult(self.resultDir)

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
        input_path = Path(path)
        if not input_path.exists():
            raise FileNotFoundError(input_path)
        with input_path.open("r") as source:
            first_line = source.readline()
        return float(first_line) if first_line else None

    # Compatibility wrappers used by the GUI and older scripts.
    def R_over_Q_zaxis(self, iModeNumber, xoffset, yoffset, resultName):
        self._add_complex_metric("R_over_Q", iModeNumber, xoffset, yoffset, resultName)

    def R_over_Q_zaxis_All(self, xoffset, yoffset, resultName):
        self._add_complex_metric_all("R_over_Q", xoffset, yoffset, resultName)

    def Shunt_Inpedence_zaxis(self, iModeNumber, xoffset, yoffset, resultName):
        self._add_complex_metric(
            "Shunt_Inpedence", iModeNumber, xoffset, yoffset, resultName
        )

    def Shunt_Inpedence_zaxis_All(self, xoffset, yoffset, resultName):
        self._add_complex_metric_all("Shunt_Inpedence", xoffset, yoffset, resultName)

    def R_over_Q_zaxis_readout(self, resultFilename):
        return self._read_scalar(resultFilename)

    def Shunt_Inpedence_zaxis_readout(self, resultFilename):
        return self._read_scalar(resultFilename)


def _install_simple_compatibility_methods() -> None:
    """Expose the historical per-metric methods without repeating their bodies."""

    def make_single(method_name: str):
        def single(self, iModeNumber, resultName):
            self._add_simple_metric(method_name, iModeNumber, resultName)

        single.__name__ = method_name
        return single

    def make_all(method_name: str):
        def all_modes(self, resultName):
            self._add_simple_metric_all(method_name, resultName)

        all_modes.__name__ = f"{method_name}_All"
        return all_modes

    def scalar_readout(self, resultFilename):
        return self._read_scalar(resultFilename)

    for method_name in VBPostProcessor._SIMPLE_METRICS:
        setattr(VBPostProcessor, method_name, make_single(method_name))
        setattr(VBPostProcessor, f"{method_name}_All", make_all(method_name))
        reader_name = f"{method_name}_readout"
        reader = scalar_readout
        reader.__name__ = reader_name
        setattr(VBPostProcessor, reader_name, reader)


_install_simple_compatibility_methods()

# Historical class name retained for the current worker and GUI.
vbpostprocess = VBPostProcessor
