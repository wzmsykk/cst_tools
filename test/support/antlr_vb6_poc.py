"""Isolated, parse-only ANTLR VB6 experiment. Never imports or launches CST.

--prepare downloads pinned upstream inputs into artifacts and generates Python.
Normal runs use those local inputs, with no Java or network required.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "b96e04db9d54bb313e542cc3e6ee913900a21520"
VERSION = "4.13.2"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare(directory, java):
    """Build only in the explicitly selected artifacts directory."""
    inputs = directory / "inputs"
    generated = directory / "generated"
    runtime = directory / "runtime"
    for path in (inputs, generated, runtime):
        path.mkdir(exist_ok=True)
    sources = [
        ("VisualBasic6Lexer.g4", f"https://raw.githubusercontent.com/antlr/grammars-v4/{COMMIT}/vb6/VisualBasic6Lexer.g4"),
        ("VisualBasic6Parser.g4", f"https://raw.githubusercontent.com/antlr/grammars-v4/{COMMIT}/vb6/VisualBasic6Parser.g4"),
        ("antlr-4.13.2-complete.jar", "https://www.antlr.org/download/antlr-4.13.2-complete.jar"),
        ("ANTLR-LICENSE.txt", "https://raw.githubusercontent.com/antlr/antlr4/4.13.2/LICENSE.txt"),
    ]
    manifest = []
    for filename, url in sources:
        path = inputs / filename
        with urllib.request.urlopen(url, timeout=60) as response:
            path.write_bytes(response.read())
        manifest.append(dict(path=str(path.relative_to(directory)), url=url, sha256=digest(path), bytes=path.stat().st_size))
    java_version = subprocess.run([java, "-version"], capture_output=True, text=True, check=True)
    command = [java, "-jar", str(inputs / "antlr-4.13.2-complete.jar"), "-Dlanguage=Python3", "-no-listener", "-no-visitor", "-o", str(generated), "VisualBasic6Lexer.g4", "VisualBasic6Parser.g4"]
    started = time.perf_counter()
    generation = subprocess.run(command, cwd=inputs, capture_output=True, text=True, timeout=120)
    (directory / "generation.log").write_text(generation.stdout + generation.stderr, encoding="utf-8")
    generation.check_returncode()
    generation_seconds = time.perf_counter() - started
    with (directory / "pip.log").open("w", encoding="utf-8") as log:
        subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "--target", str(runtime), f"antlr4-python3-runtime=={VERSION}"], stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
    save(directory / "build.json", dict(grammar_commit=COMMIT, antlr_version=VERSION, python=sys.version, java=java, java_version=java_version.stdout+java_version.stderr, command=command, generation_seconds=generation_seconds, inputs=manifest))


def load_parser(directory):
    sys.path[:0] = [str(directory / "runtime"), str(directory / "generated")]
    from antlr4 import InputStream, CommonTokenStream, Token
    from antlr4.error.ErrorListener import ErrorListener
    from antlr4.error.ErrorStrategy import BailErrorStrategy
    from antlr4.error.Errors import ParseCancellationException
    from antlr4.atn.PredictionMode import PredictionMode
    from VisualBasic6Lexer import VisualBasic6Lexer
    from VisualBasic6Parser import VisualBasic6Parser

    class Diagnostics(ErrorListener):
        def __init__(self, stage):
            self.stage = stage
            self.rows = []

        def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
            self.rows.append(dict(stage=self.stage, line_1based=line, column_0based=column, message=msg, token=getattr(offendingSymbol, "text", None)))

    def parse(source, fast=False):
        lexical, syntactic = Diagnostics("lexer"), Diagnostics("parser")
        lexer = VisualBasic6Lexer(InputStream(source))
        lexer.removeErrorListeners()
        lexer.addErrorListener(lexical)
        tokens = CommonTokenStream(lexer)
        parser = VisualBasic6Parser(tokens)
        parser.removeErrorListeners()
        parser.addErrorListener(syntactic)
        parser.buildParseTrees = False
        if fast:
            parser._interp.predictionMode = PredictionMode.SLL
            parser._errHandler = BailErrorStrategy()
        try:
            parser.startRule()
        except ParseCancellationException:
            if not fast:
                raise
            result = parse(source)
            result['fallback_ll'] = True
            token = parser.getCurrentToken()
            result['fallback_at'] = dict(line_1based=token.line, column_0based=token.column, token=token.text)
            return result
        tokens.fill()  # Include lexical errors even after parser recovery.
        errors = lexical.rows + syntactic.rows
        eof = tokens.LA(1) == Token.EOF
        return dict(accepted=not errors and eof, eof=eof, errors=errors, tokens=len(tokens.tokens), fallback_ll=False)

    return parse


def samples(directory):
    """Native labels describe prior evidence, not a new native test."""
    original = ' .Zrange ((-RestoreDoubleParameter("L"))/2), (RestoreDoubleParameter("L")/2)'
    fixed = ' .Zrange 0+((-RestoreDoubleParameter("L"))/2), 0+(RestoreDoubleParameter("L")/2)'
    def module(body):
        return 'Option Explicit\nSub Main\n' + body + '\nEnd Sub\n'
    marker = str(directory / "checked-body-executed.txt").replace(chr(34), chr(34)*2)
    cases = [
        ("body-not-executed", module('Open "'+marker+'" For Output As #1\nPrint #1, "MUST-NOT-RUN"\nClose #1'), "offline-parse-only", True),
        ("zrange-original", module('With Cylinder\n'+original+'\nEnd With'), "reconstructed-original-native-rejected", None),
        ("zrange-fixed", module('With Cylinder\n'+fixed+'\nEnd With'), "prior-native-accepted-call-shape", True),
        ("zrange-call", module('With Cylinder\n Call .Zrange((-RestoreDoubleParameter("L"))/2, RestoreDoubleParameter("L")/2)\nEnd With'), "not-native-tested", None),
        ("missing-quote", module('Dim s As String\ns = "oops'), "not-native-tested", False),
        ("missing-end-with", module('With Cylinder\n .Reset'), "not-native-tested", False),
        ("missing-end-sub", 'Sub Main\nDim x As Long\nx = 1\n', "not-native-tested", False),
        ("trailing-garbage", module('Dim x As Long\nx = 1')+'@@@\n', "not-native-tested", False),
        ("unicode-continuation", module('Dim s As String\ns = "中文路径" & _\n " quoted ""value"""'), "not-native-tested", True),
        ("byref-array", 'Option Explicit\nSub Fill(ByRef items() As String)\n items(0) = "x"\nEnd Sub\nSub Main\n Dim values(0 To 1) As String\n Fill values()\nEnd Sub\n', "not-native-tested", True),
        ("duplicate-declaration", module('Dim x As String\nDim x As Integer'), "semantic-only-not-native-tested", None),
        ("unknown-cst-member", module('With Cylinder\n .W0NonexistentMethod 1\nEnd With'), "semantic-only-not-native-tested", None),
        ("wwb-header", '\'#Language "WWB-COM"\n'+module('Dim x As Double\nx = 1'), "prior-native-header-form", True),
    ]
    # Actual retained successful history; do not regenerate it with today's emitter.
    evidence = ROOT / 'test/fixtures/antlr-vb6-poc/retained-history.vb'
    if evidence.exists():
        cases.append(("retained-history-wrapped", module(evidence.read_text(encoding="utf-8")), "retained-successful-candidate-history", True))
    fixture = ROOT / 'test/fixtures/a1-pillbox-history.vb'
    cases.append(("a1-fixture-wrapped", module(fixture.read_text(encoding="utf-8")), "synthetic-offline-fixture-not-native-evidence", True))
    return cases


