from pathlib import Path

from csttool.runtime_protocol import (
    Acknowledge,
    Completion,
    CompletionStatus,
    ErrorCode,
    ParameterAssignment,
    ParameterKind,
    Task,
    decode_ack,
    decode_completion,
    decode_task,
    encode_ack,
    encode_completion,
    encode_task,
)


DATA = Path("test/data/runtime_protocol_v1")
TASK_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = "22222222-2222-4222-8222-222222222222"


def fixture(name):
    return (DATA / name).read_text(encoding="ascii")


def test_python_codec_matches_frozen_golden_vectors():
    task = Task(
        TASK_ID,
        SESSION_ID,
        (
            ParameterAssignment("Rx", ParameterKind.LITERAL, "90.0"),
            ParameterAssignment("L", ParameterKind.EXPRESSION, "2 * Rx = L"),
        ),
    )
    success = Completion(TASK_ID, SESSION_ID, CompletionStatus.SUCCESS)
    failure = Completion(
        TASK_ID,
        SESSION_ID,
        CompletionStatus.FAILURE,
        ErrorCode.REBUILD_FAILED,
        "Rebuild returned False",
    )
    ack = Acknowledge(TASK_ID, SESSION_ID)

    assert encode_task(task) == fixture("task.txt")
    assert encode_completion(success) == fixture("completion-success.txt")
    assert encode_completion(failure) == fixture("completion-failure.txt")
    assert encode_ack(ack) == fixture("ack.txt")
    assert decode_task(fixture("task.txt")) == task
    assert decode_completion(fixture("completion-success.txt")) == success
    assert decode_completion(fixture("completion-failure.txt")) == failure
    assert decode_ack(fixture("ack.txt")) == ack


def test_vba_codec_is_a_library_with_required_contracts():
    source = Path("data/runtime_protocol_v1.vb").read_text(encoding="utf-8")
    lowered = source.lower()

    assert "sub main" not in lowered
    for symbol in (
        "Public Function CSTP_ReadTask",
        "Public Function CSTP_WriteCompletion",
        "Public Function CSTP_ReadAck",
        "Public Function CSTP_ReadStopRequest",
        "Public Function CSTP_WriteStopAck",
        "Private Function CSTP_AtomicWrite",
    ):
        assert symbol in source
    assert 'Name tempPath As filePath' in source
    assert 'task.Parameters(i).Kind <> "literal"' in source
    assert 'task.Parameters(i).Kind <> "expression"' in source
    assert "expectedSessionId" in source
    assert "On Error Resume Next" in source
    assert lowered.count("on error resume next") == 2
