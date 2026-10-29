# Meeting Light for macOS (preview)

Download the macOS ZIP matching your processor: **arm64** for Apple Silicon (M1 and newer), **x86_64** for Intel. These builds target macOS 15 or newer. Extract the archive, move **MeetingLight.app** to Applications, and open it. No Python, Xcode, or SDK installation is required for the app bundle.

This preview is ad-hoc signed, not Apple Developer ID signed or notarized. macOS may block first launch. Review the source and release checksum before using Apple's per-app opening approval; do not disable Gatekeeper globally.

Use Settings → Calendars → Import to select a local text file containing one private HTTPS iCal URL per line. You may instead put the file at `~/cal.txt` before first launch. The file remains unchanged and contains plaintext secrets; the app stores its own encrypted copies. Never upload that file to GitHub.

URLs and cached calendar data are encrypted under `~/Library/Application Support/MeetingLight/data`. The encryption key lives in **macOS Keychain**. If Keychain access is denied, the app does not fall back to plaintext storage. A new build may prompt for Keychain access again.

The menu-bar calendar opens the agenda, settings, test reminder, and quit actions. Reminders appear one minute before events; refresh is every 30 minutes. Titles exactly matching “busy” are excluded. These settings and online-only filtering are adjustable.

Enable or disable **Start Meeting Light when I sign in** in Settings → Reminders. Enable this only after moving the app to its final location; the setting writes a user LaunchAgent pointing to that location. To remove startup, uncheck the setting before deleting the app. Disabling removes the next-login entry without stopping the currently running app.

This preview's synthetic checks run on GitHub-hosted macOS machines, including encryption, recurrence/filter tests, a timed popup, dismissal, and menu-bar initialization. Physical sleep/wake, lock-screen behaviour, multiple monitors, and first launch of the downloaded/quarantined app still need testing on a real Mac.

## Run from Python instead

With an existing Python 3.12+ installation including Tkinter:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements.txt
.venv/bin/python source/run.py
```

No SDK is needed when binary wheels are available for your Python/processor. Use the downloadable app bundle if pip proposes building native dependencies from source. Source and packaged installations share the same encrypted data and should not run together.