def benchmark(directory, repeats):
    started = time.perf_counter()
    parse = load_parser(directory)
    import_seconds = time.perf_counter() - started
    rows = []
    case_dir = directory / "cases"
    case_dir.mkdir(exist_ok=True)
    for name, code, native, expected in samples(directory):
        path = case_dir / (name + '.bas')
        path.write_text(code, encoding="utf-8")
        started = time.perf_counter()
        result = parse(code)
        first_ms = (time.perf_counter() - started)*1000
        times = []
        diagnostic_variants = {json.dumps(result["errors"], sort_keys=True)}
        for _ in range(repeats):
            started = time.perf_counter()
            repeated = parse(code)
            times.append((time.perf_counter()-started)*1000)
            diagnostic_variants.add(json.dumps(repeated['errors'], sort_keys=True))
            if (repeated['accepted'], repeated['eof']) != (result['accepted'], result['eof']):
                raise AssertionError('nondeterministic verdict: '+name)
        print(name, 'ACCEPT' if result['accepted'] else 'REJECT', round(statistics.median(times),3), 'ms', flush=True)
        fast_times = []
        for _ in range(repeats):
            started = time.perf_counter()
            fast_result = parse(code, fast=True)
            fast_times.append((time.perf_counter()-started)*1000)
            if (fast_result['accepted'], fast_result['eof']) != (result['accepted'], result['eof']):
                raise AssertionError('SLL/LL verdict mismatch: '+name)
        rows.append(dict(fast_median_ms=statistics.median(fast_times), fast_fallback_ll=fast_result['fallback_ll'], fast_fallback_at=fast_result.get('fallback_at'), diagnostic_variants=[json.loads(v) for v in sorted(diagnostic_variants)], name=name, source=str(path.relative_to(directory)), sha256=digest(path), bytes=len(code.encode('utf-8')), prior_native_evidence=native, expected_general_syntax=expected, first_ms=first_ms, warm_median_ms=statistics.median(times), warm_p95_ms=sorted(times)[max(0, int(.95*len(times))-1)], **result))
    sizes = {name:sum(p.stat().st_size for p in (directory/name).rglob('*') if p.is_file()) for name in ('inputs','runtime','generated')}
    distribution = importlib.metadata.distribution('antlr4-python3-runtime')
    footprint = {name:dict(total=sizes[name], python_source=sum(p.stat().st_size for p in (directory/name).rglob('*.py')), bytecode=sum(p.stat().st_size for p in (directory/name).rglob('*.pyc'))) for name in sizes}
    marker_absent = not (directory/'checked-body-executed.txt').exists()
    if not marker_absent:
        raise AssertionError('checked body sentinel exists; investigate before accepting no-execution claim')
    result = dict(body_execution_marker_absent=marker_absent, footprint=footprint, python=sys.version, runtime_version=distribution.version, runtime_requirements=distribution.requires or [], parse_only=True, native_execution=False, build= json.loads((directory/'build.json').read_text(encoding='utf-8')), import_seconds=import_seconds, repeat_count=repeats, directory_bytes=sizes, cases=rows)
    save(directory / 'report.json', result)
    # These assertions validate the harness and generic diagnostic fixtures,
    # intentionally NOT requiring rejection of the native Zrange counterexample.
    mismatches = [r['name'] for r in rows if r['expected_general_syntax'] is not None and r['accepted'] != r['expected_general_syntax']]
    for row in rows:
        print(row['name'], 'ACCEPT' if row['accepted'] else 'REJECT', round(row['warm_median_ms'],3), 'ms; fast', round(row['fast_median_ms'],3), 'ms', row['errors'][:1], flush=True)
    print('REPORT='+str(directory/'report.json'), 'MISMATCHES='+str(mismatches), flush=True)
    return result, mismatches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--java')
    parser.add_argument('--repeats', type=int, default=20)
    parser.add_argument('--cold-child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if not directory.is_relative_to(ROOT/'artifacts'):
        parser.error('PoC output must stay under workspace artifacts')
    if not 1 <= args.repeats <= 100:
        parser.error('repeats must be 1..100')
    directory.mkdir(parents=True, exist_ok=True)
    if args.cold_child:
        parse = load_parser(directory)
        parse('Sub Main\nEnd Sub\n')
        return
    if args.prepare:
        if not args.java:
            parser.error('--prepare requires --java')
        prepare(directory, args.java)
    result, mismatches = benchmark(directory, args.repeats)
    cold = []
    for _ in range(5):
        started = time.perf_counter()
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--directory', str(directory), '--cold-child'], check=True, stdout=subprocess.DEVNULL, timeout=30)
        cold.append((time.perf_counter()-started)*1000)
    result['cold_process_ms'] = cold
    result['cold_process_median_ms'] = statistics.median(cold)
    save(directory/'report.json', result)
    if mismatches:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
