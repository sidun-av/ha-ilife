"""Pause tracking: a LAN pause leaves the robot reporting plain `standby`."""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

_PKG = pathlib.Path(
    os.environ.get("ILIFE_PKG")
    or pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "ilife"
)
_spec = importlib.util.spec_from_file_location("_ilife_pause", _PKG / "tuya_pause.py")
tuya_pause = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tuya_pause
_spec.loader.exec_module(tuya_pause)

CLEANING = {"smart", "zone_clean", "cleaning"}


def _tracker():
    return tuya_pause.PauseTracker(CLEANING)


def test_pause_then_standby_is_paused_until_status_moves():
    t = _tracker()
    t.on_status("smart", True)
    t.on_pause_sent()
    t.on_status("smart", True)   # the push from before the robot stopped
    assert not t.paused_by_us()
    t.on_status("standby", False)
    assert t.paused_by_us()
    t.on_status("standby", False)
    assert t.paused_by_us()
    t.on_status("goto_charge", False)
    assert not t.paused_by_us()
    t.on_status("standby", False)  # a later stop is not a pause
    assert not t.paused_by_us()


def test_start_clears_pause():
    t = _tracker()
    t.on_pause_sent()
    t.on_status("standby", False)
    assert t.paused_by_us()
    t.on_command_sent()
    assert not t.paused_by_us()
    t.on_status("standby", False)
    assert not t.paused_by_us()


def test_standby_without_a_pause_is_not_paused():
    t = _tracker()
    t.on_status("smart", True)
    t.on_status("standby", False)
    assert not t.paused_by_us()


def test_resumed_elsewhere_clears_pause():
    t = _tracker()
    t.on_pause_sent()
    t.on_status("standby", False)
    t.on_status("smart", True)
    assert not t.paused_by_us()
    t.on_status("standby", False)
    assert not t.paused_by_us()


def test_failed_send_restores_a_real_pause():
    t = _tracker()
    t.on_pause_sent()
    t.on_status("standby", False)
    assert t.paused_by_us()
    before = t.snapshot()
    t.on_command_sent()          # e.g. a resume that then fails to send
    t.restore(before)
    assert t.paused_by_us()
    t.on_status("smart", True)   # resumed for real later
    assert not t.paused_by_us()


def test_snapshot_of_idle_tracker_restores_idle():
    t = _tracker()
    before = t.snapshot()
    t.on_pause_sent()
    t.restore(before)
    t.on_status("standby", False)
    assert not t.paused_by_us()


def test_returning_or_docking_ends_a_pause():
    for status in ("goto_charge", "charging", "charge_done", "fault"):
        t = _tracker()
        t.on_pause_sent()
        t.on_status("standby", False)
        assert t.paused_by_us()
        t.on_status(status, False)
        assert not t.paused_by_us(), status


def test_a_pause_ended_elsewhere_is_forgotten_after_the_hold():
    """Paused here, then ended from the app: the robot stays in plain `standby`,
    so only time can tell. After the hold, Start must not send "resume"."""
    now = [1000.0]
    t = tuya_pause.PauseTracker(CLEANING, hold_seconds=600, clock=lambda: now[0])
    t.on_pause_sent()
    t.on_status("standby", False)
    now[0] += 599
    assert t.paused_by_us()
    now[0] += 1
    assert not t.paused_by_us()
    t.on_status("standby", False)  # still standby: not a pause any more
    assert not t.paused_by_us()


def test_the_hold_counts_from_the_last_pause_sent():
    now = [0.0]
    t = tuya_pause.PauseTracker(CLEANING, hold_seconds=600, clock=lambda: now[0])
    t.on_pause_sent()
    t.on_status("standby", False)
    now[0] = 500
    t.on_command_sent()             # resumed from here...
    t.on_status("smart", True)
    t.on_pause_sent()               # ...and paused again
    t.on_status("standby", False)
    now[0] = 1000
    assert t.paused_by_us()


def test_restore_keeps_the_hold_running():
    now = [0.0]
    t = tuya_pause.PauseTracker(CLEANING, hold_seconds=600, clock=lambda: now[0])
    t.on_pause_sent()
    t.on_status("standby", False)
    now[0] = 300
    before = t.snapshot()
    t.on_command_sent()
    t.restore(before)               # a resume that failed to send
    now[0] = 600
    assert not t.paused_by_us()
