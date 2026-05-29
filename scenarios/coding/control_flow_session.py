from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


SCENARIOS: dict[str, list[dict[str, object]]] = {
    "abort-recovery": [
        {"prompt": "long control flow run", "hold": True, "tool": True},
        {"wait_for": "tool_execution_start"},
        {"abort": True},
        {"prompt": "hello"},
        {
            "expect": {
                "interruption_count": 1,
                "request_cancelled_count": 0,
                "assistant_text_contains": "ok: hello",
                "model_call_count": 2,
                "tool_end_count": 0,
            }
        },
    ],
    "steer-during-run": [
        {"prompt": "draft presentation", "hold": True},
        {"steer": "make it more commercial"},
        {"complete": "ok: draft presentation"},
        {"expect": {"steer_count": 1, "follow_count": 0, "request_cancelled_count": 0}},
    ],
    "follow-during-run": [
        {"prompt": "draft presentation", "hold": True},
        {"follow": "summarize final changes"},
        {"complete": "ok: draft presentation"},
        {"expect": {"steer_count": 0, "follow_count": 1, "request_cancelled_count": 0}},
    ],
    "steer-then-follow": [
        {"prompt": "draft presentation", "hold": True},
        {"steer": "make it more commercial"},
        {"follow": "summarize final changes"},
        {"complete": "ok: draft presentation"},
        {"expect": {"steer_count": 1, "follow_count": 1, "request_cancelled_count": 0}},
    ],
    "follow-then-abort": [
        {"prompt": "draft presentation", "hold": True},
        {"follow": "summarize final changes"},
        {"abort": True},
        {"expect": {"follow_count": 1, "interruption_count": 1, "request_cancelled_count": 0}},
    ],
    "steer-then-abort": [
        {"prompt": "draft presentation", "hold": True},
        {"steer": "make it more commercial"},
        {"abort": True},
        {"expect": {"steer_count": 1, "interruption_count": 1, "request_cancelled_count": 0}},
    ],
    "abort-during-tool": [
        {"prompt": "run tool", "hold": True, "tool": True},
        {"wait_for": "tool_execution_start"},
        {"abort": True},
        {
            "expect": {
                "tool_start_count": 1,
                "tool_end_count": 0,
                "model_call_count": 1,
                "request_cancelled_count": 0,
            }
        },
    ],
    "abort-during-provider-stream": [
        {"prompt": "stream response", "hold": True, "stream": True},
        {"wait_for": "provider_stream_start"},
        {"abort": True},
        {
            "expect": {
                "provider_stream_start_count": 1,
                "interruption_count": 1,
                "request_cancelled_count": 0,
            }
        },
    ],
    "mixed-race": [
        {"prompt": "make product-definition-draft.md a commercial ppt", "hold": True, "tool": True},
        {"wait_for": "tool_execution_start"},
        {"steer": "make it more commercial"},
        {"follow": "then summarize the result"},
        {"abort": True},
        {"prompt": "hello"},
        {
            "expect": {
                "interruption_count": 1,
                "request_cancelled_count": 0,
                "steer_count": 1,
                "follow_count": 1,
                "assistant_text_contains": "ok: hello",
            }
        },
    ],
}


@dataclass
class ActiveRun:
    prompt: str
    tool: bool = False
    stream: bool = False


@dataclass
class ScenarioState:
    trace_scopes: frozenset[str] = frozenset()
    trace_file: Path | None = None
    simulate_bug: bool = False
    active_run: ActiveRun | None = None
    events: list[dict[str, object]] = field(default_factory=list)
    assistant_texts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    steers: list[str] = field(default_factory=list)
    follows: list[str] = field(default_factory=list)
    model_call_count: int = 0
    interruption_count: int = 0
    tool_start_count: int = 0
    tool_end_count: int = 0
    provider_stream_start_count: int = 0
    request_cancelled_count: int = 0

    def emit(self, kind: str, **payload: object) -> None:
        event = {"kind": kind, **payload}
        self.events.append(event)
        if _trace_scope_enabled(self.trace_scopes, "scenario"):
            print(f"  trace: {json.dumps(event, ensure_ascii=False, sort_keys=True)}", flush=True)
        if self.trace_file is not None:
            with self.trace_file.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    @property
    def assistant_text(self) -> str:
        return "\n".join(self.assistant_texts)

    @property
    def steer_count(self) -> int:
        return len(self.steers)

    @property
    def follow_count(self) -> int:
        return len(self.follows)


def run_step(state: ScenarioState, step: dict[str, object], *, index: int) -> list[str]:
    state.emit("step", index=index, step=step)
    if "prompt" in step:
        return _run_prompt(state, step)
    if "steer" in step:
        return _run_steer(state, str(step["steer"]))
    if "follow" in step:
        return _run_follow(state, str(step["follow"]))
    if "abort" in step:
        return _run_abort(state)
    if "complete" in step:
        return _run_complete(state, str(step["complete"]))
    if "wait_for" in step:
        return _run_wait_for(state, str(step["wait_for"]))
    if "expect" in step:
        expected = step["expect"]
        if not isinstance(expected, dict):
            return ["expect step must be an object"]
        return _run_expect(state, expected)
    return [f"unknown step: {step}"]


