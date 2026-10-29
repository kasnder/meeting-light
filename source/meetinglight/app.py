from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import queue
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

import pystray
from PIL import Image, ImageDraw, ImageTk

from .core import DEFAULTS, Event, Scheduler, eligible, merge_events, now_utc, UTC
from .feeds import import_sources, load_all
from .storage import Store
from . import platform_api as platform

PALETTE = ("#2563eb", "#a855f7", "#059669", "#d97706", "#db2777")


def icon_image(stale=False):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 8, 60, 60), 12, fill="#d97706" if stale else "#2563eb")
    d.rectangle((5, 20, 59, 24), fill="white")
    d.line((20, 4, 20, 16), fill="white", width=5)
    d.line((44, 4, 44, 16), fill="white", width=5)
    d.line((32, 31, 32, 43, 43, 43), fill="white", width=4)
    return img


def countdown(e):
    seconds = int((e.start - now_utc()).total_seconds())
    if seconds < 0:
        return "In progress"
    if seconds < 60:
        return f"Starts in {seconds}s"
    if seconds < 3600:
        return f"Starts in {seconds // 60}m"
    return e.start.astimezone().strftime("%a %d %b, %H:%M")


def auto_scrollbar(scrollbar):
    def update(first, last):
        scrollbar.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            scrollbar.pack_forget()
        elif not scrollbar.winfo_manager():
            scrollbar.pack(side="right", fill="y")
    return update


