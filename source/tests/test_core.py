from datetime import datetime, timedelta, timezone
from dataclasses import replace
import json
import pytest

from meetinglight.core import (DEFAULTS, Event, Scheduler, eligible, meeting_links,
                               merge_events, parse_calendar)

UTC = timezone.utc
NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


def event(key="a", title="Meeting", start=None, links=()):
    start = start or NOW + timedelta(minutes=1)
    return Event(key, title, start, start + timedelta(hours=1), ("one",), links)


def calendar(body):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Synthetic Tests//EN\r\n" + body.strip().replace("\n", "\r\n") + "\r\nEND:VCALENDAR\r\n").encode()


def vevent(extra="", uid="one", title="Meeting", start="20261029T130000Z", end="20261029T140000Z"):
    return f"BEGIN:VEVENT\nUID:{uid}\nDTSTART:{start}\nDTEND:{end}\nSUMMARY:{title}\n{extra}\nEND:VEVENT\n"


@pytest.mark.parametrize("title,expected", [("busy", False), (" BUSY ", False), ("Busy planning", True), ("Not busy", True)])
def test_exact_title_filter(title, expected):
    assert eligible(event(title=title), DEFAULTS, {"one"}) == expected


def test_filters_and_disabled_sources():
    assert not eligible(event(), dict(DEFAULTS, online_only=True), {"one"})
    assert eligible(event(links=(("Zoom", "https://zoom.us/j/123"),)), dict(DEFAULTS, online_only=True), {"one"})
    assert not eligible(event(), DEFAULTS, {"two"})
    assert not eligible(event(title="Focus"), dict(DEFAULTS, exclusions=["Focus"]), {"one"})


@pytest.mark.parametrize("url,provider", [
    ("https://us02web.zoom.us/j/123?pwd=abc", "Zoom"),
    ("https://meet.google.com/abc-defg-hij", "Google Meet"),
    ("https://teams.microsoft.com/l/meetup-join/19%3atest", "Teams"),
    ("https://teams.live.com/meet/123", "Teams"),
    ("https://meet.proton.me/join/abc#secret", "Proton Meet")])
def test_providers(url, provider):
    assert meeting_links(f'<a href="{url}">Join</a>') == ((provider, url),)


def test_links_deduplicate_and_reject_lookalikes():
    assert not meeting_links("https://zoom.us.evil.example/j/123 https://zoom.us@evil.example/j/1 file:///x https://zoom.us/")
    assert len(meeting_links("https://meet.google.com/abc https://meet.google.com/abc")) == 1
    assert meeting_links("https://zoom.us/j/12?x=1&amp;y=2")[0][1].endswith("x=1&y=2")


def test_calendar_recurring_modified_cancelled_and_folded_links():
    body = vevent("RRULE:FREQ=DAILY;COUNT=3\nDESCRIPTION:https://meet.google.com/abc-\n defg-hij")
    body += vevent("RECURRENCE-ID:20261030T130000Z", start="20261030T150000Z", end="20261030T160000Z")
    body += vevent("RECURRENCE-ID:20261031T130000Z\nSTATUS:CANCELLED", start="20261031T130000Z", end="20261031T140000Z")
    parsed = parse_calendar(calendar(body), "one", NOW)
    assert len(parsed) == 2
    assert sorted(e.start.hour for e in parsed) == [13, 15]
    assert any(e.links and e.links[0][1] == "https://meet.google.com/abc-defg-hij" for e in parsed)
    # Changing the moved occurrence's time must not change its identity.
    revised = parse_calendar(calendar(body.replace("20261030T150000Z", "20261030T170000Z")), "one", NOW)
    assert {e.key for e in revised} == {e.key for e in parsed}


def test_all_day_cancelled_and_ended_omitted():
    body = vevent("STATUS:CANCELLED")
    body += vevent(uid="day").replace("DTSTART:20261029T130000Z", "DTSTART;VALUE=DATE:20261029").replace("DTEND:20261029T140000Z", "DTEND;VALUE=DATE:20261030")
    body += vevent(uid="past", start="20261028T100000Z", end="20261028T110000Z")
    assert parse_calendar(calendar(body), "one", NOW) == []


