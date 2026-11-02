from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from meetinglight.floating_strip import clamp_position, FloatingStrip


@pytest.mark.parametrize('position,size,areas,expected', [
    (None, (200, 40), [(0, 0, 1920, 1040)], (1708, 988)),
    ([1900, 1035], (200, 40), [(0, 0, 1920, 1040)], (1720, 1000)),
    ([-1800, 100], (200, 40), [(0, 0, 1920, 1040), (-1920, 0, 0, 1080)], (-1800, 100)),
    ([3000, 500], (200, 40), [(0, 0, 1920, 1040)], (1720, 500)),
    ([1800, 1000], (200, 40), [(0, 0, 1280, 720)], (1080, 680)),
    ('corrupt', (200, 40), [(0, 0, 1920, 1040)], (1708, 988)),
])
def test_position_recovers_work_area_changes(position, size, areas, expected):
    assert clamp_position(position, size, areas) == expected


def strip(monkeypatch):
    from meetinglight import floating_strip as module
    native = SimpleNamespace(foreground_fullscreen=Mock(return_value=False),
                             show_strip_without_focus=Mock())
    monkeypatch.setattr(module, 'platform', native)
    obj = FloatingStrip.__new__(FloatingStrip)
    obj.app = SimpleNamespace(settings={'floating_strip': True, 'floating_strip_position': None},
                              locked=False, background='#fafafa')
    obj.label, obj.window, obj.place = Mock(), Mock(), Mock()
    obj.drag = None
    return obj, native


def test_visibility_and_stale_state(monkeypatch):
    obj, native = strip(monkeypatch)
    event = object()
    obj.update('12m · Project', event, True)
    assert obj.event is event
    assert obj.label.configure.call_args.kwargs['background'] == '#fff3d6'
    native.show_strip_without_focus.assert_called_once_with(obj.window)
    for reason in ('disabled', 'locked', 'fullscreen', 'outside_window', 'no_event'):
        obj.app.settings['floating_strip'] = reason != 'disabled'
        obj.app.locked = reason == 'locked'
        native.foreground_fullscreen.return_value = reason == 'fullscreen'
        obj.window.withdraw.reset_mock()
        obj.update('' if reason == 'outside_window' else '12m', None if reason == 'no_event' else event, False)
        obj.window.withdraw.assert_called_once()
    obj.app.locked = False
    native.foreground_fullscreen.return_value = False
    obj.update('11m · Project', event, False)
    assert obj.label.configure.call_args.kwargs['background'] == '#fafafa'
    assert native.show_strip_without_focus.call_count == 2


def test_countdown_advances_at_start():
    from datetime import datetime, timedelta, timezone
    from meetinglight.app import until_next
    from meetinglight.core import DEFAULTS, Event, eligible
    now = datetime.now(timezone.utc)
    first = Event('first', 'Project', now, now+timedelta(hours=1), ('a',))
    second = Event('second', 'Next', now+timedelta(minutes=12), now+timedelta(hours=2), ('a',))
    excluded = Event('busy', 'busy', now+timedelta(minutes=1), now+timedelta(hours=1), ('a',))
    events = [e for e in (first, excluded, second) if eligible(e, dict(DEFAULTS, exclusions=["busy"]), {'a'})]
    assert until_next(events, now) == '12m · Next'
    assert until_next(events, now, within_minutes=0) == ''
    assert until_next(events, now, chars=0) == '12m'


def test_drag_persists_and_click_selects_event(monkeypatch):
    obj, native = strip(monkeypatch)
    native.bring_to_front = Mock()
    obj.app.root, obj.app.tree, obj.app.save_config = Mock(), Mock(), Mock()
    obj.window.winfo_x.return_value = 200
    obj.window.winfo_y.return_value = 300
    obj.event = SimpleNamespace(key='next')
    obj.press(SimpleNamespace(x_root=20, y_root=30))
    obj.release(SimpleNamespace())
    native.bring_to_front.assert_called_once_with(obj.app.root)
    obj.app.tree.selection_set.assert_called_once_with('next')
    obj.press(SimpleNamespace(x_root=20, y_root=30))
    obj.motion(SimpleNamespace(x_root=40, y_root=50))
    obj.place.assert_called_once_with((220, 320))
    obj.release(SimpleNamespace())
    assert obj.app.settings['floating_strip_position'] == [200, 300]
    obj.app.save_config.assert_called_once()
    obj.reset()
    assert obj.app.settings['floating_strip_position'] is None
    obj.place.assert_called_with(None)

@pytest.mark.skipif(__import__('sys').platform != 'win32', reason='Windows native boundary')
@pytest.mark.parametrize('rect,window_class,expected', [
    ((0, 0, 1920, 1080), 'Game', True),
    ((0, 0, 1920, 1040), 'OrdinaryWindow', False),
    ((-1920, 0, 0, 1080), 'Game', True),
    ((0, 0, 1920, 1080), 'WorkerW', False),
])
def test_native_fullscreen_detection(monkeypatch, rect, window_class, expected):
    from meetinglight import platform_windows as p
    native = Mock()
    native.GetForegroundWindow.return_value = 123
    native.IsIconic.return_value = False
    def get_class(hwnd, buffer, size):
        buffer.value = window_class
        return len(window_class)
    def get_rect(hwnd, pointer):
        pointer._obj.left, pointer._obj.top, pointer._obj.right, pointer._obj.bottom = rect
        return True
    def get_monitor(handle, pointer):
        m = pointer._obj.monitor
        m.left, m.top, m.right, m.bottom = (-1920, 0, 0, 1080) if rect[0] < 0 else (0, 0, 1920, 1080)
        return True
    native.GetClassNameW.side_effect = get_class
    native.GetWindowRect.side_effect = get_rect
    native.GetMonitorInfoW.side_effect = get_monitor
    monkeypatch.setattr(p.ctypes.windll, 'user32', native)
    assert p.foreground_fullscreen() == expected
