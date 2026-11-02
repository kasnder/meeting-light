"""Synthetic desktop check for release builds. Never reads user calendars."""
import json
from pathlib import Path
import tempfile
import os
import sys
import uuid


def run():
    from .app import App
    from .storage import Store
    result = {}
    def stage(name):
        report = os.environ.get("MEETINGLIGHT_CHECK_REPORT")
        if report:
            Path(report).write_text(json.dumps(dict(result, stage=name)))
    if sys.platform == "darwin":
        from . import platform_macos
        # The bundled executable must create its own synthetic Keychain item.
        # Reusing the source interpreter's item triggers an access approval dialog.
        platform_macos.KEYCHAIN_SERVICE += ".selfcheck." + uuid.uuid4().hex
        platform_macos._cipher = None
    stage("starting")
    with tempfile.TemporaryDirectory(prefix='meetinglight-check-') as directory:
        store = Store(directory)
        sample = b'synthetic test content'
        stage('encrypting')
        store.write('check', sample)
        result['encrypted_storage'] = store.read('check') == sample and sample not in (Path(directory) / 'check.bin').read_bytes()
        stage('calendar-worker')
        from .core import now_utc
        from .feeds import parse_isolated
        start = now_utc().strftime('%Y%m%dT%H%M%SZ')
        calendar = ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Synthetic//EN\r\nBEGIN:VEVENT\r\n'
                    f'UID:check\r\nDTSTART:{start}\r\nDURATION:PT1H\r\nSUMMARY:Synthetic\r\n'
                    'URL:https://meet.google.com/abc-defg-hij\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n').encode()
        # No fallback: the packaged executable itself must act as the parsing worker.
        parsed = parse_isolated(calendar, 'check', now_utc(), fallback=False)
        result['calendar_worker'] = [(e.title, len(e.links)) for e in parsed] == [('Synthetic', 1)]
        stage("creating-ui")
        app = App(store, demo=True, background=True)
        stage("ui-created")
        app.settings['sound'] = False
        app.settings['auto_open'] = False
        def inspect():
            result['tray'] = bool(app.tray.visible)
            result['timed_popup'] = bool(app.popup and app.popup.winfo_exists())
            if app.visible:
                app.dismiss(app.visible[0])
            result['dismiss'] = app.popup is None
            stage("checked")
            app.quit()
        app.root.after(8500, inspect)
        app.run()
    if sys.platform == "darwin":
        platform_macos.Keyring().delete_password(platform_macos.KEYCHAIN_SERVICE, "calendar-storage-v1")
    stage("finished")
    print(json.dumps(result), flush=True)
    if not all(result.values()) or len(result) != 5:
        raise RuntimeError('Desktop self-check failed')
