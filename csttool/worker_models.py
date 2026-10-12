"""Typed Python worker boundary; CST's file protocol remains independent."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class WorkerConfig:
    task_directory: Path
    result_directory: Path
    executable: Path
    project_path: Path
    parameters: Sequence[Mapping[str, Any]]
    postprocess: Sequence[Mapping[str, Any]] = ()
    background: bool = True
    progress_callback: Callable | None = None

    @classmethod
    def from_mapping(cls, values):
        """Explicit adapter for standalone harnesses using dictionary fixtures."""
        return cls(Path(values["taskFileDir"]), Path(values["resultDir"]),
                   Path(values["CSTENVPATH"]), Path(values["cstPath"]),
                   tuple(values["paramList"]), tuple(values.get("postProcess", ())),
                   bool(values.get("runInBackground", True)), values.get("progressCallback"))


@dataclass(frozen=True, slots=True)
class SimulationResult(Mapping[str, Any]):
    worker_id: str
    status: str
    job_name: str
    parameters: Mapping[str, Any]
    postprocess: list[dict[str, Any]] | None
    failure: str | None = None
    snapshot: Path | None = None
    task_id: str = ""
    result_directory: Path | None = None

    def __getitem__(self, key):
        return self.to_mapping()[key]

    def __iter__(self):
        return iter(self.to_mapping())

    def __len__(self):
        return len(self.to_mapping())

    def to_mapping(self) -> dict[str, Any]:
        """Serialize at the existing algorithm result boundary."""
        return {"WorkerID": self.worker_id, "TaskStatus": self.status,
                "RunName": self.job_name, "RunParameters": dict(self.parameters),
                "PostProcessResult": self.postprocess, "FailureReport": self.failure,
                "ProjectSnapshot": str(self.snapshot) if self.snapshot else None,
                "TaskID": self.task_id,
                "ResultDirectory": str(self.result_directory) if self.result_directory else None}
