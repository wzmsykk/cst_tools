"""Explicit native Windows desktop check; no CST and no desktop switching."""
import json
import os
import sys
import time

import pytest

from csttool.cst_background import PrivateDesktop
from csttool.windows_desktop_process import DesktopProcess


@pytest.mark.skipif(os.name!='nt' or os.environ.get('CST_RUN_DESKTOP_TESTS')!='1',
                    reason='explicit normal-user Windows desktop test required')
def test_createprocess_uses_real_requested_desktop_and_closes_process_handle(tmp_path):
    source='''import ctypes,json
from ctypes import wintypes
u=ctypes.WinDLL('user32');k=ctypes.WinDLL('kernel32')
u.GetThreadDesktop.argtypes=[wintypes.DWORD];u.GetThreadDesktop.restype=wintypes.HANDLE
u.GetUserObjectInformationW.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
name=ctypes.create_unicode_buffer(256);size=wintypes.DWORD()
ok=u.GetUserObjectInformationW(u.GetThreadDesktop(k.GetCurrentThreadId()),2,name,ctypes.sizeof(name),ctypes.byref(size))
print(json.dumps({'ok':bool(ok),'desktop':name.value}))
'''
    with PrivateDesktop() as desktop:
        with (tmp_path/'child.log').open('wb') as log:
            child=DesktopProcess([sys.executable,'-c',source],desktop='WinSta0\\'+desktop.name,
                                 cwd=tmp_path,env=dict(os.environ),log=log)
            deadline=time.monotonic()+10
            while child.poll() is None and time.monotonic()<deadline:time.sleep(.02)
            assert child.poll()==0
            assert child.handle is None
        data=json.loads((tmp_path/'child.log').read_text(encoding='utf-8'))
        assert data==dict(ok=True,desktop=desktop.name)
    assert desktop.handle is None
