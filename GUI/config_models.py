"""Typed GUI configuration models with legacy serialization compatibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from csttool.postprocess_cst import VBPostProcessor


PPS_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AlgorithmSettings:
    fmin: float
    fmax: float
    endfreq: float
    cfreq: float
    cflag: bool

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "AlgorithmSettings":
        settings = cls(
            fmin=float(values.get("fmin", 500)),
            fmax=float(values.get("fmax", 700)),
            endfreq=float(values.get("endfreq", 2500)),
            cfreq=float(values.get("cfreq", 650)),
            cflag=bool(values.get("cflag", False)),
        )
        if settings.fmin >= settings.fmax:
            raise ValueError("最低频率必须小于最高频率")
        if settings.endfreq < settings.fmax:
            raise ValueError("扫描频率上限不能低于最高频率")
        if settings.cflag and not settings.fmin <= settings.cfreq <= settings.endfreq:
            raise ValueError("继续频率必须位于扫描频率范围内")
        return settings

    def to_legacy_dict(self) -> dict[str, float | int]:
        return {
            "fmin": self.fmin,
            "fmax": self.fmax,
            "endfreq": self.endfreq,
            "cfreq": self.cfreq,
            "cflag": int(self.cflag),
        }


_DISPLAY_NAMES = {
    "R_over_Q": "R/Q",
    "Shunt_Inpedence": "Shunt Impedance",
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
        if base in {"R_over_Q", "Shunt_Inpedence"}:
            for key in ("xoffset", "yoffset"):
                try:
                    normalized[key] = float(normalized[key])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(f"{method} 的 {key} 必须是数字") from exc
        return cls(result_name.strip(), str(method), normalized)

    @property
    def display_text(self) -> str:
        return f"{self.result_name} — {postprocess_display_name(self.method)}"

    def to_legacy_dict(self) -> dict[str, Any]:
        return {
            "resultName": self.result_name,
            "method": self.method,
            "params": dict(self.params),
        }


def decode_postprocess_document(document: Any) -> list[PostProcessSetting]:
    if isinstance(document, list):
        entries = document
    elif isinstance(document, Mapping):
        version = document.get("schemaVersion")
        if version != PPS_SCHEMA_VERSION:
            raise ValueError(f"不支持的后处理配置版本: {version!r}")
        entries = document.get("postProcesses")
    else:
        raise ValueError("后处理配置必须是列表或版本化对象")
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
        "postProcesses": [item.to_legacy_dict() for item in settings],
    }
