"""Build the bounded P5.6 native Result Template evaluation Gate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .hom_project_profile import HOM_PROFILE_V1
from .project_profile import ProjectProfile, ResultTemplateRequirement
from .protocol_worker import WorkerWorkspace, _vb_string, prepare_worker_workspace
from .runtime_protocol import Task


@dataclass(frozen=True, slots=True)
class ResultTemplateRecord:
    result_name: str
    template_type: str
    template_name: str
    folder: str


@dataclass(frozen=True, slots=True)
class HomTemplateEvaluationWorkspace:
    worker: WorkerWorkspace
    inventory_before_path: Path
    inventory_after_path: Path
    result_before_path: Path
    result_after_path: Path


def prepare_hom_template_evaluation_workspace(
    root: str | Path,
    task: Task,
    source_project: str | Path,
    *,
    result_name: str,
    profile: ProjectProfile = HOM_PROFILE_V1,
) -> HomTemplateEvaluationWorkspace:
    """Prepare a worker that inventories and re-evaluates existing templates."""
    profile.validate_task(task)
    worker = prepare_worker_workspace(root, task, source_project, result_name=result_name)
    inventory_before_path = worker.root / "templates-before.tsv"
    inventory_after_path = worker.root / "templates-after.tsv"
    result_before_path = worker.root / "native-before-evaluate.rd0"
    result_after_path = worker.root / "native-after-evaluate.rd0"
    live_result_path = worker.project_path.with_suffix("") / "Result" / f"{result_name}.rd0"
    _install_template_evaluation_extension(
        worker.macro_path,
        inventory_before_path=inventory_before_path,
        inventory_after_path=inventory_after_path,
        live_result_path=live_result_path,
        result_before_path=result_before_path,
        result_after_path=result_after_path,
        required_templates=profile.required_templates,
    )
    return HomTemplateEvaluationWorkspace(
        worker,
        inventory_before_path,
        inventory_after_path,
        result_before_path,
        result_after_path,
    )


def read_result_template_inventory(path: str | Path) -> tuple[ResultTemplateRecord, ...]:
    records = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="ascii").splitlines(), 1
    ):
        fields = line.split("\t")
        if len(fields) != 4:
            raise ValueError(
                f"invalid Result Template inventory line {line_number}: expected 4 fields"
            )
        records.append(ResultTemplateRecord(*fields))
    return tuple(records)


def _install_template_evaluation_extension(
    macro_path: Path,
    *,
    inventory_before_path: Path,
    inventory_after_path: Path,
    live_result_path: Path,
    result_before_path: Path,
    result_after_path: Path,
    required_templates: tuple[ResultTemplateRequirement, ...],
) -> None:
    macro = macro_path.read_text(encoding="ascii")
    solver = '    stage = "solver"\n'
    parameters = '    stage = "parameters"\n'
    flush = '    stage = "flush"\n'
    if (
        macro.count(solver) != 1
        or macro.count(parameters) != 1
        or macro.count(flush) != 1
    ):
        raise ValueError("one-shot worker stages are ambiguous")

    macro = macro.replace(
        parameters,
        '    stage = "template-inventory-before"\n'
        f'    CSTPW_WriteTemplateInventory "{_vb_string(inventory_before_path.absolute())}"\n\n'
        + _profile_checks(required_templates)
        + parameters,
        1,
    )
    macro = macro.replace(
        flush,
        '    stage = "template-evaluate-current-run"\n'
        f'    If Dir("{_vb_string(live_result_path.absolute())}") = "" Then\n'
        '        CSTPW_PublishFailure task, "TEMPLATE_RESULT_MISSING", "template result missing before explicit evaluation"\n'
        '        Exit Sub\n'
        '    End If\n'
        f'    FileCopy "{_vb_string(live_result_path.absolute())}", "{_vb_string(result_before_path.absolute())}"\n'
        '    EvaluateResultTemplates\n'
        f'    If Dir("{_vb_string(live_result_path.absolute())}") = "" Then\n'
        '        CSTPW_PublishFailure task, "TEMPLATE_EVALUATION_FAILED", "template result missing after explicit evaluation"\n'
        '        Exit Sub\n'
        '    End If\n'
        f'    FileCopy "{_vb_string(live_result_path.absolute())}", "{_vb_string(result_after_path.absolute())}"\n'
        f'    CSTPW_WriteTemplateInventory "{_vb_string(inventory_after_path.absolute())}"\n\n'
        + flush,
        1,
    )
    macro += '''
Private Sub CSTPW_WriteTemplateInventory(ByVal filePath As String)
    Dim fileNumber As Integer
    Dim resultName As String
    Dim templateType As String
    Dim templateName As String
    Dim folder As String

    fileNumber = FreeFile
    Open filePath For Output As #fileNumber
    ResetTemplateIterator
    While GetNextTemplate(resultName, templateType, templateName, folder)
        Print #fileNumber, resultName & Chr(9) & templateType & Chr(9) & templateName & Chr(9) & folder
    Wend
    Close #fileNumber
End Sub

Private Function CSTPW_HasRegisteredTemplate(ByVal requiredResultName As String, ByVal requiredType As String, ByVal requiredTemplateName As String, ByVal requiredFolder As String) As Boolean
    Dim resultName As String
    Dim templateType As String
    Dim templateName As String
    Dim folder As String

    CSTPW_HasRegisteredTemplate = False
    ResetTemplateIterator
    While GetNextTemplate(resultName, templateType, templateName, folder)
        If resultName = requiredResultName And templateType = requiredType And templateName = requiredTemplateName And folder = requiredFolder Then
            CSTPW_HasRegisteredTemplate = True
            Exit Function
        End If
    Wend
End Function
'''
    lowered = macro.lower()
    if lowered.count("sub main") != 1:
        raise ValueError("P5.6 worker must contain exactly one Sub Main")
    if lowered.count("eigenmodesolver.start") != 1:
        raise ValueError("P5.6 worker must contain exactly one solver call")
    if "update params" in lowered:
        raise ValueError("P5.6 worker must not update parameters after solving")
    macro_path.write_text(macro, encoding="ascii", newline="\n")


def _profile_checks(
    required_templates: tuple[ResultTemplateRequirement, ...],
) -> str:
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
            f"    If Not CSTPW_HasRegisteredTemplate({arguments}) Then\n"
            f'        CSTPW_PublishFailure task, "PROFILE_CAPABILITY_MISSING", "{message}"\n'
            "        Quit\n"
            "        Exit Sub\n"
            "    End If\n"
        )
    return "".join(checks) + "\n"
