from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
import requests

from .core import parse_calendar, now_utc


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


def load_source(source, store, fetch=True, clock=now_utc, downloader=download):
    name = "feed-" + source["id"]
    now = clock()
    if fetch:
        try:
            raw = downloader(source["url"])
            events = parse_calendar(raw, source["id"], now)
            store.write(name, raw)
            return source["id"], events, now.isoformat(), None
        except Exception:
            pass  # Exception messages can contain the secret URL. Do not log them.
    try:
        raw = store.read(name)
        if raw is not None:
            return source["id"], parse_calendar(raw, source["id"], now), None, ("Refresh failed; using saved calendar" if fetch else None)
    except Exception:
        pass
    return source["id"], [], None, "Calendar unavailable; retry or re-import sources"


def load_all(sources, store, fetch=True):
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda s: load_source(s, store, fetch), sources))
