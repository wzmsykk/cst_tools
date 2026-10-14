"""Typed Python worker boundary; CST's file protocol remains independent."""

from dataclasses import dataclass, field
from .cst_memory_guard import MemoryGuardPolicy
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
    memory_guard: MemoryGuardPolicy = field(default_factory=MemoryGuardPolicy)
    run_directory: Path | None = None
    project_directory: Path | None = None
    execution_fingerprint: str | None = None
    field_reference_result: Path | None = None
    field_match_policy: Mapping[str, Any] | None = None
    vacuum_domain: Mapping[str, Any] | None = None
    vacuum_reference_store: Path | None = None

    @classmethod
    def from_mapping(cls, values):
        """Explicit adapter for standalone harnesses using dictionary fixtures."""
        return cls(Path(values["taskFileDir"]), Path(values["resultDir"]),
                   Path(values["CSTENVPATH"]), Path(values["cstPath"]),
                   tuple(values["paramList"]), tuple(values.get("postProcess", ())),
                   bool(values.get("runInBackground", True)), values.get("progressCallback"),
                   field_reference_result=(Path(values['fieldReferenceResult']) if values.get('fieldReferenceResult') else None),
                   field_match_policy=values.get('fieldMatchPolicy'),
                   vacuum_domain=values.get('vacuumDomain'))


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
    receipt_path: Path | None = None
    field_diagnostic: Mapping[str, Any] | None = None
    field_artifacts: list[dict[str, Any]] | None = None
    domain_registration: Mapping[str, Any] | None = None

    def __getitem__(self, key):
        return self.to_mapping()[key]

    def __iter__(self):
        return iter(self.to_mapping())

    def __len__(self):
        return len(self.to_mapping())

    def to_mapping(self) -> dict[str, Any]:
        """Serialize at the existing algorithm result boundary."""
        result = {"WorkerID": self.worker_id, "TaskStatus": self.status,
                "RunName": self.job_name, "RunParameters": dict(self.parameters),
                "PostProcessResult": self.postprocess, "FailureReport": self.failure,
                "ProjectSnapshot": str(self.snapshot) if self.snapshot else None,
                "TaskID": self.task_id,
                "ResultDirectory": str(self.result_directory) if self.result_directory else None,
                "ReceiptPath": str(self.receipt_path) if self.receipt_path else None}
        if self.field_diagnostic is not None:
            result['FieldDiagnostic'] = dict(self.field_diagnostic)
        if self.field_artifacts is not None:
            result['FieldArtifacts'] = self.field_artifacts
        if self.domain_registration is not None:
            result['DomainRegistration'] = dict(self.domain_registration)
        return result
