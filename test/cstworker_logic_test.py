import logging

from csttool.cstworker import local_cstworker
from csttool.postprocess_cst import VBPostProcessor


class StubPostProcessor:
    def __init__(self):
        self.result_dir = None
        self.cst_result_dir = None

    def setResultDir(self, path):
        self.result_dir = path

    def setCSTRunResultDir(self, path):
        self.cst_result_dir = path

    def readAllResults(self):
        return [{"resultName": "frequency", "value": 500.0}]


def worker_without_cst(tmp_path):
    instance = local_cstworker.__new__(local_cstworker)
    instance._ID = 0
    instance.cstStatus = "on"
    instance.resultDir = tmp_path / "result"
    instance.resultDir.mkdir()
    instance.taskFileDir = tmp_path / "task"
    instance.taskFileDir.mkdir()
    instance.runName = "run-1"
    instance.cstType = "default"
    instance.taskIndex = 0
    instance.runParams = {"Rx": 90.0}
    instance.postProcessHelper = StubPostProcessor()
    instance.logger = logging.getLogger("cstworker-logic-test")
    return instance


def test_existing_failure_returns_failure_without_reading_results(tmp_path):
    instance = worker_without_cst(tmp_path)
    (instance.taskFileDir / "0.failure").write_text(
        "run-1\n\nStructureError\n", encoding="utf-8"
    )

    result = instance.run()

    assert result["TaskStatus"] == "Failure"
    assert result["FailureReport"] == "StructureError"
    assert result["TaskIndex"] == 0
    assert result["PostProcessResult"] is None
    assert instance.taskIndex == 0


def test_success_reports_completed_index_before_advancing(tmp_path):
    instance = worker_without_cst(tmp_path)
    (instance.taskFileDir / "0.success").write_text(
        "run-1\n\nsuccess\n", encoding="utf-8"
    )

    result = instance.run()

    assert result["TaskStatus"] == "Success"
    assert result["TaskIndex"] == 0
    assert instance.taskIndex == 1


def test_missing_direct_0d_result_is_a_failure(tmp_path):
    with __import__("pytest").raises(FileNotFoundError):
        VBPostProcessor.cst0dreadout(tmp_path / "missing.rd0")
