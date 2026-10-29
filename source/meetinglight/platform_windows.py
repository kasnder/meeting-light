"""Windows-only boundary: DPAPI, startup, session events, sound and instance lock."""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import sys


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(data: bytes, decrypt=False):
    if sys.platform != "win32":
        raise RuntimeError("Secure storage is currently implemented for Windows only")
    buf = ctypes.create_string_buffer(data)
    src = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    dest = DATA_BLOB()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dest)):
        raise OSError("Secure storage operation failed")
    try:
        return ctypes.string_at(dest.data, dest.size)
    finally:
        kernel = ctypes.WinDLL("kernel32")
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(dest.data)


def set_app_identity():
    """Keep taskbar grouping separate from generic Python windows."""
    shell = ctypes.WinDLL("shell32")
    shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
    shell.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
    if shell.SetCurrentProcessExplicitAppUserModelID("KonradKollnig.MeetingLight") < 0:
        raise OSError("Application identity could not be set")


def data_dir():
    return Path(os.environ["LOCALAPPDATA"]) / "MeetingLight" / "data"


class InstanceLock:
    def __init__(self, identity):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        name = "Local\\MeetingLight-" + hashlib.sha256(str(identity).encode()).hexdigest()[:24]
        self.handle = self.kernel.CreateMutexW(None, False, name)
        self.acquired = bool(self.handle) and ctypes.get_last_error() != 183

    def close(self):
        if self.handle:
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def startup_path():
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/MeetingLight.vbs"


def set_startup(enabled):
    path = startup_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    command = launch_command() + ' --background'
    escaped = command.replace('"', '""')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'CreateObject("WScript.Shell").Run "{escaped}", 0, False\n', encoding="utf-8")


def launch_command():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    entry = Path(__file__).resolve().parent.parent / "run.py"
    return f'"{pythonw}" "{entry}"'


def sound():
    import winsound
    winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)


def show_without_focus(window):
    user = ctypes.windll.user32
    user.GetParent.argtypes = [wintypes.HWND]
    user.GetParent.restype = wintypes.HWND
    user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    window.update_idletasks()
    hwnd = user.GetParent(window.winfo_id())
    old = user.GetWindowLongPtrW(hwnd, -20)
    user.SetWindowLongPtrW(hwnd, -20, old | 0x08000000)  # WS_EX_NOACTIVATE during mapping.
    window.deiconify()
    window.update_idletasks()
    user.SetWindowLongPtrW(hwnd, -20, old)


def center(window, preferred_height=300):
    """Centre on the cursor's monitor, with no foreground activation."""
    user = ctypes.windll.user32
    pt = wintypes.POINT()
    user.GetCursorPos(ctypes.byref(pt))
    user.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user.MonitorFromPoint.restype = wintypes.HANDLE
    monitor = user.MonitorFromPoint(pt, 2)
    class MonitorInfo(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                    ("work", wintypes.RECT), ("flags", wintypes.DWORD)]
    info = MonitorInfo()
    info.size = ctypes.sizeof(info)
    user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    user.GetMonitorInfoW(monitor, ctypes.byref(info))
    window.update_idletasks()
    width, height = 600, min(preferred_height, info.work.bottom - info.work.top - 80)
    x = info.work.left + (info.work.right - info.work.left - width) // 2
    y = info.work.top + (info.work.bottom - info.work.top - height) // 2
    window.geometry(f"{width}x{height}+{x}+{y}")


class SessionObserver:
    """Subclass the Tk top-level HWND; dispatch wake/unlock to the application's queue."""
    def __init__(self, root, callback):
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.wts = ctypes.WinDLL("wtsapi32")
        self.user.GetParent.argtypes = [wintypes.HWND]
        self.user.GetParent.restype = wintypes.HWND
        root.update_idletasks()
        self.hwnd = self.user.GetParent(root.winfo_id())
        self.proc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                           ctypes.c_size_t, ctypes.c_ssize_t)
        self.user.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                            ctypes.c_size_t, ctypes.c_ssize_t]
        self.user.CallWindowProcW.restype = ctypes.c_ssize_t
        self.user.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        self.user.SetWindowLongPtrW.restype = ctypes.c_void_p
        def handler(hwnd, msg, wp, lp):
            if (msg == 0x218 and wp in (7, 18)) or (msg == 0x2B1 and wp == 8):
                callback("resume")
            elif msg == 0x2B1 and wp == 7:
                callback("lock")
            elif msg == 0x1E:
                callback("time")
            return self.user.CallWindowProcW(self.previous, hwnd, msg, wp, lp)
        self.handler = self.proc_type(handler)
        self.previous = self.user.SetWindowLongPtrW(self.hwnd, -4, ctypes.cast(self.handler, ctypes.c_void_p))
        if not self.previous:
            raise OSError("Session observer unavailable")
        self.wts.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
        if not self.wts.WTSRegisterSessionNotification(self.hwnd, 0):
            self.user.SetWindowLongPtrW(self.hwnd, -4, self.previous)
            raise OSError("Session notifications unavailable")

    def close(self):
        self.wts.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]
        self.wts.WTSUnRegisterSessionNotification(self.hwnd)
        self.user.SetWindowLongPtrW(self.hwnd, -4, self.previous)
