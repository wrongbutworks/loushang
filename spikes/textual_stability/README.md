# Textual Stability Spike

This spike validates whether Textual remains stable under a timed, high-pressure terminal workload before `loushang-tui` commits to Textual as its implementation base.

## What It Simulates

- immediate warmup skeleton before stress starts
- streaming transcript deltas
- concurrent tool-pane updates
- auto-submitted input / ack cycles
- heartbeat and watchdog monitoring
- timed exit with pass/fail summary

## Run

Direct path:

```bash
python spikes/textual_stability/app.py --duration-seconds 180 --profile high
```

Module mode:

```bash
python -m spikes.textual_stability.app --duration-seconds 180 --profile high
```

Use the local checkout in `~/workspace/textual`:

```bash
python spikes/textual_stability/app.py --use-local-textual
```

Install the local checkout and its runtime dependencies into `loushang/.venv`:

```bash
.venv/bin/python -m pip install -e /home/dev/workspace/textual
```

## Notes

- The current `loushang` virtualenv does not ship Textual by default.
- `--use-local-textual` only adds the local checkout to `sys.path`; Textual runtime dependencies must still be installed in the active Python environment.
- The app enters a short `warming_up` phase first so the first screen paints before the high-pressure timers start.
- First verification target: macOS `Terminal.app`
- Second verification target: `iTerm2`

## Failure Criteria

- process crash
- terminal state not restored
- watchdog hard failure
- unrecoverable freeze in transcript, tool pane, or input activity
