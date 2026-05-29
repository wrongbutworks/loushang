from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ToolPhase = Literal["pending", "running", "done", "error"]


@dataclass
class TranscriptEntry:
    entry_id: str
    role: Literal["user", "assistant", "tool", "status"]
    text: str
    created_at: float
    streaming: bool = False
    updates: int = 0


@dataclass
class ToolEntry:
    tool_id: str
    title: str
    phase: ToolPhase
    progress: int
    last_update_at: float
    updates: int = 0


@dataclass
class InputState:
    buffer: str = ""
    submitting: bool = False
    last_submit_at: float | None = None
    last_ack_at: float | None = None
    submit_count: int = 0
    ack_count: int = 0


@dataclass
class SpikeHealthState:
    event_count: int = 0
    last_transcript_at: float | None = None
    last_tool_update_at: float | None = None


@dataclass
class SpikeState:
    transcript: list[TranscriptEntry] = field(default_factory=list)
    tools: dict[str, ToolEntry] = field(default_factory=dict)
    input_state: InputState = field(default_factory=InputState)
    health: SpikeHealthState = field(default_factory=SpikeHealthState)
    _entry_seq: int = 0

    def append_entry(self, role: Literal["user", "assistant", "tool", "status"], text: str, *, created_at: float, streaming: bool = False) -> TranscriptEntry:
        self._entry_seq += 1
        entry = TranscriptEntry(
            entry_id=f"entry-{self._entry_seq}",
            role=role,
            text=text,
            created_at=created_at,
            streaming=streaming,
        )
        self.transcript.append(entry)
        self.health.event_count += 1
        self.health.last_transcript_at = created_at
        return entry

    def append_assistant_delta(self, delta: str, *, now: float, finish: bool = False) -> TranscriptEntry:
        if self.transcript and self.transcript[-1].role == "assistant" and self.transcript[-1].streaming:
            entry = self.transcript[-1]
            entry.text += delta
            entry.updates += 1
            if finish:
                entry.streaming = False
        else:
            entry = self.append_entry("assistant", delta, created_at=now, streaming=not finish)
        self.health.event_count += 1
        self.health.last_transcript_at = now
        return entry

    def upsert_tool(self, tool_id: str, *, title: str, phase: ToolPhase, progress: int, now: float) -> ToolEntry:
        entry = self.tools.get(tool_id)
        if entry is None:
            entry = ToolEntry(tool_id=tool_id, title=title, phase=phase, progress=progress, last_update_at=now)
            self.tools[tool_id] = entry
        else:
            entry.title = title
            entry.phase = phase
            entry.progress = progress
            entry.last_update_at = now
            entry.updates += 1
        self.health.event_count += 1
        self.health.last_tool_update_at = now
        return entry

    def submit_input(self, text: str, *, now: float) -> None:
        self.input_state.buffer = text
        self.input_state.submitting = True
        self.input_state.last_submit_at = now
        self.input_state.submit_count += 1

    def ack_input(self, *, now: float) -> None:
        self.input_state.submitting = False
        self.input_state.buffer = ""
        self.input_state.last_ack_at = now
        self.input_state.ack_count += 1
