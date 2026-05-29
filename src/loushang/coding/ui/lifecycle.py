from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RunLifecycle:
    active: bool = False
    active_id: int = 0
    aborted_id: int | None = None

    def begin_work(self) -> int:
        self.active = True
        self.active_id += 1
        return self.active_id

    def end_work(self) -> None:
        self.active = False

    def mark_abort_requested(self) -> None:
        if self.active:
            self.aborted_id = self.active_id

    def abort_is_settling(self) -> bool:
        return self.active and self.aborted_id == self.active_id

    def clear_aborted(self, run_id: int) -> None:
        if self.aborted_id == run_id:
            self.aborted_id = None

    def visible_running(self, *, session_running: bool) -> bool:
        return self.active or session_running


__all__ = ["RunLifecycle"]
