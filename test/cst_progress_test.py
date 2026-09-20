import time

from csttool.cst_progress import (
    CstLogProgressMonitor,
    CstLogProgressParser,
)


def _context():
    return {
        "task_id": "task-1",
        "interval_lo": 500.0,
        "interval_hi": 550.0,
    }


def test_parser_reports_pass_local_progress_and_deduplicates():
    parser = CstLogProgressParser("0", _context)

    stage = parser.feed_line("Eigenmodes, Pass 2:")
    progress = parser.feed_line("[========>                ] 37 %")
    duplicate = parser.feed_line("[========>                ] 37 %")

    assert stage.stage == "eigenmode-solver"
    assert stage.pass_name == "Pass 2"
    assert progress.local_percent == 37
    assert progress.interval_lo == 500.0
    assert progress.interval_hi == 550.0
    assert duplicate is None


def test_parser_does_not_present_refinement_as_overall_progress():
    parser = CstLogProgressParser("1", _context)

    event = parser.feed_line("Marked 4125 of 29439 for refinement.")

    assert event.stage == "mesh-refinement"
    assert event.local_percent is None


def test_monitor_tails_appended_log_without_blocking_writer(tmp_path):
    path = tmp_path / "cst.log"
    path.write_bytes(b"")
    events = []
    monitor = CstLogProgressMonitor(
        path,
        CstLogProgressParser("0", _context),
        events.append,
        poll_interval=0.01,
        encoding="utf-8",
    )
    monitor.start()
    with path.open("ab", buffering=0) as stream:
        stream.write(b"Eigenmodes, Pass 1:\r[====> ] 20 %\r")

    deadline = time.monotonic() + 1
    while len(events) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    monitor.stop()

    assert [(item.pass_name, item.local_percent) for item in events] == [
        ("Pass 1", None),
        ("Pass 1", 20),
    ]