class App:
    def __init__(self, store, demo=False, background=False):
        self.store, self.demo = store, demo
        self.config = store.load("config", {"settings": dict(DEFAULTS), "sources": []})
        self.settings = dict(DEFAULTS, **self.config["settings"])
        if not demo:
            platform.migrate_startup(self.settings["startup"])
            self.settings["startup"] = platform.startup_enabled()
        self.sources = self.config["sources"]
        self.states = {} if demo else store.load("states", {})
        self.scheduler = Scheduler(self.states)
        self.statuses = store.load("status", {})
        self.events_by_source = {}
        self.events, self.visible = [], []
        self.commands = queue.Queue()
        self.fetching = False
        self.closing = False
        self.locked = False
        self.recovering = True
        self.next_refresh = 0
        self.last_tick = time.time()
        self.last_persist = ""
        self.popup = None
        self.popup_signature = None
        self.popup_labels = {}
        self.settings_window = None
        self.last_agenda = None
        platform.set_app_identity()
        self.root = tk.Tk()
        self.root.withdraw()
        # Set Tk's default for this window and all subsequent Toplevels.
        # Keep PhotoImage references alive for the lifetime of the application.
        self.window_icons = [ImageTk.PhotoImage(icon_image().resize((size, size), Image.Resampling.LANCZOS), master=self.root)
                             for size in (16, 32, 48, 64)]
        self.root.iconphoto(True, *self.window_icons)
        self.root.title("Meeting Light" + (" — Demo" if demo else ""))
        self.root.geometry("850x540")
        self.root.minsize(650, 400)
        self.root.protocol("WM_DELETE_WINDOW", self.root.withdraw)
        self.root.report_callback_exception = lambda *args: self.ui_error()
        self.apply_style()
        self.build_agenda()
        self.observer = platform.SessionObserver(self.root, self.commands.put)
        self.tray = pystray.Icon("MeetingLight", icon_image(), "Meeting Light",
            menu=pystray.Menu(
                pystray.MenuItem("Upcoming events", lambda *a: self.commands.put("agenda"), default=True),
                pystray.MenuItem("Refresh now", lambda *a: self.commands.put("refresh")),
                pystray.MenuItem("Settings", lambda *a: self.commands.put("settings")),
                pystray.MenuItem("Test reminder", lambda *a: self.commands.put("test")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", lambda *a: self.commands.put("exit"))))
        platform.start_tray(self.tray, lambda: self.commands.put("tray_error"))
        if demo:
            self.sources = [dict(id="demo", name="Sample calendar", enabled=True)]
            now = now_utc()
            event = Event("demo-timed", "Weekly catch-up · sample event", now + timedelta(seconds=65),
                          now + timedelta(minutes=30), ("demo",), (("Test link", "https://example.com/"),))
            self.events_by_source["demo"] = [event,
                Event("demo-later", "Project review · sample event", now + timedelta(hours=2),
                      now + timedelta(hours=3), ("demo",), (("Google Meet", "https://example.com/"),)),
                Event("demo-busy", "busy", now + timedelta(minutes=3), now + timedelta(hours=1), ("demo",))]
            self.events = merge_events(self.events_by_source["demo"])
            self.statuses = {"demo": {"last": now.isoformat(), "error": None}}
            self.next_refresh = float("inf")
        elif not self.sources:
            self.status_text.set("Import your calendars in Settings → Calendars to begin.")
            self.next_refresh = time.monotonic() + self.settings["refresh_minutes"] * 60
        else:
            self.refresh(cached_first=True)
        if not background or not self.sources:
            self.root.deiconify()
        self.root.after(250, self.tick)

    def apply_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#f5f7fb", foreground="#152238")
        style.configure("TButton", padding=(12, 7))
        style.configure("Heading.TLabel", font=("Segoe UI", 21, "bold"))
        style.configure("Sub.TLabel", foreground="#52627a")
        style.configure("Accent.TButton", background="#2563eb", foreground="white")
        style.map("Accent.TButton", background=[("active", "#1d4ed8")])
        style.configure("Treeview", rowheight=37, background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=7)
        style.configure("TNotebook.Tab", padding=(18, 9))
        self.root.configure(background="#f5f7fb")

    def build_agenda(self):
        frame = ttk.Frame(self.root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Your next meetings", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(frame, text="The next seven days · reminders stay until you act", style="Sub.TLabel").pack(anchor="w", pady=(4, 18))
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(0, 14))
        self.refresh_button = ttk.Button(bar, text="Refresh now", command=self.refresh)
        self.refresh_button.pack(side="left")
        ttk.Button(bar, text="Settings", command=self.show_settings).pack(side="left", padx=8)
        ttk.Button(bar, text="Test reminder", command=self.test_reminder).pack(side="left")
        ttk.Button(bar, text="Hide to tray", command=self.root.withdraw).pack(side="right")
        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=("when", "title", "calendar", "meeting"), show="headings", selectmode="browse")
        for key, label, width in [("when", "When", 155), ("title", "Event", 300),
                                   ("calendar", "Calendar", 135), ("meeting", "Meeting", 120)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=70)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=auto_scrollbar(scroll))
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.join_selected())
        footer = ttk.Frame(frame)
        footer.pack(fill="x", pady=(16, 0))
        ttk.Button(footer, text="Join selected meeting", style="Accent.TButton", command=self.join_selected).pack(side="right")
        self.status_text = tk.StringVar(value="Loading calendars…")
        ttk.Label(footer, textvariable=self.status_text, wraplength=510, style="Sub.TLabel").pack(side="left", anchor="w")

    def ui_error(self):
        self.status_text.set("An action failed. Private details were not logged; retry from the tray.")

    def enabled(self):
        return {s["id"] for s in self.sources if s.get("enabled", True)} | {"test"}

    def source_name(self, source_id):
        return next((s["name"] for s in self.sources if s["id"] == source_id), "Test calendar")

    def save_config(self):
        self.store.save("config", {"settings": self.settings, "sources": self.sources})

    def persist_states(self):
        serialized = json.dumps(self.scheduler.states, sort_keys=True)
        if serialized != self.last_persist:
            self.store.save("states", self.scheduler.states)
            self.last_persist = serialized

    def refresh(self, cached_first=False):
        if self.fetching or self.demo:
            return
        self.fetching = True
        self.refresh_button.configure(state="disabled")
        self.status_text.set("Refreshing calendars securely…")
        snapshot = [dict(s) for s in self.sources]
        def worker():
            try:
                if cached_first:
                    self.commands.put(("results", load_all(snapshot, self.store, fetch=False), False))
                self.commands.put(("results", load_all(snapshot, self.store), True))
            except Exception:
                self.commands.put(("results", [(s["id"], [], None, "Calendar unavailable") for s in snapshot], True))
        threading.Thread(target=worker, daemon=True).start()

    def handle_results(self, rows, final):
        valid_ids = {s["id"] for s in self.sources}
        for source_id, events, last, error in rows:
            if source_id not in valid_ids:
                continue
            # A transient fetch/cache failure must not erase a usable in-memory calendar.
            if events or not error or source_id not in self.events_by_source:
                self.events_by_source[source_id] = events
            status = self.statuses.setdefault(source_id, {})
            if last:
                status["last"] = last
            status["error"] = error
        self.events = merge_events([e for sid, events in self.events_by_source.items()
                                    if sid in valid_ids or sid == "test" for e in events])
        self.store.save("status", self.statuses)
        self.last_agenda = None
        if final:
            self.fetching = False
            self.refresh_button.configure(state="normal")
            self.next_refresh = time.monotonic() + self.settings["refresh_minutes"] * 60

    def tick(self):
        if self.closing:
            return
        try:
            current = time.time()
            if abs(current - self.last_tick - 1) > 10:
                self.recovering = True
                self.next_refresh = 0
            self.last_tick = current
            while True:
                try:
                    command = self.commands.get_nowait()
                except queue.Empty:
                    break
                if isinstance(command, tuple):
                    _, rows, final = command
                    self.handle_results(rows, final)
                elif command == "exit":
                    self.quit()
                    return
                elif command == "agenda":
                    self.root.deiconify()
                    self.root.lift()
                elif command == "settings":
                    self.show_settings()
                elif command == "test":
                    self.test_reminder()
                elif command in ("refresh", "resume", "time"):
                    if command != "refresh":
                        self.recovering = True
                        self.locked = False
                    self.refresh()
                elif command == "lock":
                    self.locked = True
                    if self.popup:
                        self.popup.withdraw()
                elif command == "tray_error":
                    self.root.deiconify()
                    messagebox.showwarning("Meeting Light", "The tray icon could not start. Keep this window open and restart the app from your normal desktop.", parent=self.root)
            if time.monotonic() >= self.next_refresh:
                self.refresh()
            if not self.locked:
                visible, auto = self.scheduler.evaluate(self.events, self.settings, self.enabled(), self.recovering)
                self.recovering = False
                # Save the at-most-once marker before launching an external browser.
                self.persist_states()
                for e in auto:
                    self.open_link(e, e.links[0][1], automatic=True)
                self.update_popup(visible)
            self.update_agenda()
        except Exception:
            self.ui_error()
        finally:
            if not self.closing:
                self.root.after(1000, self.tick)

    def update_agenda(self):
        now = now_utc()
        selected = self.tree.selection()
        events = [e for e in self.events if e.end > now and eligible(e, self.settings, self.enabled())]
        signature = tuple((e.key, e.title, e.start, e.end, e.links, e.calendars) for e in events)
        if signature != self.last_agenda:
            self.tree.delete(*self.tree.get_children())
            for i, source in enumerate(self.sources):
                self.tree.tag_configure(source["id"], foreground=PALETTE[i % len(PALETTE)])
            for e in events:
                self.tree.insert("", "end", iid=e.key, tags=e.calendars[:1], values=(
                    e.start.astimezone().strftime("%a %d %b  %H:%M"), e.title,
                    ", ".join(self.source_name(s) for s in e.calendars),
                    ", ".join(dict.fromkeys(p for p, u in e.links)) or "—"))
            if selected and self.tree.exists(selected[0]):
                self.tree.selection_set(selected)
            self.last_agenda = signature
        if self.fetching:
            return
        messages, stale = [], False
        for s in self.sources:
            status = self.statuses.get(s["id"], {})
            last = status.get("last")
            old = not last or (now - datetime.fromisoformat(last)).total_seconds() > self.settings["refresh_minutes"] * 120
            failed = status.get("error") or old
            stale |= bool(failed)
            when = datetime.fromisoformat(last).astimezone().strftime("%H:%M") if last else "never"
            messages.append(f'{s["name"]}: {"STALE · " if failed else ""}synced {when}')
        if not events:
            messages.insert(0, "No matching upcoming events.")
        self.status_text.set("\n".join(messages) if messages else "Import calendar URLs in Settings to begin.")
        if getattr(self, "tray_stale", None) != stale:
            self.tray.icon = icon_image(stale)
            self.tray.title = "Meeting Light — calendars need attention" if stale else "Meeting Light"
            self.tray_stale = stale

    def scroll_frame(self, parent):
        holder = ttk.Frame(parent)
        holder.pack(fill="both", expand=True)
        canvas = tk.Canvas(holder, bg="#f5f7fb", highlightthickness=0)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=18)
        ident = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(ident, width=e.width))
        canvas.configure(yscrollcommand=auto_scrollbar(scrollbar))
        canvas.pack(side="left", fill="both", expand=True)
        def wheel(event):
            first, last = canvas.yview()
            if first > 0 or last < 1:
                canvas.yview_scroll(-int(event.delta / 120), "units")
        parent.bind("<MouseWheel>", wheel)
        return inner

    def update_popup(self, visible):
        signature = tuple((e.key, e.title, e.start, e.links) for e in visible)
        old_keys = {e.key for e in self.visible}
        self.visible = visible
        if not visible:
            if self.popup:
                self.popup.destroy()
                self.popup = None
            self.popup_signature = None
            return
        if self.popup_signature != signature or not self.popup:
            if self.popup:
                self.popup.destroy()
            self.popup = tk.Toplevel(self.root)
            self.popup.withdraw()
            self.popup.configure(background="#f5f7fb")
            self.popup.title("Meeting Light — Reminder")
            self.popup.attributes("-topmost", True)
            self.popup.protocol("WM_DELETE_WINDOW", self.dismiss_visible)
            ttk.Label(self.popup, text="It's nearly time", style="Heading.TLabel", padding=(22, 18, 22, 0)).pack(anchor="w")
            ttk.Label(self.popup, text="Join, snooze, or dismiss when you're ready.", style="Sub.TLabel", padding=(22, 4, 22, 10)).pack(anchor="w")
            inner = self.scroll_frame(self.popup)
            self.popup_labels = {}
            for e in visible:
                card = ttk.Frame(inner, padding=(0, 10, 0, 18))
                card.pack(fill="x")
                ttk.Label(card, text=e.title, font=("Segoe UI", 15, "bold"), wraplength=510).pack(anchor="w")
                label = ttk.Label(card, text=countdown(e), foreground="#2563eb")
                label.pack(anchor="w", pady=(5, 2))
                self.popup_labels[e.key] = label
                ttk.Label(card, text=", ".join(self.source_name(s) for s in e.calendars), style="Sub.TLabel").pack(anchor="w")
                buttons = ttk.Frame(card)
                buttons.pack(fill="x", pady=(12, 0))
                if e.links:
                    ttk.Button(buttons, text="Join meeting", style="Accent.TButton", command=lambda event=e: self.join(event)).pack(side="left", padx=(0, 8))
                for minutes in (1, 5):
                    ttk.Button(buttons, text=f"Snooze {minutes}m", command=lambda event=e, m=minutes: self.snooze(event, m)).pack(side="left", padx=(0, 5))
                ttk.Button(buttons, text="Dismiss", command=lambda event=e: self.dismiss(event)).pack(side="right")
                ttk.Separator(inner).pack(fill="x")
            platform.center(self.popup, preferred_height=min(540, 125 + 180 * len(visible)))
            platform.show_without_focus(self.popup)
            self.popup_signature = signature
            if self.settings["sound"] and any(e.key not in old_keys for e in visible):
                platform.sound()
        elif self.popup.state() == "withdrawn":
            platform.show_without_focus(self.popup)
        for e in visible:
            self.popup_labels[e.key].configure(text=countdown(e))

    def dismiss_visible(self):
        for e in list(self.visible):
            self.scheduler.dismiss(e)
        self.persist_states()
        self.update_popup([])

    def dismiss(self, event):
        self.scheduler.dismiss(event)
        self.persist_states()
        self.update_popup([e for e in self.visible if e.key != event.key])

    def snooze(self, event, minutes):
        self.scheduler.snooze(event, minutes)
        self.persist_states()
        self.update_popup([e for e in self.visible if e.key != event.key])

    def join_selected(self):
        selected = self.tree.selection()
        event = next((e for e in self.events if selected and e.key == selected[0]), None)
        if event:
            self.join(event)

    def join(self, event):
        if not event.links:
            messagebox.showinfo("Meeting Light", "This event has no recognised online meeting link.", parent=self.root)
        elif len(event.links) == 1:
            self.open_link(event, event.links[0][1])
        else:
            chooser = tk.Toplevel(self.root)
            chooser.title("Choose meeting link")
            chooser.attributes("-topmost", True)
            ttk.Label(chooser, text="This event has several meeting links.", padding=20).pack()
            for i, (provider, url) in enumerate(event.links, 1):
                def open_choice(link=url):
                    chooser.destroy()
                    self.open_link(event, link)
                ttk.Button(chooser, text=f"{provider} · link {i}", command=open_choice).pack(fill="x", padx=20, pady=5)

    def open_link(self, event, url, automatic=False):
        # Persist first for at-most-once behaviour even if opening a browser crashes.
        if not automatic:
            self.scheduler.joined(event)
        self.persist_states()
        try:
            if not webbrowser.open(url, new=2):
                raise RuntimeError("Browser unavailable")
            if not automatic:
                self.update_popup([e for e in self.visible if e.key != event.key])
        except Exception:
            if not automatic:
                self.scheduler.state(event)["dismissed"] = False
                self.persist_states()
            messagebox.showerror("Meeting Light", "The browser could not open. Try Join again.", parent=self.root)

    def test_reminder(self):
        now = now_utc()
        event = Event("test-" + str(time.time_ns()), "Test reminder · no real meeting", now + timedelta(minutes=1),
                      now + timedelta(minutes=10), ("test",), (("Test link", "https://example.com/"),))
        self.events_by_source["test"] = [event]
        self.events = merge_events([e for events in self.events_by_source.values() for e in events])
        self.last_agenda = None

    def show_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        win = self.settings_window = tk.Toplevel(self.root)
        win.title("Meeting Light — Settings")
        win.geometry("640x600")
        win.minsize(600, 550)
        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=18, pady=18)
        general, filtering, calendars = (ttk.Frame(notebook, padding=20) for _ in range(3))
        notebook.add(general, text="Reminders")
        notebook.add(filtering, text="Filters")
        notebook.add(calendars, text="Calendars")
        values = {}
        for row, (key, label, lo, hi) in enumerate([
            ("lead_minutes", "Remind before event (minutes)", 0, 120),
            ("refresh_minutes", "Refresh calendars (minutes)", 1, 1440)]):
            ttk.Label(general, text=label).grid(row=row, column=0, sticky="w", pady=12)
            values[key] = tk.StringVar(value=str(self.settings[key]))
            ttk.Spinbox(general, from_=lo, to=hi, textvariable=values[key], width=8).grid(row=row, column=1, padx=20)
        for row, (key, text) in enumerate([
            ("sound", "Play a sound when a reminder appears"),
            ("auto_open", "Automatically open meetings 1 minute before start"),
            ("startup", "Start Meeting Light when I sign in")], 2):
            values[key] = tk.BooleanVar(value=self.settings[key])
            box = ttk.Checkbutton(general, text=text, variable=values[key])
            box.grid(row=row, column=0, columnspan=2, sticky="w", pady=12)
            if key == "startup" and self.demo:
                box.configure(state="disabled")
        ttk.Label(general, text="Automatic opening opens the page in your default browser.\nIt does not join the call or enable your camera/microphone.", style="Sub.TLabel", wraplength=490).grid(row=5, column=0, columnspan=2, sticky="w", pady=20)
        values["online_only"] = tk.BooleanVar(value=self.settings["online_only"])
        ttk.Checkbutton(filtering, text="Only remind for online meetings", variable=values["online_only"]).pack(anchor="w")
        ttk.Label(filtering, text="Zoom, Google Meet, Teams and Proton Meet", style="Sub.TLabel").pack(anchor="w", pady=(5, 24))
        ttk.Label(filtering, text="Exclude exact event titles (one per line)").pack(anchor="w")
        exclusions = tk.Text(filtering, height=8, width=45, font=("Segoe UI", 11), relief="solid", bd=1)
        exclusions.insert("1.0", "\n".join(self.settings["exclusions"]))
        exclusions.pack(fill="x", pady=8)
        ttk.Label(filtering, text="Case and surrounding spaces are ignored.\nAll-day and cancelled events are always omitted.", style="Sub.TLabel").pack(anchor="w")
        ttk.Label(calendars, text="Private sources are encrypted; URLs are never displayed.", style="Sub.TLabel", wraplength=480).pack(anchor="w", pady=(0, 18))
        source_values = []
        for i, source in enumerate(self.sources):
            row = ttk.Frame(calendars)
            row.pack(fill="x", pady=7)
            enabled = tk.BooleanVar(value=source.get("enabled", True))
            name = tk.StringVar(value=source["name"])
            ttk.Checkbutton(row, variable=enabled).pack(side="left")
            ttk.Label(row, text="●", foreground=PALETTE[i % len(PALETTE)]).pack(side="left", padx=7)
            ttk.Entry(row, textvariable=name, width=26).pack(side="left")
            ttk.Label(row, text="  HTTPS · protected", style="Sub.TLabel").pack(side="left")
            source_values.append((source, enabled, name))
        def import_file():
            if self.fetching:
                messagebox.showinfo("Meeting Light", "Wait for the current refresh to finish, then import.", parent=win)
                return
            path = filedialog.askopenfilename(parent=win, title="Import private calendar URLs", filetypes=[("Text file", "*.txt"), ("All files", "*.*")])
            if not path:
                return
            try:
                new_sources = import_sources(path)
                old = {s["id"]: s for s in self.sources}
                for source in new_sources:
                    if source["id"] in old:
                        source.update(name=old[source["id"]]["name"], enabled=old[source["id"]]["enabled"])
                self.sources = new_sources
                self.events_by_source = {}
                self.events = []
                self.save_config()
                win.destroy()
                self.show_settings()
                self.refresh()
            except Exception:
                messagebox.showerror("Meeting Light", "Could not import this file. Use one HTTPS calendar URL per line.", parent=win)
        ttk.Button(calendars, text="Import calendars from text file…", command=import_file, state="disabled" if self.demo else "normal").pack(anchor="w", pady=24)
        ttk.Label(calendars, text="Import replaces the calendar list. Original files are unchanged.\nUse the checkboxes to disable individual calendars.", style="Sub.TLabel", wraplength=490).pack(anchor="w")
        bottom = ttk.Frame(win, padding=(18, 0, 18, 18))
        bottom.pack(fill="x")
        def save():
            try:
                lead, refresh = int(values["lead_minutes"].get()), int(values["refresh_minutes"].get())
                if not 0 <= lead <= 120 or not 1 <= refresh <= 1440:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Meeting Light", "Use 0–120 minutes for reminders and 1–1440 for refresh.", parent=win)
                return
            updated = dict(self.settings, lead_minutes=lead, refresh_minutes=refresh)
            for key in ("sound", "online_only", "auto_open", "startup"):
                updated[key] = values[key].get()
            updated["exclusions"] = [line.strip() for line in exclusions.get("1.0", "end").splitlines() if line.strip()]
            try:
                if not self.demo and updated["startup"] != self.settings["startup"]:
                    platform.set_startup(updated["startup"])
                self.settings = updated
                for source, enabled, name in source_values:
                    source.update(enabled=enabled.get(), name=name.get().strip() or "Calendar")
                self.save_config()
            except Exception:
                messagebox.showerror("Meeting Light", "Could not save settings or startup registration.", parent=win)
                return
            self.next_refresh = time.monotonic() + refresh * 60
            self.last_agenda = None
            self.popup_signature = None
            win.destroy()
        ttk.Button(bottom, text="Save settings", style="Accent.TButton", command=save).pack(side="right")
        ttk.Button(bottom, text="Cancel", command=win.destroy).pack(side="right", padx=8)

    def quit(self):
        self.closing = True
        self.persist_states()
        self.observer.close()
        platform.stop_tray(self.tray)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Meeting Light — private calendar reminders")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--enable-startup", action="store_true")
    parser.add_argument("--disable-startup", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        from .selfcheck import run
        run()
        return
    directory = args.data_dir or platform.data_dir()
    if args.demo:
        directory = args.data_dir or platform.data_dir().parent / "demo"
    lock = platform.InstanceLock(directory)
    if not lock.acquired:
        if not args.background:
            messagebox.showinfo("Meeting Light", "Meeting Light is already running. Open Upcoming events from its tray icon.")
        return
    try:
        store = Store(directory)
        if args.enable_startup or args.disable_startup:
            enabled = args.enable_startup and not args.disable_startup
            platform.set_startup(enabled)
            config = store.load("config", {"settings": dict(DEFAULTS), "sources": []})
            config["settings"]["startup"] = enabled
            store.save("config", config)
            print("Sign-in startup " + ("enabled" if enabled else "disabled"))
            return
        App(store, demo=args.demo, background=args.background).run()
    finally:
        lock.close()
