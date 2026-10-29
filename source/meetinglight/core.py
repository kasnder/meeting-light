from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from html import unescape
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from icalendar import Calendar
import recurring_ical_events
from tzlocal import get_localzone

UTC = timezone.utc


def now_utc():
    return datetime.now(UTC)


def meeting_links(text):
    """Only known HTTPS conferencing hosts, never executable URL schemes."""
    found = []
    for url in re.findall(r'https://[^\s<>"\x00-\x20]+', unescape(str(text)), re.I):
        url = url.rstrip(".,;!)]}'")
        try:
            p = urlsplit(url)
            host = (p.hostname or "").lower()
            if p.username or p.password or p.port not in (None, 443):
                continue
            provider = None
            if host == "zoom.us" or host.endswith(".zoom.us") or host == "zoom.com" or host.endswith(".zoom.com"):
                if re.match(r"/(j/|my/|s/|wc/|w/)", p.path):
                    provider = "Zoom"
            elif host == "meet.google.com" and len(p.path) > 1:
                provider = "Google Meet"
            elif host in ("teams.microsoft.com", "teams.live.com", "teams.cloud.microsoft") and len(p.path) > 1:
                provider = "Teams"
            elif host == "meet.proton.me" and len(p.path) > 1:
                provider = "Proton Meet"
            if provider and (provider, url) not in found:
                found.append((provider, url))
        except ValueError:
            continue
    return tuple(found)


@dataclass(frozen=True)
class Event:
    key: str
    title: str
    start: datetime
    end: datetime
    calendars: tuple[str, ...]
    links: tuple[tuple[str, str], ...] = ()


def parse_calendar(raw: bytes, source_id: str, now: datetime):
    cal = Calendar.from_ical(raw)
    if cal.name != "VCALENDAR":
        raise ValueError("Invalid calendar")
    tzname = str(cal.get("X-WR-TIMEZONE", ""))
    try:
        localzone = ZoneInfo(tzname) if tzname else get_localzone()
    except (ValueError, KeyError):
        localzone = get_localzone()

    def aware(dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=localzone)
        return dt.astimezone(UTC)

    events = []
    # Include in-progress events that began before today, but never expand unbounded.
    occurrences = recurring_ical_events.of(cal).between(now - timedelta(days=7), now + timedelta(days=8))
    for component in occurrences:
        if str(component.get("STATUS", "")).upper() == "CANCELLED":
            continue
        start = component.decoded("DTSTART", None)
        if not isinstance(start, datetime):  # Date-only all-day events are intentionally omitted.
            continue
        start = aware(start)
        end = component.decoded("DTEND", None)
        if not isinstance(end, datetime):
            duration = component.decoded("DURATION", timedelta(minutes=30))
            end = start + (duration if isinstance(duration, timedelta) else timedelta(minutes=30))
        end = aware(end)
        if end <= start:
            end = start + timedelta(minutes=1)
        if end <= now or start > now + timedelta(days=7):
            continue
        uid = str(component.get("UID", ""))
        rid = component.decoded("RECURRENCE-ID", start)
        identity = aware(rid).isoformat() if isinstance(rid, datetime) else str(rid)
        title = str(component.get("SUMMARY", "Untitled event"))
        # Missing UID cannot safely deduplicate across independent calendars.
        uid = uid or f"{source_id}:{title}:{start.isoformat()}"
        key = sha256(f"{uid}\0{identity}".encode()).hexdigest()
        texts = []
        for name in ("URL", "LOCATION", "DESCRIPTION", "X-ALT-DESC", "X-GOOGLE-CONFERENCE", "CONFERENCE"):
            values = component.get(name, [])
            values = values if isinstance(values, list) else [values]
            texts.extend(str(v) for v in values)
        events.append(Event(key, title, start, end, (source_id,), meeting_links("\n".join(texts))))
    return events


def merge_events(events):
    merged = {}
    for e in events:
        old = merged.get(e.key)
        if old:
            merged[e.key] = Event(e.key, old.title, old.start, old.end,
                                  tuple(dict.fromkeys(old.calendars + e.calendars)),
                                  tuple(dict.fromkeys(old.links + e.links)))
        else:
            merged[e.key] = e
    return sorted(merged.values(), key=lambda e: (e.start, e.title.casefold()))


DEFAULTS = dict(refresh_minutes=30, lead_minutes=1, sound=True, online_only=False,
                auto_open=False, startup=False, exclusions=["busy"])


def eligible(e, settings, enabled_sources):
    excluded = {x.strip().casefold() for x in settings["exclusions"]}
    return (e.title.strip().casefold() not in excluded
            and bool(set(e.calendars) & set(enabled_sources))
            and (not settings["online_only"] or bool(e.links)))


class Scheduler:
    """Pure scheduling engine. Browser and sound actions belong to the application."""
    def __init__(self, states=None, clock=now_utc):
        self.states = states if states is not None else {}
        self.clock = clock

    def state(self, event):
        return self.states.setdefault(event.key, {"expires": event.end.timestamp()})

    def dismiss(self, event):
        self.state(event)["dismissed"] = True

    def joined(self, event):
        self.state(event).update(opened=True, dismissed=True)

    def snooze(self, event, minutes):
        self.state(event)["snooze"] = (self.clock() + timedelta(minutes=minutes)).timestamp()

    def evaluate(self, events, settings, enabled, recovering=False):
        now = self.clock()
        visible, automatic = [], []
        for e in events:
            if e.end <= now or not eligible(e, settings, enabled):
                continue
            s = self.state(e)
            s["expires"] = e.end.timestamp()
            if s.get("dismissed"):
                continue
            reminder_due = e.start - timedelta(minutes=settings["lead_minutes"])
            auto_due = e.start - timedelta(minutes=1)
            if recovering and now > auto_due + timedelta(seconds=5):
                s["auto_skipped"] = True
            if now >= reminder_due and now.timestamp() >= s.get("snooze", 0):
                visible.append(e)
            if (settings["auto_open"] and len(e.links) == 1 and auto_due <= now < e.start
                    and not s.get("opened") and not s.get("auto_skipped")):
                # Never open old pages on first discovery/recovery or delayed timer delivery.
                if now <= auto_due + timedelta(seconds=5):
                    s["opened"] = True
                    automatic.append(e)
                else:
                    s["auto_skipped"] = True
        self.states = {k: v for k, v in self.states.items()
                       if v.get("expires", 0) > now.timestamp() - 86400}
        return visible, automatic
