"""Typed GUI configuration models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from csttool.postprocess_cst import VBPostProcessor


PPS_SCHEMA_VERSION = 1


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
        raise ValueError(f"无法识别布尔值: {value!r}")
    return bool(value)


@dataclass(frozen=True)
class AlgorithmSettings:
    fmin: float
    fmax: float
    endfreq: float
    mesh_cells_per_wavelength: int
    mesh_convergence_enabled: bool
    mesh_convergence_start: int
    mesh_convergence_stop: int
    mesh_convergence_step: int
    mesh_convergence_tolerance: float

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "AlgorithmSettings":
        settings = cls(
            fmin=float(values.get("fmin", 500)),
            fmax=float(values.get("fmax", 700)),
            endfreq=float(values.get("endfreq", 2500)),
            mesh_cells_per_wavelength=int(
                values.get("mesh_cells_per_wavelength", 20)
            ),
            mesh_convergence_enabled=_as_bool(
                values.get("mesh_convergence_enabled", False)
            ),
            mesh_convergence_start=int(values.get("mesh_convergence_start", 10)),
            mesh_convergence_stop=int(values.get("mesh_convergence_stop", 30)),
            mesh_convergence_step=int(values.get("mesh_convergence_step", 5)),
            mesh_convergence_tolerance=float(
                values.get("mesh_convergence_tolerance", 0.01)
            ),
        )
        if settings.fmin >= settings.fmax:
            raise ValueError("最低频率必须小于最高频率")
        if settings.endfreq < settings.fmax:
            raise ValueError("扫描频率上限不能低于最高频率")
        if settings.mesh_cells_per_wavelength < 1:
            raise ValueError("每波长网格数必须是正整数")
        if (
            settings.mesh_convergence_start < 1
            or settings.mesh_convergence_stop < settings.mesh_convergence_start
            or settings.mesh_convergence_step < 1
        ):
            raise ValueError("Mesh 收敛范围必须是递增的正整数")
        if not 0 < settings.mesh_convergence_tolerance < 1:
            raise ValueError("Mesh 收敛容差必须在 0 和 1 之间")
        return settings

    def to_backend_payload(self) -> dict[str, float]:
        return {
            "fmin": self.fmin,
            "fmax": self.fmax,
            "endfreq": self.endfreq,
            "mesh_cells_per_wavelength": self.mesh_cells_per_wavelength,
            "mesh_convergence_enabled": self.mesh_convergence_enabled,
            "mesh_convergence_start": self.mesh_convergence_start,
            "mesh_convergence_stop": self.mesh_convergence_stop,
            "mesh_convergence_step": self.mesh_convergence_step,
            "mesh_convergence_tolerance": self.mesh_convergence_tolerance,
        }


_DISPLAY_NAMES = {
    "R_over_Q": "R/Q",
    "Shunt_Impedance": "Shunt Impedance",
    "Q_Factor": "Q Factor",
    "Q_Ext": "External Q",
    "Total_Loss": "Total Loss",
    "Loss_Enclosure": "Enclosure Loss",
    "Loss_Volume": "Volume Loss",
    "Loss_Surface": "Surface Loss",
    "Q_Enclosure": "Enclosure Q",
    "Q_Volume": "Volume Q",
    "Q_Surface": "Surface Q",
    "Total_Energy": "Total Energy",
    "Frequency": "Frequency",
    "ModeRec_All": "All-mode Record",
    "Direct_PPS_0D": "CST 0D Result",
}


def postprocess_display_name(method: str) -> str:
    base = method[:-4] if method.endswith("_All") else method
    label = _DISPLAY_NAMES.get(base, base.replace("_", " "))
    return f"{label} (all modes)" if method.endswith("_All") else label


@dataclass(frozen=True)
class PostProcessSetting:
    result_name: str
    method: str
    params: dict[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PostProcessSetting":
        if not isinstance(value, Mapping):
            raise ValueError("后处理条目必须是对象")
        result_name = value.get("resultName")
        method = value.get("method")
        params = value.get("params", {})
        if not isinstance(result_name, str) or not result_name.strip():
            raise ValueError("后处理结果名称不能为空")
        if method not in VBPostProcessor.supported_methods():
            raise ValueError(f"不支持的后处理方法: {method!r}")
        if not isinstance(params, Mapping):
            raise ValueError("后处理 params 必须是对象")
        normalized = dict(params)
        all_modes = method.endswith("_All") or method in {"ModeRec_All", "Direct_PPS_0D"}
        if not all_modes:
            mode = normalized.get("iModeNumber")
            if isinstance(mode, bool) or not isinstance(mode, int) or mode < 1:
                raise ValueError(f"{method} 的 Mode Index 必须是正整数")
        base = method[:-4] if method.endswith("_All") else method
        if base in {"R_over_Q", "Shunt_Impedance"}:
            axis = str(normalized.get("axis", "z")).strip().lower()
            if axis not in {"x", "y", "z"}:
                raise ValueError(f"{method} 的积分轴必须是 X、Y 或 Z")
            normalized["axis"] = axis
            for key in ("xoffset", "yoffset", "zoffset"):
                try:
                    normalized[key] = float(normalized.get(key, 0))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{method} 的 {key} 必须是数字") from exc
        return cls(result_name.strip(), str(method), normalized)

    @property
    def display_text(self) -> str:
        label = postprocess_display_name(self.method)
        base = self.method[:-4] if self.method.endswith("_All") else self.method
        if base in {"R_over_Q", "Shunt_Impedance"}:
            label = f"{label} [{self.params['axis'].upper()}轴]"
        return f"{self.result_name} — {label}"

    def to_backend_payload(self) -> dict[str, Any]:
        return {
            "resultName": self.result_name,
            "method": self.method,
            "params": dict(self.params),
        }


def decode_postprocess_document(document: Any) -> list[PostProcessSetting]:
    if isinstance(document, Mapping):
        version = document.get("schemaVersion")
        if version != PPS_SCHEMA_VERSION:
            raise ValueError(f"不支持的后处理配置版本: {version!r}")
        entries = document.get("postProcesses")
    else:
        raise ValueError("后处理配置必须是版本化对象")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
        raise ValueError("postProcesses 必须是列表")
    settings = [PostProcessSetting.from_mapping(item) for item in entries]
    names = [item.result_name for item in settings]
    if len(names) != len(set(names)):
        raise ValueError("后处理结果名称不能重复")
    return settings


def encode_postprocess_document(
    settings: Sequence[PostProcessSetting],
) -> dict[str, Any]:
    return {
        "schemaVersion": PPS_SCHEMA_VERSION,
        "postProcesses": [item.to_backend_payload() for item in settings],
    }
