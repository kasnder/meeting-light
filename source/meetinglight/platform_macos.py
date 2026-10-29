"""macOS integration. Secrets never fall back to plaintext storage."""
import fcntl
import os
from pathlib import Path
import plistlib
import sys
import threading

from cryptography.fernet import Fernet, InvalidToken
from keyring.backends.macOS import Keyring

KEYCHAIN_SERVICE = "net.kollnig.MeetingLight"
_key_lock = threading.Lock()
_cipher = None


def protect(data, decrypt=False):
    global _cipher
    with _key_lock:
        if _cipher is None:
            # Select Apple's Keychain explicitly; never accept a plaintext backend.
            backend = Keyring()
            key = backend.get_password(KEYCHAIN_SERVICE, 'calendar-storage-v1')
            if key is None:
                if decrypt:
                    raise OSError('Calendar encryption key is unavailable')
                key = Fernet.generate_key().decode('ascii')
                backend.set_password(KEYCHAIN_SERVICE, 'calendar-storage-v1', key)
            _cipher = Fernet(key.encode('ascii'))
    try:
        return _cipher.decrypt(data) if decrypt else _cipher.encrypt(data)
    except InvalidToken:
        raise OSError('Encrypted calendar could not be opened') from None


def data_dir():
    return Path.home() / 'Library/Application Support/MeetingLight/data'


class InstanceLock:
    def __init__(self, identity):
        directory = Path(identity)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = open(directory / '.instance.lock', 'a+b')
        os.chmod(directory / '.instance.lock', 0o600)
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.acquired = True
        except BlockingIOError:
            self.acquired = False

    def close(self):
        if self.file:
            self.file.close()
            self.file = None


def startup_path():
    return Path.home() / 'Library/LaunchAgents/net.kollnig.MeetingLight.plist'


def launch_arguments():
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--background']
    return [sys.executable, str(Path(__file__).resolve().parent.parent / 'run.py'), '--background']


def set_startup(enabled):
    path = startup_path()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {'Label': 'net.kollnig.MeetingLight', 'ProgramArguments': launch_arguments(),
               'RunAtLoad': True, 'ProcessType': 'Interactive'}
    path.write_bytes(plistlib.dumps(content))
    path.chmod(0o600)


def set_app_identity():
    pass  # App bundle carries its identifier; Tk owns the shared NSApplication.


def start_tray(icon, on_error):
    # Cocoa UI and Tk must share the main thread/event loop.
    try:
        icon.run_detached(setup=lambda tray: None)
        icon.visible = True
    except Exception:
        on_error()


def stop_tray(icon):
    icon.visible = False  # Do not stop NSApplication's event loop, owned by Tk.


def sound():
    import AppKit
    AppKit.NSBeep()


def show_without_focus(window):
    window.deiconify()


def center(window, preferred_height=300):
    window.update_idletasks()
    width = min(600, window.winfo_screenwidth() - 40)
    height = min(preferred_height, window.winfo_screenheight() - 100)
    window.geometry(f'{width}x{height}+{(window.winfo_screenwidth()-width)//2}+{(window.winfo_screenheight()-height)//2}')


class SessionObserver:
    def __init__(self, root, callback):
        import AppKit
        import Foundation
        class MeetingLightSessionObserver(Foundation.NSObject):
            def awake_(self, notification):
                callback('resume')
            def locked_(self, notification):
                callback('lock')
        self.observer = MeetingLightSessionObserver.alloc().init()
        self.workspace = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
        self.distributed = Foundation.NSDistributedNotificationCenter.defaultCenter()
        self.workspace.addObserver_selector_name_object_(self.observer, 'awake:', AppKit.NSWorkspaceDidWakeNotification, None)
        self.distributed.addObserver_selector_name_object_(self.observer, 'awake:', 'com.apple.screenIsUnlocked', None)
        self.distributed.addObserver_selector_name_object_(self.observer, 'locked:', 'com.apple.screenIsLocked', None)

    def close(self):
        self.workspace.removeObserver_(self.observer)
        self.distributed.removeObserver_(self.observer)
