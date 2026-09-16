"""Build the bounded two-task Warm Worker used by the P4 gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from install_compat import resource_path

from .project_profile import ProjectProfile, ResultTemplateRequirement
from .protocol_worker import _vb_string
from .runtime_protocol import FileProtocol, Task


@dataclass(frozen=True, slots=True)
class WarmTaskArtifact:
    task: Task
    result_root: Path
    snapshot_path: Path
    result_path: Path
    timing_path: Path


@dataclass(frozen=True, slots=True)
class WarmWorkerWorkspace:
    root: Path
    protocol: FileProtocol
    tasks: tuple[WarmTaskArtifact, WarmTaskArtifact]
    project_path: Path
    macro_path: Path
    marker_path: Path
    stop_request_path: Path
    stop_ack_path: Path
    profile_inventory_path: Path | None


def prepare_warm_worker_workspace(
    root: str | Path,
    tasks: tuple[Task, Task],
    source_project: str | Path,
    *,
    result_name: str,
    profile: ProjectProfile | None = None,
) -> WarmWorkerWorkspace:
    if len(tasks) != 2:
        raise ValueError("P4 Warm Worker requires exactly two tasks")
    if tasks[0].session_id != tasks[1].session_id:
        raise ValueError("Warm tasks must belong to the same worker session")
    if profile is not None:
        for task in tasks:
            profile.validate_task(task)

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    protocol = FileProtocol(root / "protocol")
    artifacts = []
    for task in tasks:
        protocol.submit(task)
        result_root = root / "results" / task.task_id
        result_root.mkdir(parents=True)
        snapshot_path = result_root / "project.cst"
        artifacts.append(WarmTaskArtifact(
            task=task,
            result_root=result_root,
            snapshot_path=snapshot_path,
            result_path=result_root / "project" / "Result" / f"{result_name}.rd0",
            timing_path=result_root / "timing.txt",
        ))

    project_path = root / "worker-input.cst"
    macro_path = root / "runtime_warm_worker_v1.bas"
    marker_path = root / "worker.result"
    profile_inventory_path = root / "profile-templates.tsv" if profile else None
    shutil.copy2(source_project, project_path)
    build_warm_worker_macro(
        macro_path,
        project_path=project_path,
        artifacts=(artifacts[0], artifacts[1]),
        protocol=protocol,
        marker_path=marker_path,
        session_id=tasks[0].session_id,
        profile=profile,
        profile_inventory_path=profile_inventory_path,
    )
    return WarmWorkerWorkspace(
        root=root,
        protocol=protocol,
        tasks=(artifacts[0], artifacts[1]),
        project_path=project_path,
        macro_path=macro_path,
        marker_path=marker_path,
        stop_request_path=protocol.root / "stop.request",
        stop_ack_path=protocol.root / "stop.ack",
        profile_inventory_path=profile_inventory_path,
    )


def build_warm_worker_macro(
    destination: str | Path,
    *,
    project_path: Path,
    artifacts: tuple[WarmTaskArtifact, WarmTaskArtifact],
    protocol: FileProtocol,
    marker_path: Path,
    session_id: str,
    profile: ProjectProfile | None = None,
    profile_inventory_path: Path | None = None,
) -> Path:
    codec = Path(resource_path("data/runtime_protocol_v1.vb")).read_text(encoding="utf-8")
    worker = Path(resource_path("data/runtime_warm_worker_v1_main.vb")).read_text(encoding="utf-8")
    replacements = {
        "%PROJECT_PATH%": _vb_string(project_path.absolute()),
        "%MARKER_PATH%": _vb_string(marker_path.absolute()),
        "%SESSION_ID%": _vb_string(session_id),
        "%STOP_REQUEST_PATH%": _vb_string((protocol.root / "stop.request").absolute()),
        "%STOP_ACK_PATH%": _vb_string((protocol.root / "stop.ack").absolute()),
    }
    for index, artifact in enumerate(artifacts):
        task_id = artifact.task.task_id
        replacements.update({
            f"%TASK_{index}_PATH%": _vb_string(protocol.task_path(task_id).absolute()),
            f"%COMPLETION_{index}_PATH%": _vb_string(
                (protocol.completed / f"{task_id}.completion").absolute()
            ),
            f"%ACK_{index}_PATH%": _vb_string((protocol.acks / f"{task_id}.ack").absolute()),
            f"%SNAPSHOT_{index}_PATH%": _vb_string(artifact.snapshot_path.absolute()),
            f"%RESULT_{index}_PATH%": _vb_string(artifact.result_path.absolute()),
            f"%TIMING_{index}_PATH%": _vb_string(artifact.timing_path.absolute()),
        })
    if profile is not None:
        if profile_inventory_path is None:
            raise ValueError("profile inventory path is required with a profile")
        worker = _install_profile_preflight(
            worker, profile.required_templates, profile_inventory_path
        )
    for placeholder, value in replacements.items():
        worker = worker.replace(placeholder, value)
    if "%" in worker:
        raise ValueError("warm worker macro contains an unresolved placeholder")
    output = "'#Language \"WWB-COM\"\n\nOption Explicit\n\n" + codec + "\n" + worker
    if output.lower().count("sub main") != 1:
        raise ValueError("warm worker macro must contain exactly one Sub Main")
    destination = Path(destination)
    destination.write_text(output, encoding="ascii", newline="\n")
    return destination


def _install_profile_preflight(
    worker: str,
    required_templates: tuple[ResultTemplateRequirement, ...],
    inventory_path: Path,
) -> str:
    marker = '    OpenFile "%PROJECT_PATH%"\n'
    if worker.count(marker) != 1:
        raise ValueError("warm worker open-project stage is ambiguous")
    checks = []
    for item in required_templates:
        arguments = ", ".join(
            f'"{_vb_string(value)}"'
            for value in (
                item.result_name,
                item.template_type,
                item.template_name,
                item.folder,
            )
        )
        message = _vb_string(f"missing registered template: {item.result_name}")
        checks.append(
            f"    If Not CSTPWW_HasRegisteredTemplate({arguments}) Then\n"
            f'        CSTPWW_PublishFailure "%COMPLETION_0_PATH%", profileTask, "PROFILE_CAPABILITY_MISSING", "{message}"\n'
            "        Quit\n"
            "        Exit Sub\n"
            "    End If\n"
        )
    preflight = (
        marker
        + '\n    CSTPWW_WriteMarker "%MARKER_PATH%", "stage:profile-preflight"\n'
        + '    If Not CSTP_ReadTask("%TASK_0_PATH%", "%SESSION_ID%", profileTask, profileErrorCode, profileErrorMessage) Then\n'
        + '        CSTPWW_WriteMarker "%MARKER_PATH%", "failure:" & profileErrorCode & ":" & profileErrorMessage\n'
        + "        Quit\n"
        + "        Exit Sub\n"
        + "    End If\n"
        + f'    CSTPWW_WriteTemplateInventory "{_vb_string(inventory_path.absolute())}"\n'
        + "".join(checks)
        + "\n"
    )
    worker = worker.replace(marker, preflight, 1)
    declarations = (
        "    Dim profileTask As CSTP_Task\n"
        "    Dim profileErrorCode As String\n"
        "    Dim profileErrorMessage As String\n"
    )
    worker = worker.replace(
        "    Dim errorMessage As String\n",
        declarations + "    Dim errorMessage As String\n",
        1,
    )
    helpers = [
        "",
        "Private Sub CSTPWW_WriteTemplateInventory(ByVal filePath As String)",
        "    Dim fileNumber As Integer",
        "    Dim resultName As String",
        "    Dim templateType As String",
        "    Dim templateName As String",
        "    Dim folder As String",
        "",
        "    fileNumber = FreeFile",
        "    Open filePath For Output As #fileNumber",
        "    ResetTemplateIterator",
        "    While GetNextTemplate(resultName, templateType, templateName, folder)",
        "        Print #fileNumber, resultName & Chr(9) & templateType & Chr(9) & templateName & Chr(9) & folder",
        "    Wend",
        "    Close #fileNumber",
        "End Sub",
        "",
        "Private Function CSTPWW_HasRegisteredTemplate(ByVal requiredResultName As String, ByVal requiredType As String, ByVal requiredTemplateName As String, ByVal requiredFolder As String) As Boolean",
        "    Dim resultName As String",
        "    Dim templateType As String",
        "    Dim templateName As String",
        "    Dim folder As String",
        "",
        "    CSTPWW_HasRegisteredTemplate = False",
        "    ResetTemplateIterator",
        "    While GetNextTemplate(resultName, templateType, templateName, folder)",
        "        If resultName = requiredResultName And templateType = requiredType And templateName = requiredTemplateName And folder = requiredFolder Then",
        "            CSTPWW_HasRegisteredTemplate = True",
        "            Exit Function",
        "        End If",
        "    Wend",
        "End Function",
        "",
    ]
    return worker + "\n".join(helpers)
