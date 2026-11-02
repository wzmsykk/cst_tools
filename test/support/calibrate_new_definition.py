"""Calibrate second RunScript dispatch on a bound new 3D object, without solving."""
import argparse
from pathlib import Path
import sys
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from csttool.acceptance_session import exclusive_probe
from csttool.native_definition_builder import run_new_definition
from csttool.configuration import write_json_atomic
from csttool.vb_codec import quote_vb_string


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run-cst',action='store_true');args=parser.parse_args()
    if not args.run_cst:parser.error('--run-cst required')
    with exclusive_probe(ROOT):
        root=ROOT/'artifacts'/('new-dispatch-'+uuid4().hex[:8]);root.mkdir()
        print('DISPATCH_ROOT='+str(root),flush=True)
        q=lambda p:quote_vb_string(p)
        macro=f''''#Language "WWB-COM"
Option Explicit
Sub Main
 Dim f As Integer
    On Error GoTo Failed
 SaveAs "{q(root/'definition.cst')}", False
 f = FreeFile
 Open "{q(root/'completed.txt')}" For Output As #f
 Print #f, "simple-dispatch"
 Close #f
 Exit Sub
Failed:
 f = FreeFile
 Open "{q(root/'failed.txt')}" For Output As #f
 Print #f, CStr(Err.Number) & " " & Err.Description
 Close #f
End Sub
'''
        closure=run_new_definition(Path(r'D:\Program Files (x86)\CST Studio Suite 2022\CST DESIGN ENVIRONMENT.exe'),root/'definition.cst',root,macro)
        report=dict(closure=closure,executed=(root/'completed.txt').exists(),solver_start_calls=0)
        write_json_atomic(root/'acceptance.json',report)
        print(report,flush=True)


if __name__=='__main__':main()
