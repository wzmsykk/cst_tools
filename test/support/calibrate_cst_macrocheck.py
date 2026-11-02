"""One owned new CST session, one RunScript, batch parse-only MacroCheckThis.

Requires explicit --run-cst. No solver, history execution or original project.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from csttool.acceptance_session import exclusive_probe, cst_processes
from csttool.configuration import write_json_atomic
from csttool.native_definition_builder import run_new_definition
from csttool.vb_codec import quote_vb_string


def cases(directory):
    def module(body):
        return '\'#Language "WWB-COM"\nOption Explicit\nSub Main\n'+body+'\nEnd Sub\n'
    original = '((-RestoreDoubleParameter("L"))/2), (RestoreDoubleParameter("L")/2)'
    fixed = '0+((-RestoreDoubleParameter("L"))/2), 0+(RestoreDoubleParameter("L")/2)'
    q = quote_vb_string(directory/'checked-body-executed.txt')
    rows = [
        ('body-marker', module(f'Open "{q}" For Output As #1\nPrint #1, "MUST-NOT-RUN"\nClose #1'), True),
        ('parameter-write', module('StoreParameter "L", "999"'), True),
        ('obvious-syntax-error', module('Dim w0x As Double\nw0x = ('), False),
        ('zrange-original', module('With Cylinder\n .Zrange '+original+'\nEnd With'), False),
        ('zrange-fixed', module('With Cylinder\n .Zrange '+fixed+'\nEnd With'), True),
        ('zrange-call', module('With Cylinder\n Call .Zrange('+original+')\nEnd With'), None),
        ('duplicate-declaration', module('Dim w0x As String\nDim w0x As Integer'), False),
        ('missing-end-with', module('With Cylinder\n .Reset'), False),
        ('unicode', module('Dim w0text As String\nw0text = "中文"'), True),
        ('parameter-read', module('Dim w0x As Double\nw0x = RestoreDoubleParameter("L")'), True),
        ('inner-history-text', module('Dim w0ok As Boolean\nw0ok = AddToHistory("W0", "not valid history ! (")'), True),
    ]
    for axis in 'XY':
        rows.append((axis.lower()+'range-fixed', module('With Cylinder\n .'+axis+'range '+fixed+'\nEnd With'), True))
    history = (ROOT/'test/fixtures/antlr-vb6-poc/retained-history.vb').read_text(encoding='utf-8')
    rows.append(('retained-history-wrapped', module(history), True))
    return rows


def render(directory, samples, nonce):
    q = lambda s: '"'+quote_vb_string(s)+'"'
    statements = []
    for name, source, _ in samples:
        statements += ['    w0code = ""']
        for line in source.splitlines():
            for index in range(0, len(line), 24):
                statements.append('    w0code = w0code & '+q(line[index:index+24]))
            statements.append('    w0code = w0code & vbCrLf')
        statements.append('    W0Check '+q(name)+', w0code')
    return ''''#Language "WWB-COM"
Option Explicit
Sub Main
    Dim w0code As String, w0f As Integer, w0message As String
    On Error GoTo Failed
    StoreParameter "W0Base", "2"
    StoreParameter "L", "2 * W0Base"
    StoreParameter "R", "2"
'''+ '\n'.join(statements)+f'''
    w0f = FreeFile
    Open {q(directory/'parameter-after.txt')} For Output As #w0f
    Print #w0f, RestoreParameterExpression("L")
    Close #w0f
    SaveAs {q(directory/'definition.cst')}, False
    w0f = FreeFile
    Open {q(directory/'completed.txt')} For Output As #w0f
    Print #w0f, {q(nonce)}
    Close #w0f
    Exit Sub
Failed:
    w0message = CStr(Err.Number) & " " & Err.Description & " source=" & Err.Source
    On Error Resume Next
    Close
    w0f = FreeFile
    Open {q(directory/'failed.txt')} For Output As #w0f
    Print #w0f, w0message
    Close #w0f
End Sub

Private Sub W0Check(ByVal w0name As String, ByVal w0source As String)
 Dim w0error As ErrObject, w0stream As Integer
 w0stream = FreeFile
 Open {q(directory/'stages.tsv')} For Append As #w0stream
 Print #w0stream, w0name & vbTab & "begin"
 Close #w0stream
 Set w0error = MacroCheckThis(w0source)
 w0stream = FreeFile
 Open {q(directory/'checks.tsv')} For Append As #w0stream
 If w0error Is Nothing Then
  Print #w0stream, w0name & vbTab & "accepted"
 Else
  Print #w0stream, w0name & vbTab & "rejected"
 End If
 Close #w0stream
 If Not w0error Is Nothing Then
  w0stream = FreeFile
  Open {q(str(directory)+chr(92))} & w0name & ".error.txt" For Output As #w0stream
  Print #w0stream, CStr(w0error.Number)
  Print #w0stream, w0error.Description
  Print #w0stream, w0error.Source
  Close #w0stream
 End If
End Sub
'''


def evaluate(directory, samples, closure, nonce):
    checks = directory/'checks.tsv'
    pairs = [line.split('\t') for line in checks.read_text(encoding='mbcs').splitlines()] if checks.exists() else []
    results = []
    for name, source, expected in samples:
        found = [row[1] for row in pairs if len(row)==2 and row[0]==name]
        error = directory/(name+'.error.txt')
        raw_error = error.read_text(encoding='mbcs') if error.exists() else None
        results.append(dict(name=name, expected=expected, statuses=found,
                            error=raw_error, diagnostic=parse_error(raw_error),
                            source_sha256=hashlib.sha256(source.encode('utf-8')).hexdigest()))
    completed = directory/'completed.txt'
    parameters = directory/'parameter-after.txt'
    matches = lambda row: len(row['statuses'])==1 and (row['expected'] is None or (row['statuses'][0]=='accepted')==row['expected'])
    marker_absent = not (directory/'checked-body-executed.txt').exists()
    expression = parameters.read_text(encoding='mbcs').strip() if parameters.exists() else None
    quiet = closure.get('quiet') or {}
    windows = closure.get('window_observation') or {}
    binding_path = directory/'identity-bound.json'
    binding = json.loads(binding_path.read_text(encoding='utf-8')) if binding_path.exists() else {}
    background = (binding.get('nonce') is not None and quiet.get('nonce')==binding['nonce']
                  and quiet.get('setter_returned') is True
                  and windows.get('owned_foreground_events')==0
                  and not windows.get('errors') and windows.get('dropped_events')==0)
    complete = (closure.get('exit_confirmed') is True and closure.get('exit_code')==0
                and completed.exists() and completed.read_text(encoding='ascii').strip()==nonce
                and not (directory/'failed.txt').exists() and marker_absent
                and expression=='2 * W0Base' and len(pairs)==len(samples) and all(map(matches,results))
                and background)
    return dict(acceptance_passed=complete, closure=closure, marker_absent=marker_absent,
                parameter_expression_after=expression, cases=results, checks=len(pairs), solver_start_calls=0,
                background_verified=background,
                failure=(directory/'failed.txt').read_text(encoding='mbcs') if (directory/'failed.txt').exists() else None)


def parse_error(raw):
    """Decode observed Source framing; preserve unknown forms without guessing."""
    if raw is None:
        return None
    rows = raw.splitlines()
    source = '\n'.join(rows[2:]).rstrip()
    match = re.fullmatch(r'\[(?P<module>[^\]\r\n]+)#(?P<line>\d+)\] (?P<statement>.*)', source)
    return dict(number=int(rows[0]) if rows and rows[0].isdigit() else None,
                description=rows[1] if len(rows)>1 else None, source=source,
                module=match['module'] if match else None,
                wrapped_line_1based=int(match['line']) if match else None,
                original_statement=match['statement'] if match else None,
                column=None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-cst', action='store_true')
    parser.add_argument('--cst-exe',type=Path,default=Path('D:/Program Files (x86)/CST Studio Suite 2022/CST DESIGN ENVIRONMENT.exe'))
    args = parser.parse_args()
    if not args.run_cst: parser.error('--run-cst required')
    with exclusive_probe(ROOT):
        directory = ROOT/'artifacts'/('cst-macrocheck-'+uuid4().hex[:8])
        directory.mkdir()
        print('PROBE_ROOT='+str(directory),flush=True)
        nonce = uuid4().hex
        samples = cases(directory)
        for name, source, _ in samples:
            (directory/(name+'.bas')).write_text(source,encoding='utf-8')
        write_json_atomic(directory/'source-map.json',dict(nonce=nonce,wrapper_lines=3,
                          cases=[dict(name=name,expected=expected,sha256=hashlib.sha256(source.encode('utf-8')).hexdigest()) for name,source,expected in samples]))
        macro = render(directory,samples,nonce)
        closure = run_new_definition(args.cst_exe,directory/'definition.cst',directory,macro)
        report = evaluate(directory,samples,closure,nonce)
        report['after_cst'] = cst_processes()
        write_json_atomic(directory/'acceptance.json',report)
        windows=closure.get('window_observation') or {}
        print(json.dumps(dict(root=str(directory),acceptance_passed=report['acceptance_passed'],
            checks=report['checks'],background_verified=report['background_verified'],
            owned_foreground_events=windows.get('owned_foreground_events'),
            window_errors=windows.get('errors'),closure_exit=closure.get('exit_code'),
            exit_confirmed=closure.get('exit_confirmed')),ensure_ascii=True),flush=True)
        if not report['acceptance_passed']:raise SystemExit(2)


if __name__=='__main__':main()
