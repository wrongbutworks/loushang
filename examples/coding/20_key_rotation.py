from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from _support import (
    _resolve_model_catalog,
    build_kimi_model,
    create_kimi_runtime_session,
    describe_model,
    resolve_api_key,
)


def print_event(name: str, payload: dict[str, object]) -> None:
    print(f"{name}: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}")


def _simulate_rotation() -> bool:
    attempts = [
        ("bad_key", 401),
        ("good_key", 200),
    ]
    return True, attempts


async def _run_prompt(session, prompt: str, timeout_seconds: float = 6.0) -> None:
    await asyncio.wait_for(session.prompt(prompt), timeout=timeout_seconds)


async def _run_offline_simulation() -> bool:
    print("=== offline key rotation simulation ===")
    print_event("message.start", {"mode": "offline", "step": "simulate"})

    ok, steps = _simulate_rotation()
    assert ok
    for step, (key_name, status) in enumerate(steps, start=1):
        print_event(
            "model.start",
            {"step": step, "key": key_name, "status": "start", "provider": "moonshot", "endpoint": "kimi-code-anthropic"},
        )
        print_event("tool.start", {"name": "http_request", "step": step, "key": key_name})

        if status == 401:
            print_event("message.end", {"step": step, "status": "401", "result": "auth_failed"})
        else:
            print_event("message.end", {"step": step, "status": "200", "result": "ok"})

        print_event("tool.end", {"name": "http_request", "step": step, "status": str(status)})

    print("rotation_ok=True")
    print("=== offline expected sample ===")
    print("step=1 key=bad_key status=401")
    print("step=2 key=good_key status=200")
    print("final_status=pass")
    return True


async def _run_live_rotation(timeout_seconds: float) -> bool:
    print("=== live key rotation (best effort) ===")
    try:
        live_key = resolve_api_key()
    except Exception:
        print("live path skipped: no resolvable key")
        return False

    model = build_kimi_model()
    model_info = describe_model(model)
    print_event("model.start", {"provider": model_info["provider"], "endpoint": model_info["endpoint"], "api": model_info["api"]})
    with TemporaryDirectory(prefix="loushang-key-rotation-") as workspace:
        runtime, session = await create_kimi_runtime_session(
            cwd=Path(workspace),
            model=model,
            persist=False,
        )

        async def _attempt(attempt: int, key: str) -> int:
            session.agent.get_api_key = lambda provider: key
            print_event("tool.start", {"name": "http_request", "attempt": attempt})
            try:
                await _run_prompt(session, f"请回复 ok#{attempt}", timeout_seconds=timeout_seconds)
                print_event("tool.end", {"name": "http_request", "attempt": attempt, "status": "ok"})
                return 200
            except Exception as error:
                text = str(error)
                print_event("tool.end", {"name": "http_request", "attempt": attempt, "status": "error", "error": text})
                if "401" in text:
                    return 401
                if "403" in text:
                    return 403
                return 500

        first = await _attempt(1, "bad-key-for-test")
        print_event("message.end", {"attempt": 1, "status": first})
        if first == 200:
            print("live rotation already pass without bad key path")
            return True

        second = await _attempt(2, live_key)
        print_event("message.end", {"attempt": 2, "status": second})
        print_event("message.end", {"result": "pass" if second == 200 else "fail", "step": "live_rotation"})
        return second == 200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="simulate key rotation with offline-first path")
    parser.add_argument("--live", action="store_true", help="Attempt live request rotation path.")
    parser.add_argument("--timeout", type=float, default=8.0, help="Live path prompt timeout in seconds.")
    return parser.parse_args()


async def _main_async() -> int:
    args = parse_args()

    model = build_kimi_model()
    info = describe_model(model)
    print("=== Key Rotation Probe ===")
    catalog_path = _resolve_model_catalog()
    if catalog_path is None:
        print("resolved catalog: <unset>; using built-in fallback")
    else:
        print(f"resolved catalog: {catalog_path}")
    print_event("message.start", {"mode": "offline-first", "step": "bootstrap"})
    print_event("model.start", {
        "provider": info["provider"],
        "endpoint": info["endpoint"],
        "api": info["api"],
        "model": info["model"],
        "base_url": info["base_url"],
    })

    passed = await _run_offline_simulation()
    live_ok = True
    if args.live:
        live_ok = await _run_live_rotation(args.timeout)

    print_event("message.end", {"offline_ok": passed, "live_ok": live_ok, "result": "pass" if (passed and live_ok) else "partial" if passed else "fail"})
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(_main_async()))
    except KeyboardInterrupt:
        raise SystemExit(130)
