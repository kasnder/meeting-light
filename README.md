# Meeting Light

Windows and macOS downloads are available under GitHub Releases. See [MACOS.md](MACOS.md) for Mac setup and preview limitations. Builds run on GitHub; no local SDK is required.

A local Python app for Windows and macOS that reminds you about upcoming calendar events. No Google OAuth registration, backend, or telemetry. Run it from Python or use a self-contained release download.

Inspired by [MeetingBar](https://meetingbar.app/), the macOS-only menu-bar app for keeping track of upcoming meetings and joining them in one click. Meeting Light began with the desire for a similar experience on Windows, using private iCal feeds and persistent reminders.

## Start and use

Double-click **Start Meeting Light.vbs**. The blue calendar icon may be inside Windows' hidden tray icons. Double-click the icon for your seven-day agenda, or right-click for Settings, Refresh now, Test reminder, and Exit. Closing the agenda hides it to the tray; Exit stops reminders.

Defaults:

- Refresh every **30 minutes**, plus startup and wake/unlock.
- Persistent popup and a short system sound **one minute before** timed events.
- Exclude exact event titles **busy**, ignoring case and outer spaces.
- Include events with and without online links; all-day and cancelled events are omitted.
- Automatic browser opening is **off**. Enable it in Settings to open a meeting page one minute before the start. This does not join the call.

The popup has Join meeting, Snooze 1m, Snooze 5m, and Dismiss. Closing it dismisses every event currently shown. Automatic opening keeps the reminder visible; clicking Join acknowledges it. With several distinct links, Join offers a choice instead of automatically opening one.

Settings lets you change reminder/refresh timing, sound, online-only filtering, exclusions, calendar names and enablement, automatic opening, and sign-in startup. Calendar colours distinguish sources in the agenda.

Zoom, Google Meet, Microsoft Teams, and Proton Meet links are recognised. Links open through your default browser; the provider/browser may subsequently offer to open its native app. Browser opening is attempted only once automatically per occurrence; the Join button remains available for retry.

## Calendars and privacy

On first start, the app imports one HTTPS calendar URL per nonempty line from `cal.txt` in your user home folder. It does not change that file. Settings → Calendars → Import can replace the source list from another text file. No secret URLs are displayed in Settings.

Google Calendar provides these URLs under Settings → your calendar → Integrate calendar → Secret address in iCal format. Do not make the calendar public or share the URL.

Imported URLs, cached feeds, settings, and reminder state are encrypted for your Windows user using DPAPI under `%LOCALAPPDATA%\MeetingLight\data`. Files cannot simply be copied to another Windows account; re-import the original URLs there. Removed-source cache files may remain encrypted in this data directory. No private event details or URLs are written to logs.

Feed downloads go directly to the source over HTTPS without following redirects or using environment proxies. If refresh fails, the last successful cache remains active and the tray icon turns amber. The agenda shows each calendar's last successful sync. New or changed events may take until the next refresh to appear.

The computer must be awake, the user signed in, and the app running to show reminders. After wake/unlock it refreshes and shows unacknowledged events still in progress, without reopening overdue meeting links. Sound follows your Windows volume settings. Fullscreen/exclusive applications can obscure ordinary always-on-top windows.

## Python installation and startup

This copy uses the installed **Python 3.14** in an isolated environment at `source\.venv`. The source supports Python 3.12 or later with Tkinter. It does not use or modify the speaker-power app's environment.

To prepare another copy, run `Install.ps1` in PowerShell. It finds a locally installed Python under `%LOCALAPPDATA%\Python`, installs `source\requirements.txt` into its own environment, registers sign-in startup, and starts the app. Alternatively:

```powershell
.\Install.ps1 -Python 'C:\path\to\python.exe'
```

Use `-NoStartup` to skip registration. Exit a running Meeting Light before reinstalling. The hidden startup launcher is `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MeetingLight.vbs`; it invokes this app's `pythonw.exe` and `run.py`. Keep the application folder at its current location, or rerun installation after moving it.

Run `Uninstall.ps1` to stop this application and remove its startup registration. It preserves the source, isolated environment, encrypted data, and original `cal.txt`; you can delete the app folder afterward if no longer needed. It does not touch Windows Speaker Power.

## Source and tests

- `source/meetinglight/core.py`: parsing, filtering, identity, recurrence and scheduling.
- `source/meetinglight/app.py`: Tkinter interface and thread coordination.
- `source/meetinglight/platform_windows.py`: secure storage, startup, session events and sound.
- `source/meetinglight/feeds.py` and `storage.py`: independent feed refreshes and protected caching.

From `source`, run `.venv\Scripts\python.exe -m pytest` after installing pytest. Tests use synthetic calendars. A safe visual demonstration is `.venv\Scripts\python.exe run.py --demo`; its synthetic Join links point to example.com.

Windows is supported, and macOS is available as a preview with native Keychain encryption, menu-bar integration and login startup. Linux is not included in this release. Downloaded Windows ZIPs contain MeetingLight.exe and its companion _internal folder; keep them together. No Python installation is required for release downloads. Move the extracted folder to its permanent location before enabling sign-in startup.
