"""Read installed COM type-library resources without registration or activation.

Runs only on Windows. Does not create COM classes, initialize WinWrap, read
license material, load the CST project model or invoke any inspected member.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path


def inspect(path):
    import pythoncom
    path = Path(path).resolve(strict=True)
    row = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    try:
        load = ctypes.OleDLL("oleaut32").LoadTypeLibEx
        load.argtypes = [ctypes.c_wchar_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        load.restype = ctypes.c_long
        pointer = ctypes.c_void_p()
        load(str(path), 2, ctypes.byref(pointer))  # REGKIND_NONE
        library = pythoncom.ObjectFromAddress(pointer.value, pythoncom.IID_ITypeLib)
        # Keep the loader's reference for this short-lived inspection process;
        # no raw COM Release/ownership assumptions are needed here.
        row["library"] = library.GetDocumentation(-1)
        row["interfaces"] = []
        for index in range(library.GetTypeInfoCount()):
            info = library.GetTypeInfo(index)
            attr = info.GetTypeAttr()
            functions = []
            for item in range(attr.cFuncs):
                function = info.GetFuncDesc(item)
                try:
                    functions.append(dict(names=info.GetNames(function.memid), documentation=info.GetDocumentation(function.memid)[1], invkind=function.invkind))
                except pythoncom.com_error as error:
                    functions.append(dict(memid=function.memid, error=str(error)))
            row["interfaces"].append(dict(name=library.GetDocumentation(index)[0], guid=str(attr.iid), kind=attr.typekind, functions=functions))
    except (OSError, pythoncom.com_error) as error:
        row["error"] = str(error)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", required=True, type=Path, help="selected CST AMD64 directory")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = [inspect(args.install / name) for name in ("WB9ENT64.OCX", "wwb9_64.dll", "CST DESIGN ENVIRONMENT_AMD64.exe", "modeler_AMD64.exe")]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
