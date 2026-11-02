"""Optional real-parser tests. Prepare the isolated PoC before running these."""
import importlib.util
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def poc():
    directory = os.environ.get("ANTLR_VB6_POC_DIRECTORY")
    if not directory:
        pytest.skip("explicit ANTLR_VB6_POC_DIRECTORY required; no production dependency")
    directory = Path(directory).resolve()
    if not directory.is_relative_to(ROOT / "artifacts"):
        pytest.fail("isolated PoC must be under workspace artifacts")
    spec = importlib.util.spec_from_file_location("antlr_vb6_poc", ROOT / "test/support/antlr_vb6_poc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_parser(directory), {name: code for name, code, _, _ in module.samples(directory)}


def test_known_native_counterexample_is_a_generic_parser_false_negative(poc):
    parse, cases = poc
    assert parse(cases["zrange-original"])["accepted"]
    assert parse(cases["zrange-fixed"])["accepted"]
    # This test deliberately documents the gap, not a successful WinWrap gate.


@pytest.mark.parametrize("name", ["missing-quote", "missing-end-with", "missing-end-sub", "trailing-garbage"])
def test_diagnostics_reject_recovery_trees_and_report_positions(poc, name):
    parse, cases = poc
    for fast in (False, True):
        result = parse(cases[name], fast=fast)
        assert not result["accepted"]
        assert result["errors"]
        assert all(e["line_1based"] >= 1 and e["column_0based"] >= 0 for e in result["errors"])
    if name == "missing-quote":
        assert result["errors"][0]["stage"] == "lexer"
        assert result["errors"][0]["line_1based"] == 4


@pytest.mark.parametrize("name", ["duplicate-declaration", "unknown-cst-member"])
def test_semantic_errors_are_outside_generic_syntax(poc, name):
    parse, cases = poc
    assert parse(cases[name], fast=True)["accepted"]


def test_parse_does_not_execute_source_and_fast_path_matches_full(poc, tmp_path):
    parse, cases = poc
    marker = tmp_path / "must-not-run.txt"
    source = 'Sub Main\nOpen "' + str(marker) + '" For Output As #1\nClose #1\nEnd Sub\n'
    assert parse(source)["accepted"]
    assert not marker.exists()
    for name in ("byref-array", "unicode-continuation", "retained-history-wrapped"):
        normal, fast = parse(cases[name]), parse(cases[name], fast=True)
        assert normal["accepted"] and fast["accepted"]
        assert normal["eof"] and fast["eof"]
