# Meeting Light

Local meeting reminders for **Windows and macOS**: a tray/menu-bar agenda, persistent alerts, and one-click meeting links. No Google OAuth registration, backend, or telemetry.

Inspired by [MeetingBar](https://meetingbar.app/), the macOS-only menu-bar app for keeping track of upcoming meetings and joining them in one click. Meeting Light began with the desire for a similar experience on Windows, using private iCal feeds and persistent reminders.

## Download and start

Get the packages from [GitHub Releases](https://github.com/kasnder/meeting-light/releases). **No Python, Xcode, or SDK installation is needed.** Builds run on GitHub.

| Computer | Download | Start |
| --- | --- | --- |
| Windows, 64-bit Intel/AMD | `MeetingLight-Windows-x86_64.zip` | Extract the entire ZIP and open `MeetingLight.exe` inside the extracted folder. Keep `_internal` beside it. |
| Mac with Apple Silicon (M1 or newer) | `MeetingLight-macOS-arm64.zip` | Extract, move `MeetingLight.app` to Applications, and open it. |
| Intel Mac | `MeetingLight-macOS-x86_64.zip` | Extract, move `MeetingLight.app` to Applications, and open it. |

The Mac builds target macOS 15 or newer and remain a preview; see [MACOS.md](MACOS.md). Windows binaries are not Authenticode signed; Mac apps are ad-hoc signed but not Apple Developer ID signed or notarized. Operating-system download/security prompts may appear. SHA-256 files accompany each download.

**Put the app in its permanent location before enabling startup.** Source-code ZIPs are for developers; use the named platform downloads above to run the app directly.

## Connect calendars

1. In Google Calendar, open Settings → your calendar → Integrate calendar → **Secret address in iCal format**.
2. Put one private HTTPS calendar URL per line in a local text file.
3. In Meeting Light, open Settings → Calendars → **Import calendars from text file**.

Repeat for additional calendars in the same file. Import replaces the app's calendar list. The app does not search your home folder or automatically import any file.

The source text file remains unchanged and contains plaintext secrets. Do not upload or share it. You do not need to make your calendar public.

## Everyday use

On Windows, open the blue calendar icon in the system tray, possibly under hidden icons. On Mac, use the calendar icon in the menu bar. Open Upcoming events for the seven-day agenda, or choose Settings, Refresh now, Test reminder, or Exit. Closing the agenda hides it; Exit stops reminders.

Defaults:

- Refresh every **30 minutes**, plus startup and wake/unlock.
- Show a persistent popup and play a short sound **one minute before** timed events.
- Exclude titles exactly matching **busy**, ignoring case and surrounding spaces.
- Include events with and without online links; omit all-day and cancelled events.
- Automatic browser opening is **off**. Enable it to open a meeting page one minute before the start; it does not join the call.

The reminder offers Join meeting, Snooze 1m, Snooze 5m, and Dismiss. Closing it dismisses the events currently shown. Multiple distinct meeting links require a choice. Zoom, Google Meet, Microsoft Teams, and Proton Meet are supported.

Settings controls timing, sound, online-only filtering, excluded titles, calendar names/enablement, automatic opening, and startup.

### Start automatically at sign-in

Use **Settings → Reminders → Start Meeting Light when I sign in** to enable or disable startup.

- **Windows:** a per-user native registry startup entry launches the app directly. No VBScript launcher is used. Upgrading from an older version removes its obsolete Meeting Light startup script while preserving your preference.
- **macOS:** a user LaunchAgent launches the app at login.

If you move the app, disable and re-enable the setting from the new location. Before removing it, disable startup and choose Exit. Delete the extracted folder or Mac app to remove the release build; encrypted local data is preserved.

## Privacy and reliability

The app encrypts imported URLs, cached feeds, settings, and reminder state:

- **Windows:** user-bound DPAPI encryption, stored under `%LOCALAPPDATA%\MeetingLight\data`.
- **macOS:** encryption with a Keychain-held key, stored under `~/Library/Application Support/MeetingLight/data`.

No plaintext app copies of calendar URLs or event data are written to disk. Original import files are your responsibility. Encrypted data cannot simply be transferred to another user account; re-import your URLs there. Removed-calendar cache files may remain encrypted locally. No private event details or URLs are written to logs.

Downloads go directly to calendar sources over HTTPS without redirects or environment proxies. Failed refreshes retain the last successful cache and show a stale-data warning. New changes arrive on a subsequent refresh.

Your computer must be awake, you must be signed in, and the app must be running. After wake/unlock it refreshes and shows unacknowledged events still in progress without opening overdue links. Sound follows your system volume. Exclusive fullscreen applications may obscure normal always-on-top windows. Real-device sleep/wake and multi-monitor testing on Mac remains outstanding.

## Run from Python (optional)

For developers or users with **Python 3.12+ and Tkinter** already installed. Release users can skip this section.

On Windows, run `Install.ps1` in PowerShell. It creates `source\.venv`, installs the dependencies, creates a normal **Meeting Light** shortcut in the project folder, enables sign-in startup, and starts the app. To select Python explicitly:

```powershell
.\Install.ps1 -Python 'C:\path\to\python.exe'
```

Use `-NoStartup` to skip startup registration. Exit the app before reinstalling. `Uninstall.ps1` stops this source installation, removes its shortcut and startup entry, and preserves the source, environment, encrypted data, and original import file.

On macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r source/requirements.txt
.venv/bin/python source/run.py
```

Use the packaged app if Python asks to build native dependencies from source; no local SDK is needed for the downloads. Source and packaged installations share the same app data and should not run together.

## Development and verification

Calendar parsing, filtering and scheduling live in `source/meetinglight/core.py`; desktop integration is separated into Windows and macOS adapters. Linux is not included in this release.

Install pytest into your environment and run `python -m pytest source/tests -q` using that environment's Python. Tests use synthetic calendars. `python source/run.py --demo` shows synthetic events whose Join links point to example.com. GitHub builds also run `--self-check` against each packaged app to verify encrypted storage, a timed popup, dismissal, and tray/menu-bar initialization.

## License

Copyright (C) 2026 Konrad Kollnig.

Meeting Light is licensed under the [GNU General Public License version 3](LICENSE) (SPDX: `GPL-3.0-only`). It is provided without warranty. Third-party dependencies retain their respective licenses.