def _run_prompt(state: ScenarioState, step: dict[str, object]) -> list[str]:
    if state.active_run is not None:
        return [f"prompt started while another run is active: {state.active_run.prompt}"]
    prompt = str(step["prompt"])
    state.model_call_count += 1
    state.emit("event", type="message_start", role="user", text=prompt)
    state.active_run = ActiveRun(
        prompt=prompt,
        tool=bool(step.get("tool", False)),
        stream=bool(step.get("stream", False)),
    )
    if state.active_run.tool:
        state.tool_start_count += 1
        state.emit("event", type="tool_execution_start", tool_name="fake_tool")
    if state.active_run.stream:
        state.provider_stream_start_count += 1
        state.emit("event", type="provider_stream_start")
    if not bool(step.get("hold", False)):
        return _run_complete(state, f"ok: {prompt}")
    return []


def _run_steer(state: ScenarioState, text: str) -> list[str]:
    if state.active_run is None:
        return [f"steer requires an active run: {text}"]
    state.steers.append(text)
    state.emit("control", action="steer", text=text)
    return []


def _run_follow(state: ScenarioState, text: str) -> list[str]:
    if state.active_run is None:
        return [f"follow requires an active run: {text}"]
    state.follows.append(text)
    state.emit("control", action="follow", text=text)
    return []


def _run_abort(state: ScenarioState) -> list[str]:
    if state.active_run is None:
        return ["abort requires an active run"]
    state.interruption_count += 1
    state.emit("control", action="abort", prompt=state.active_run.prompt)
    if state.simulate_bug:
        for _ in range(20):
            state.request_cancelled_count += 1
            state.errors.append("Request cancelled.")
            state.emit("event", type="agent_end", stop_reason="aborted", error_message="Request cancelled.")
        if state.active_run.tool:
            state.tool_end_count += 1
            state.emit("event", type="tool_execution_end", tool_name="fake_tool", is_error=True)
    state.active_run = None
    return []


def _run_complete(state: ScenarioState, text: str) -> list[str]:
    if state.active_run is None:
        return [f"complete requires an active run: {text}"]
    if state.active_run.tool:
        state.tool_end_count += 1
        state.emit("event", type="tool_execution_end", tool_name="fake_tool", is_error=False)
    state.assistant_texts.append(text)
    state.emit("event", type="message_end", role="assistant", text=text)
    state.active_run = None
    return []


def _run_wait_for(state: ScenarioState, event_type: str) -> list[str]:
    if any(event.get("type") == event_type for event in state.events):
        state.emit("assert", name="wait_for", expected=event_type, actual=event_type)
        return []
    return [f"event not observed: {event_type}"]


def _run_expect(state: ScenarioState, expected: dict[str, object]) -> list[str]:
    failures: list[str] = []
    for name, value in expected.items():
        if name == "assistant_text_contains":
            actual_text = state.assistant_text
            if str(value) not in actual_text:
                failures.append(f"assistant text missing {value!r}; actual={actual_text!r}")
            state.emit("assert", name=name, expected=value, actual=actual_text)
            continue
        actual = getattr(state, str(name), None)
        if actual != value:
            failures.append(f"{name}: expected {value!r}, got {actual!r}")
        state.emit("assert", name=str(name), expected=value, actual=actual)
    return failures


def run_scenario(name: str, steps: list[dict[str, object]], args: argparse.Namespace) -> list[str]:
    state = ScenarioState(
        trace_scopes=_parse_trace_scopes(args.trace),
        trace_file=Path(args.trace_file).expanduser() if args.trace_file else None,
        simulate_bug=bool(args.simulate_bug),
    )
    print(f"\ncase: {name}")
    failures: list[str] = []
    for index, step in enumerate(steps, start=1):
        print(f"[{index}/{len(steps)}] {_step_label(step)}")
        failures.extend(run_step(state, step, index=index))
        if failures and not args.keep_going:
            break
    if state.active_run is not None:
        failures.append(f"scenario ended with active run: {state.active_run.prompt}")
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"- {failure}")
    else:
        print("PASS")
    print(
        "summary: "
        f"models={state.model_call_count} "
        f"steers={len(state.steers)} "
        f"follows={len(state.follows)} "
        f"interruptions={state.interruption_count} "
        f"request_cancelled={state.request_cancelled_count}"
    )
    return failures


def _step_label(step: dict[str, object]) -> str:
    for key in ("prompt", "steer", "follow", "abort", "complete", "wait_for", "expect"):
        if key in step:
            return f"{key}: {step[key]}"
    return str(step)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic coding control-flow scenarios.")
    parser.add_argument("--case", choices=[*sorted(SCENARIOS), "all"], default="all")
    parser.add_argument(
        "--trace",
        nargs="?",
        const="all",
        default="",
        help="Optional comma-separated trace scopes. Omit value to trace all deterministic scenario events.",
    )
    parser.add_argument("--trace-file")
    parser.add_argument("--simulate-bug", action="store_true", help="Replay the historical repeated-cancellation failure mode.")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--live", action="store_true", help="Reserved for future real-model workflow execution.")
    return parser.parse_args(argv)


def _parse_trace_scopes(raw: str) -> frozenset[str]:
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _trace_scope_enabled(scopes: frozenset[str], scope: str) -> bool:
    return "all" in scopes or scope in scopes


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.live:
        print("--live is reserved for the next workflow iteration; deterministic mode is available now.", file=sys.stderr)
        return 2

    if args.trace_file:
        trace_file = Path(args.trace_file).expanduser()
        trace_file.parent.mkdir(parents=True, exist_ok=True)
        trace_file.write_text("", encoding="utf-8")

    names = sorted(SCENARIOS) if args.case == "all" else [args.case]
    failures: list[str] = []
    for name in names:
        failures.extend(run_scenario(name, SCENARIOS[name], args))

    if failures:
        print(f"\nFAIL: {len(failures)} failure(s)")
        return 1
    print("\nPASS: all selected scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
