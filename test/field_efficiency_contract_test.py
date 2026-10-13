"""Offline guards for the explicit, opt-in CST efficiency benchmark."""
from pathlib import Path
import re


def test_benchmark_does_not_recalculate_or_change_parameters():
    macro = (Path(__file__).parent / 'support/field_efficiency.bas').read_text()
    assert 'SaveAs "%PROJECT%", True' in macro
    assert 'Solver.Start' not in macro
    assert 'StoreParameter' not in macro
    assert 'Rebuild' not in macro


def test_vba_string_concatenation_does_not_become_long_type_suffix():
    macro = (Path(__file__).parent / 'support/field_efficiency.bas').read_text()
    assert re.search(r'\b[A-Za-z_]\w*&\s*"', macro) is None


def test_native_export_covers_both_modes_and_complex_samples():
    macro = (Path(__file__).parent / 'support/field_efficiency.bas').read_text()
    assert macro.count('For m=1 To 2') == 3
    assert 'Array("xre","yre","zre","xim","yim","zim")' in macro
    assert '.SetfileType "hdf5"' in macro
    assert '.SetPoints xs,ys,zs' in macro


def test_native_dot_benchmark_validates_conjugation_and_same_index_reference():
    macro = (Path(__file__).parent / 'support/field_native_efficiency.bas').read_text()
    assert 'synthetic-raw' in macro
    assert 'synthetic-conjugated' in macro
    assert 'ra.Conjugate\n        ra.DotProduct rb,rr,ii' in macro
    assert 'n<>rb.GetLength Or n<1' in macro
    assert 'reference-sum' in macro
    assert re.search(r'\b[A-Za-z_]\w*&\s*"', macro) is None
    assert 'Solver.Start' not in macro
