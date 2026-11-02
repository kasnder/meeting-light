from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit
import requests

from .core import Event, parse_calendar, now_utc

WORKER_FLAG = "--parse-calendar"


def import_sources(path):
    urls = list(dict.fromkeys(line.strip() for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
                             if line.strip()))
    sources = []
    for i, url in enumerate(urls):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Sources must be HTTPS calendar URLs")
        sources.append(dict(id=sha256(url.encode()).hexdigest()[:20], name=f"Calendar {i + 1}",
                            url=url, enabled=True))
    if not sources:
        raise ValueError("No calendar URLs found")
    return sources


def download(url):
    # No redirects: avoid forwarding a secret URL to another host.
    session = requests.Session()
    session.trust_env = False  # No third-party environment proxy or netrc authentication.
    with session, session.get(url, timeout=(10, 35), allow_redirects=False, stream=True) as response:
        if response.status_code != 200:
            raise ValueError("Calendar request failed")
        data = bytearray()
        for chunk in response.iter_content(65536):
            data.extend(chunk)
            if len(data) > 32 * 1024 * 1024:
                raise ValueError("Calendar exceeds size limit")
        return bytes(data)


def worker_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, WORKER_FLAG]
    return [sys.executable, str(Path(__file__).resolve().parent.parent / "run.py"), WORKER_FLAG]


def parse_worker(args):
    """Child side: calendar bytes on stdin, events as JSON on stdout. Never print exceptions."""
    try:
        source_id, now = args
        events = parse_calendar(sys.stdin.buffer.read(), source_id, datetime.fromisoformat(now))
        json.dump([dict(key=e.key, title=e.title, start=e.start.isoformat(), end=e.end.isoformat(),
                        calendars=e.calendars, links=e.links) for e in events], sys.stdout)
        return 0
    except Exception:
        return 1


def parse_isolated(raw, source_id, now, fallback=True):
    """Parse in a short-lived process. Large calendars grow Python's heap by hundreds of MB,
    which the long-running app would otherwise keep after every refresh."""
    try:
        result = subprocess.run(worker_command() + [source_id, now.isoformat()], input=raw,
                                capture_output=True, timeout=120,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise ValueError("Calendar worker failed")
        return [Event(e["key"], e["title"], datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"]),
                      tuple(e["calendars"]), tuple(tuple(link) for link in e["links"]))
                for e in json.loads(result.stdout)]
    except Exception:
        if not fallback:
            raise
        # A worker that cannot start must not hide calendars; invalid data fails here too.
        return parse_calendar(raw, source_id, now)


def load_source(source, store, fetch=True, clock=now_utc, downloader=download, parser=parse_isolated):
    name = "feed-" + source["id"]
    now = clock()
    if fetch:
        try:
            raw = downloader(source["url"])
            events = parser(raw, source["id"], now)
            store.write(name, raw)
            return source["id"], events, now.isoformat(), None
        except Exception:
            pass  # Exception messages can contain the secret URL. Do not log them.
    try:
        raw = store.read(name)
        if raw is not None:
            return source["id"], parser(raw, source["id"], now), None, ("Refresh failed; using saved calendar" if fetch else None)
    except Exception:
        pass
    return source["id"], [], None, "Calendar unavailable; retry or re-import sources"


def load_all(sources, store, fetch=True):
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda s: load_source(s, store, fetch), sources))
