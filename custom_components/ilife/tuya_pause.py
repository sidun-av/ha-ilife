"""Remember a pause this integration asked for.

Asked to pause over the LAN, an ILIFE Clean robot stops, reports status `standby` and
clears its own `pause` flag again almost at once, so its data alone cannot tell a
paused clean from a finished one. Without this, the entity would show `idle` and the
next Start would begin a new full clean instead of resuming.

The robot cannot say either when such a pause ends elsewhere: a clean paused here
and then ended from the app or the robot's button stays in plain `standby` too. A
pause is therefore also forgotten when the robot reports anything but paused or
cleaning (returning, docked, charging, a fault) and, failing that, after
PAUSE_HOLD_SECONDS. It lives in memory only: after a restart a paused robot shows
`idle` and Start begins a new clean.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Collection

_PAUSED = frozenset({"standby", "pause", "paused"})
# How long a pause sent from here is believed without anything to confirm it. A
# pause is resumed within minutes, rarely hours; a `standby` older than this is far
# more likely a clean ended from the app (see above) than a pause still waiting, and
# believing it would make Start send "resume" to a robot that has no job. A bound
# chosen for that trade-off, not a firmware timeout.
PAUSE_HOLD_SECONDS = 2 * 3600


class PauseTracker:
    """Pure state machine fed with the commands sent and the statuses reported.

    `cleaning_statuses` are the status values meaning "cleaning" (const.py's
    TUYA_STATUS_CLEANING; passed in so this module stays importable on its own).
    `clock` is injectable for the tests."""

    def __init__(self, cleaning_statuses: Collection[str],
                 hold_seconds: float = PAUSE_HOLD_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._cleaning = frozenset(s.lower() for s in cleaning_statuses)
        self._hold = hold_seconds
        self._clock = clock
        self._armed = False   # pause sent; the robot may not have stopped yet
        self._paused = False  # ... and it has since reported standby/paused
        self._sent_at = 0.0

    def _expire(self) -> None:
        if self._armed and self._clock() - self._sent_at >= self._hold:
            self.on_command_sent()

    def paused_by_us(self) -> bool:
        self._expire()
        return self._paused

    def snapshot(self) -> tuple[bool, bool, float]:
        """The state before a send, to restore if the send fails."""
        return (self._armed, self._paused, self._sent_at)

    def restore(self, state: tuple[bool, bool, float]) -> None:
        self._armed, self._paused, self._sent_at = state

    def on_pause_sent(self) -> None:
        self._armed = True
        self._paused = False
        self._sent_at = self._clock()

    def on_command_sent(self) -> None:
        """Any other run command (start, resume, stop, dock, ...) ends the pause."""
        self._armed = False
        self._paused = False

    def on_status(self, status: str | None, power_go: bool | None = None) -> None:
        self._expire()
        if not self._armed or status is None:
            return
        s = str(status).lower()
        if s in _PAUSED:
            # A run flag back on means it was resumed (e.g. from the app).
            if power_go is True and self._paused:
                self.on_command_sent()
            else:
                self._paused = True
            return
        if s in self._cleaning:
            # Still cleaning right after the pause was sent: wait for it to stop.
            # Cleaning again after it had stopped: resumed elsewhere.
            if self._paused:
                self.on_command_sent()
            return
        # Docking, charging, fault, ...: the paused clean is over.
        self.on_command_sent()