def test_dst_and_exdate():
    raw = calendar("""BEGIN:VEVENT
UID:dst
DTSTART;TZID=Europe/Berlin:20261024T090000
DTEND;TZID=Europe/Berlin:20261024T100000
RRULE:FREQ=DAILY;COUNT=3
EXDATE;TZID=Europe/Berlin:20261026T090000
SUMMARY:Morning
END:VEVENT""")
    results = parse_calendar(raw, "one", datetime(2026, 10, 24, tzinfo=UTC))
    assert [e.start.hour for e in results] == [7, 8]


def test_duplicate_sources_preserve_links_and_selection():
    a = event()
    b = replace(a, calendars=("two",), links=(("Zoom", "https://zoom.us/j/1"),))
    merged = merge_events([a, b])
    assert len(merged) == 1 and merged[0].calendars == ("one", "two")
    assert eligible(merged[0], DEFAULTS, {"two"})
    assert len(merged[0].links) == 1


def test_scheduler_timed_persistent_simultaneous_and_cancelled():
    clock = [NOW - timedelta(seconds=1)]
    scheduler = Scheduler(clock=lambda: clock[0])
    events = [event(), event("b")]
    assert scheduler.evaluate(events, DEFAULTS, {"one"})[0] == []
    clock[0] = NOW
    assert len(scheduler.evaluate(events, DEFAULTS, {"one"})[0]) == 2
    clock[0] += timedelta(minutes=2)
    assert len(scheduler.evaluate(events, DEFAULTS, {"one"})[0]) == 2
    assert scheduler.evaluate([], DEFAULTS, {"one"})[0] == []


def test_snooze_restart_dismiss_and_expiry():
    clock = [NOW]
    scheduler = Scheduler(clock=lambda: clock[0])
    e = event()
    scheduler.snooze(e, 1)
    scheduler = Scheduler(json.loads(json.dumps(scheduler.states)), clock=lambda: clock[0])
    assert scheduler.evaluate([e], DEFAULTS, {"one"})[0] == []
    clock[0] += timedelta(minutes=1)
    assert scheduler.evaluate([e], DEFAULTS, {"one"})[0] == [e]
    scheduler.dismiss(e)
    assert scheduler.evaluate([e], DEFAULTS, {"one"})[0] == []
    clock[0] = e.end
    assert scheduler.evaluate([e], DEFAULTS, {"one"})[0] == []


def test_auto_open_once_and_manual_suppression():
    scheduler = Scheduler(clock=lambda: NOW)
    e = event(links=(("Test", "https://example.com/"),))
    settings = dict(DEFAULTS, auto_open=True)
    assert scheduler.evaluate([e], settings, {"one"})[1] == [e]
    assert scheduler.evaluate([e], settings, {"one"})[1] == []
    restarted = Scheduler(json.loads(json.dumps(scheduler.states)), clock=lambda: NOW)
    assert restarted.evaluate([e], settings, {"one"})[1] == []
    other = replace(e, key="b")
    scheduler.joined(other)
    assert scheduler.evaluate([other], settings, {"one"}) == ([], [])


def test_recovery_no_overdue_browser_and_multiple_links():
    e = event(links=(("Test", "https://example.com/"),))
    scheduler = Scheduler(clock=lambda: NOW + timedelta(seconds=30))
    assert scheduler.evaluate([e], dict(DEFAULTS, auto_open=True), {"one"}, recovering=True) == ([e], [])
    scheduler = Scheduler(clock=lambda: NOW)
    multi = replace(e, links=e.links + (("Test2", "https://example.org/"),))
    assert scheduler.evaluate([multi], dict(DEFAULTS, auto_open=True), {"one"}) == ([multi], [])


def test_auto_timing_independent_of_lead():
    scheduler = Scheduler(clock=lambda: NOW)
    e = event(links=(("Test", "https://example.com/"),))
    assert scheduler.evaluate([e], dict(DEFAULTS, lead_minutes=0, auto_open=True), {"one"}) == ([], [e])


def test_moved_event_reconciles_reminder():
    scheduler = Scheduler(clock=lambda: NOW)
    e = event()
    assert scheduler.evaluate([e], DEFAULTS, {"one"})[0] == [e]
    moved = replace(e, start=NOW + timedelta(hours=1), end=NOW + timedelta(hours=2))
    assert scheduler.evaluate([moved], DEFAULTS, {"one"})[0] == []
