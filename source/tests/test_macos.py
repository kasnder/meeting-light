import sys
import plistlib
import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS integrations")


def test_login_agent_enable_disable(tmp_path, monkeypatch):
    from meetinglight import platform_macos as platform
    path = tmp_path / "MeetingLight.plist"
    monkeypatch.setattr(platform, "startup_path", lambda: path)
    platform.set_startup(True)
    entry = plistlib.loads(path.read_bytes())
    assert entry["RunAtLoad"] is True
    assert entry["ProgramArguments"] == platform.launch_arguments()
    assert entry["ProgramArguments"][-1] == "--background"
    platform.set_startup(False)
    assert not path.exists()


def test_keychain_denial_never_writes_plaintext(tmp_path, monkeypatch):
    from meetinglight import platform_macos as platform
    from meetinglight.storage import Store
    class LockedKeychain:
        def get_password(self, *args):
            raise RuntimeError("Keychain locked")
    monkeypatch.setattr(platform, "Keyring", LockedKeychain)
    monkeypatch.setattr(platform, "_cipher", None)
    store = Store(tmp_path)
    with pytest.raises(RuntimeError):
        store.write("secret", b"synthetic private value")
    assert list(tmp_path.iterdir()) == []
