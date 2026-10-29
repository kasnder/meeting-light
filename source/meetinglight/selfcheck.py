"""Synthetic desktop check for release builds. Never reads user calendars."""
import json
from pathlib import Path
import tempfile


def run():
    from .app import App
    from .storage import Store
    result = {}
    with tempfile.TemporaryDirectory(prefix='meetinglight-check-') as directory:
        store = Store(directory)
        sample = b'synthetic test content'
        store.write('check', sample)
        result['encrypted_storage'] = store.read('check') == sample and sample not in (Path(directory) / 'check.bin').read_bytes()
        app = App(store, demo=True, background=True)
        app.settings['sound'] = False
        app.settings['auto_open'] = False
        def inspect():
            result['tray'] = bool(app.tray.visible)
            result['timed_popup'] = bool(app.popup and app.popup.winfo_exists())
            if app.visible:
                app.dismiss(app.visible[0])
            result['dismiss'] = app.popup is None
            app.quit()
        app.root.after(8500, inspect)
        app.run()
    print(json.dumps(result), flush=True)
    if not all(result.values()) or len(result) != 4:
        raise RuntimeError('Desktop self-check failed')
