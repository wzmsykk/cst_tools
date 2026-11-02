"""Owned CST window observation and non-activating minimization on Windows.

Never selects a global CST instance, answers dialogs or changes foreground focus.
WinEvents cover startup before binding; actions require live PID/time/path proof.
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import threading
import time
from uuid import uuid4

import psutil


def process_identity(pid):
    try:
        process = psutil.Process(pid)
        return dict(pid=pid, create_time=process.create_time(), name=process.name(), path=process.exe())
    except (psutil.Error, OSError):
        return None


class PrivateDesktop:
    """Temporary non-input desktop. Never calls SwitchDesktop."""
    def __init__(self):
        self.name='CstTools_'+uuid4().hex
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.user.CreateDesktopW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR,ctypes.c_void_p,
                                          wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
        self.user.CreateDesktopW.restype=wintypes.HANDLE
        self.user.CloseDesktop.argtypes=[wintypes.HANDLE]
        self.user.CloseDesktop.restype=wintypes.BOOL
        self.handle=self.user.CreateDesktopW(self.name,None,None,0,0x01|0x02|0x04|0x08|0x40|0x80,None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            if not self.user.CloseDesktop(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle=None

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class WindowsWindowBackend:
    def __init__(self,desktop=None):
        if os.name != 'nt':
            raise OSError('CST window observation requires Windows')
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        self.user.GetWindow.restype = wintypes.HWND
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.IsWindowVisible.argtypes = [wintypes.HWND]
        self.user.IsIconic.argtypes = [wintypes.HWND]
        self.user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.ShowWindowAsync.restype = wintypes.BOOL
        self.enum_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user.EnumWindows.argtypes = [self.enum_type, wintypes.LPARAM]
        self.user.EnumDesktopWindows.argtypes=[wintypes.HANDLE,self.enum_type,wintypes.LPARAM]
        self.user.EnumDesktopWindows.restype=wintypes.BOOL
        self.desktop=desktop
        self.enumeration_gaps=0
        self.event_type = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
                                           wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
        self.user.SetWinEventHook.argtypes = [wintypes.DWORD,wintypes.DWORD,wintypes.HMODULE,
                                             self.event_type,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD]
        self.user.SetWinEventHook.restype = wintypes.HANDLE
        self.user.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        self.hooks = []

    def window(self, hwnd):
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = ctypes.create_unicode_buffer(256)
        self.user.GetClassNameW(hwnd,name,256)
        return dict(hwnd=int(hwnd or 0),pid=pid.value,visible=bool(self.user.IsWindowVisible(hwnd)),
                    minimized=bool(self.user.IsIconic(hwnd)),owner=int(self.user.GetWindow(hwnd,4) or 0),
                    window_class=name.value)

    def foreground(self):
        return self.window(self.user.GetForegroundWindow())

    def windows(self):
        result = []
        def append(hwnd, _):
            result.append(self.window(hwnd))
            return True
        callback = self.enum_type(append)
        if self.desktop is not None:
            ctypes.set_last_error(0)
            if not self.user.EnumDesktopWindows(self.desktop,callback,0):
                error=ctypes.get_last_error()
                if error:
                    raise ctypes.WinError(error)
                # Empty/new/closing desktop: unavailable enumeration, not proof
                # that no window exists. Keep foreground WinEvents running.
                self.enumeration_gaps += 1
        else:
            self.user.EnumWindows(callback,0)
        return result

    def minimize(self, hwnd):
        return bool(self.user.ShowWindowAsync(hwnd,7))  # SW_SHOWMINNOACTIVE

    def install(self, callback):
        def event(hook, event, hwnd, object_id, child_id, thread, timestamp):
            if hwnd and (event == 3 or (object_id == 0 and child_id == 0)):
                window=self.window(hwnd)
                window['event_tick_ms']=timestamp
                callback('foreground' if event == 3 else 'show',window)
        self.callback = self.event_type(event)
        for event in (3, 0x8002):
            hook = self.user.SetWinEventHook(event,event,None,self.callback,0,0,2)
            if not hook:
                self.close()
                raise ctypes.WinError(ctypes.get_last_error())
            self.hooks.append(hook)

    def pump(self):
        message = wintypes.MSG()
        while self.user.PeekMessageW(ctypes.byref(message),None,0,0,1):
            self.user.TranslateMessage(ctypes.byref(message))
            self.user.DispatchMessageW(ctypes.byref(message))

    def close(self):
        for hook in self.hooks:
            self.user.UnhookWinEvent(hook)
        self.hooks = []


class BackgroundWindowObserver:
    def __init__(self, install, *, minimize=True, backend=None, lookup=process_identity):
        self.install = Path(install).resolve()
        self.backend = backend or WindowsWindowBackend()
        self.lookup = lookup
        self.minimize = minimize
        self.owned = {}
        self.events = []
        self.actions = []
        self.states = {}
        self.errors = []
        self.dropped = 0
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.baseline_foreground = self.backend.foreground()

    def _cst(self, identity):
        return identity and identity['name'].lower().startswith(('cst design environment','modeler_','solver_'))

    def bind(self, records):
        with self.lock:
            for record in records:
                identity = self.lookup(record['pid'])
                if (self._cst(identity) and identity['create_time'] == record['create_time']
                        and Path(identity['path']).resolve().is_relative_to(self.install)):
                    self.owned[(identity['pid'],identity['create_time'])] = identity

    def _owned(self, pid):
        identity = self.lookup(pid)
        if identity and (pid,identity['create_time']) in self.owned:
            if Path(identity['path']).resolve().is_relative_to(self.install):
                return identity
        return None

    def record(self, event, window):
        identity = self.lookup(window['pid'])
        if not self._cst(identity):
            return
        with self.lock:
            if len(self.events) >= 2048:
                self.dropped += 1
                return
            self.events.append(dict(event=event,monotonic=time.monotonic(),identity=identity,window=window))

    def sample(self):
        with self.lock:
            if not any(self._owned(pid) for pid,_ in self.owned):
                return
        for window in self.backend.windows():
            with self.lock:
                identity = self._owned(window['pid'])
                if not identity:
                    continue
                key=(window['pid'],identity['create_time'],window['hwnd'])
                if self.states.get(key) != window:
                    self.record('state',window)
                    self.states[key]=window
                # Do not hide/answer an owned popup or modal dialog.
                if (self.minimize and window['visible'] and not window['minimized']
                        and window['owner']==0 and window['window_class']!='#32770'):
                    if self.backend.minimize(window['hwnd']):
                        self.actions.append(dict(hwnd=window['hwnd'],identity=identity,
                                                 action='show-minimized-no-activate'))

    def __enter__(self):
        def run():
            try:
                self.backend.install(self.record)
                self.ready.set()
                while not self.stop.is_set():
                    self.backend.pump()
                    self.sample()
                    self.stop.wait(.05)
                self.backend.pump()
            except Exception as error:
                self.errors.append(str(error))
                self.ready.set()
            finally:
                self.backend.close()
        self.thread=threading.Thread(target=run,name='cst-window-observer',daemon=True)
        self.thread.start()
        if not self.ready.wait(5) or self.errors:
            self.__exit__(None,None,None)
            raise RuntimeError('CST window observer not ready: '+str(self.errors))
        return self

    def __exit__(self,*args):
        self.stop.set()
        self.thread.join(5)
        if self.thread.is_alive():
            self.errors.append('window observer did not exit')

    def report(self):
        with self.lock:
            owned_events = [e for e in self.events if (e['identity']['pid'],e['identity']['create_time']) in self.owned]
            return dict(baseline_foreground=self.baseline_foreground,
                        observation='WinEvent foreground/show hooks plus 50ms window polling',
                        owned_foreground_events=sum(e['event']=='foreground' for e in owned_events),
                        owned_events=owned_events,actions=self.actions,errors=self.errors,dropped_events=self.dropped,
                        window_enumeration_gaps=getattr(self.backend,'enumeration_gaps',0))
