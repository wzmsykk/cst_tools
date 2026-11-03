"""CreateProcessW adapter for an explicit desktop, which Popen doesn't expose.

Only supplies pid/poll/returncode required by the existing lifecycle observer.
Closing handles never terminates a live process.
"""
import ctypes
from ctypes import wintypes
import subprocess


class DesktopProcess:
    def __init__(self, command, *, desktop, cwd, env, log):
        import msvcrt
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel=kernel
        self.returncode=None
        self.handle=None

        class STARTUPINFO(ctypes.Structure):
            _fields_=[('cb',wintypes.DWORD),('lpReserved',wintypes.LPWSTR),('lpDesktop',wintypes.LPWSTR),
                      ('lpTitle',wintypes.LPWSTR),('dwX',wintypes.DWORD),('dwY',wintypes.DWORD),
                      ('dwXSize',wintypes.DWORD),('dwYSize',wintypes.DWORD),('dwXCountChars',wintypes.DWORD),
                      ('dwYCountChars',wintypes.DWORD),('dwFillAttribute',wintypes.DWORD),('dwFlags',wintypes.DWORD),
                      ('wShowWindow',wintypes.WORD),('cbReserved2',wintypes.WORD),('lpReserved2',ctypes.POINTER(ctypes.c_byte)),
                      ('hStdInput',wintypes.HANDLE),('hStdOutput',wintypes.HANDLE),('hStdError',wintypes.HANDLE)]
        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_=[('hProcess',wintypes.HANDLE),('hThread',wintypes.HANDLE),('dwProcessId',wintypes.DWORD),('dwThreadId',wintypes.DWORD)]

        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        kernel.DuplicateHandle.argtypes=[wintypes.HANDLE,wintypes.HANDLE,wintypes.HANDLE,
                                         ctypes.POINTER(wintypes.HANDLE),wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.DuplicateHandle.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel.CloseHandle.restype=wintypes.BOOL
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.WaitForSingleObject.restype=wintypes.DWORD
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype=wintypes.BOOL
        kernel.CreateProcessW.argtypes=[wintypes.LPCWSTR,wintypes.LPWSTR,ctypes.c_void_p,ctypes.c_void_p,
                                        wintypes.BOOL,wintypes.DWORD,ctypes.c_void_p,wintypes.LPCWSTR,
                                        ctypes.POINTER(STARTUPINFO),ctypes.POINTER(PROCESS_INFORMATION)]
        kernel.CreateProcessW.restype=wintypes.BOOL

        def duplicate(stream):
            handle=wintypes.HANDLE()
            current=kernel.GetCurrentProcess()
            if not kernel.DuplicateHandle(current,msvcrt.get_osfhandle(stream.fileno()),current,
                                          ctypes.byref(handle),0,True,2):
                raise ctypes.WinError(ctypes.get_last_error())
            return handle

        inherited=[]
        try:
            output=duplicate(log);inherited.append(output)
            with open('NUL','rb') as null:
                input_handle=duplicate(null);inherited.append(input_handle)
            startup=STARTUPINFO()
            startup.cb=ctypes.sizeof(startup)
            startup.lpDesktop=desktop
            startup.dwFlags=0x100|1  # USESTDHANDLES | USESHOWWINDOW
            startup.wShowWindow=7
            startup.hStdInput=input_handle
            startup.hStdOutput=startup.hStdError=output
            info=PROCESS_INFORMATION()
            environment=ctypes.create_unicode_buffer('\0'.join(k+'='+v for k,v in sorted(env.items(),key=lambda pair:pair[0].upper()))+'\0\0')
            line=ctypes.create_unicode_buffer(subprocess.list2cmdline([str(x) for x in command]))
            if not kernel.CreateProcessW(None,line,None,None,True,0x08000000|0x400|0x200,
                                          environment,str(cwd),ctypes.byref(startup),ctypes.byref(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.pid=info.dwProcessId
            self.handle=info.hProcess
            kernel.CloseHandle(info.hThread)
        finally:
            for handle in inherited:
                kernel.CloseHandle(handle)

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        status=self.kernel.WaitForSingleObject(self.handle,0)
        if status==258:
            return None
        if status!=0:
            raise ctypes.WinError(ctypes.get_last_error())
        code=wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle,ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.returncode=code.value
        self.close()
        return self.returncode

    def close(self):
        if getattr(self,'handle',None):
            self.kernel.CloseHandle(self.handle)
            self.handle=None

    def wait(self, timeout=None):
        import time
        deadline=None if timeout is None else time.monotonic()+timeout
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired('owned desktop process',timeout)
            time.sleep(.05)
        return self.returncode

    def __del__(self):
        self.close()
