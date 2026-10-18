"""Remember a pause this integration asked for.

Asked to pause over the LAN, an ILIFE Clean robot stops, reports status `standby` and
clears its own `pause` flag again almost at once, so its data alone cannot tell a
paused clean from a finished one. Without this, the entity would show `idle` and the
next Start would begin a new full clean instead of resuming.
"""
from __future__ import annotations

from collections.abc import Collection

_PAUSED = frozenset({"standby", "pause", "paused"})


class PauseTracker:
    """Pure state machine fed with the commands sent and the statuses reported.

    `cleaning_statuses` are the status values meaning "cleaning" (const.py's
    TUYA_STATUS_CLEANING; passed in so this module stays importable on its own)."""

    def __init__(self, cleaning_statuses: Collection[str]) -> None:
        self._cleaning = frozenset(s.lower() for s in cleaning_statuses)
        self._armed = False   # pause sent; the robot may not have stopped yet
        self._paused = False  # ... and it has since reported standby/paused

    def paused_by_us(self) -> bool:
        return self._paused

    def snapshot(self) -> tuple[bool, bool]:
        """The state before a send, to restore if the send fails."""
        return (self._armed, self._paused)

    def restore(self, state: tuple[bool, bool]) -> None:
        self._armed, self._paused = state

    def on_pause_sent(self) -> None:
        self._armed = True
        self._paused = False

    def on_command_sent(self) -> None:
        """Any other run command (start, resume, stop, dock, ...) ends the pause."""
        self._armed = False
        self._paused = False

    def on_status(self, status: str | None, power_go: bool | None = None) -> None:
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
