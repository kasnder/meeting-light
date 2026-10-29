from pathlib import Path
from meetinglight.storage import Store
from meetinglight.feeds import import_sources, load_source
from meetinglight.platform_api import InstanceLock
from test_core import NOW, calendar, vevent
import pytest


def test_dpapi_roundtrip_no_plaintext_and_atomic_replace(tmp_path):
    store = Store(tmp_path)
    private = b"synthetic secret, not a real URL"
    store.write("test", private)
    assert private not in (tmp_path / "test.bin").read_bytes()
    assert store.read("test") == private
    store.write("test", b"replacement")
    assert store.read("test") == b"replacement"
    assert not list(tmp_path.glob("*.tmp"))


def test_bad_ciphertext_not_silently_reset(tmp_path):
    store = Store(tmp_path)
    (tmp_path / "config.bin").write_bytes(b"not encrypted")
    with pytest.raises(OSError):
        store.load("config", {})


def test_feed_cache_failure_and_parse_failure(tmp_path):
    store = Store(tmp_path)
    source = dict(id="s", url="https://example.com/synthetic")
    raw = calendar(vevent())
    first = load_source(source, store, clock=lambda: NOW, downloader=lambda u: raw)
    assert len(first[1]) == 1 and first[2] and first[3] is None
    def failing(url):
        raise ValueError("DO NOT EXPOSE " + url)
    failed = load_source(source, store, clock=lambda: NOW, downloader=failing)
    assert len(failed[1]) == 1 and failed[2] is None
    assert source["url"] not in str(failed[3])
    invalid = load_source(source, store, clock=lambda: NOW, downloader=lambda u: b"broken feed")
    assert len(invalid[1]) == 1
    assert store.read("feed-s") == raw


def test_one_failure_does_not_change_other_feed(tmp_path):
    store = Store(tmp_path)
    good = load_source(dict(id="a", url="https://example.com/a"), store, clock=lambda: NOW,
                       downloader=lambda u: calendar(vevent()))
    bad = load_source(dict(id="b", url="https://example.com/b"), store, clock=lambda: NOW,
                      downloader=lambda u: b"bad")
    assert good[2] and not good[3]
    assert bad[3] and not bad[1]


def test_import_no_source_changes_and_deduplication(tmp_path):
    path = tmp_path / "source.txt"
    content = "https://example.com/a\nhttps://example.com/b\nhttps://example.com/a\n"
    path.write_text(content)
    sources = import_sources(path)
    assert len(sources) == 2 and sources[0]["name"] == "Calendar 1"
    assert path.read_text() == content
    path.write_text("http://example.com/a")
    with pytest.raises(ValueError):
        import_sources(path)


def test_instance_lock(tmp_path):
    first = InstanceLock(tmp_path)
    second = InstanceLock(tmp_path)
    assert first.acquired and not second.acquired
    second.close()
    first.close()
    third = InstanceLock(tmp_path)
    assert third.acquired
    third.close()


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows startup adapter")
def test_startup_can_be_enabled_and_disabled_without_touching_other_apps(tmp_path, monkeypatch):
    from meetinglight import platform_windows as platform
    entry = tmp_path / "MeetingLight.vbs"
    other = tmp_path / "WindowsAudioPower.vbs"
    other.write_text("existing speaker launcher")
    monkeypatch.setattr(platform, "startup_path", lambda: entry)
    platform.set_startup(True)
    assert platform.launch_command().replace('"', '""') in entry.read_text()
    assert "--background" in entry.read_text()
    platform.set_startup(False)
    assert not entry.exists()
    assert other.read_text() == "existing speaker launcher"
