from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict

from .abort_signal import ManualAbortSignal
from .adapters.anthropic_httpx import create_httpx_provider
from .adapters.anthropic_sdk import create_sdk_provider
from .adapters.faux import create_faux_provider
from .config import (
    build_mock_context,
    build_mock_model,
    build_real_context,
    build_real_model,
    resolve_api_key,
)
from .registry import clear_api_providers, register_api_provider
from .stream import complete, complete_simple, stream, stream_simple
from .types import SimpleStreamOptions, StreamOptions

DEFAULT_SCENARIO_TIMEOUT_SECONDS = 30


async def run_mock() -> dict[str, object]:
    clear_api_providers()
    register_api_provider(create_faux_provider())
    model = build_mock_model()
    context = build_mock_context()
    s1 = stream(model, context, StreamOptions())
    events: list[dict[str, object]] = []
    async for event in s1:
        events.append(asdict(event))
    message = await s1.result()
    completion = await complete(model, context, StreamOptions())

    s2 = stream_simple(model, context, SimpleStreamOptions(reasoning="low"))
    simple_events: list[dict[str, object]] = []
    async for event in s2:
        simple_events.append(asdict(event))
    simple_message = await s2.result()
    simple_completion = await complete_simple(model, context, SimpleStreamOptions(reasoning="low"))

    return {
        "events": events,
        "message": asdict(message),
        "completion": asdict(completion),
        "simple_events": simple_events,
        "simple_message": asdict(simple_message),
        "simple_completion": asdict(simple_completion),
    }


async def run_real() -> dict[str, object]:
    sdk_result = await _run_with_timeout("sdk", _run_sdk)
    httpx_result = await _run_with_timeout("httpx", _run_httpx)
    aborted_result = await _run_with_timeout("aborted", _run_aborted)
    return {"sdk": sdk_result, "httpx": httpx_result, "aborted": aborted_result}


async def _run_sdk() -> dict[str, object]:
    clear_api_providers()
    model = build_real_model()
    context = build_real_context()
    api_key = resolve_api_key()
    sdk_provider = create_sdk_provider()
    register_api_provider(sdk_provider)
    sdk_stream = stream(model, context, StreamOptions(api_key=api_key))
    sdk_events: list[dict[str, object]] = []
    async for event in sdk_stream:
        sdk_events.append(asdict(event))
    sdk_message = await sdk_stream.result()
    sdk_completion = await complete(model, context, StreamOptions(api_key=api_key))

    return {
        "carrier": "anthropic-sdk",
        "events": sdk_events,
        "message": asdict(sdk_message),
        "completion": asdict(sdk_completion),
    }


async def _run_httpx() -> dict[str, object]:
    clear_api_providers()
    model = build_real_model()
    context = build_real_context()
    api_key = resolve_api_key()
    httpx_provider = create_httpx_provider()
    register_api_provider(httpx_provider)
    httpx_stream = stream_simple(model, context, SimpleStreamOptions(api_key=api_key, reasoning="low"))
    httpx_events: list[dict[str, object]] = []
    async for event in httpx_stream:
        httpx_events.append(asdict(event))
    httpx_message = await httpx_stream.result()
    httpx_completion = await complete_simple(model, context, SimpleStreamOptions(api_key=api_key, reasoning="low"))

    return {
        "carrier": "httpx-thin",
        "events": httpx_events,
        "message": asdict(httpx_message),
        "completion": asdict(httpx_completion),
    }


async def _run_aborted() -> dict[str, object]:
    clear_api_providers()
    model = build_real_model()
    context = build_real_context()
    api_key = resolve_api_key()
    httpx_provider = create_httpx_provider()
    register_api_provider(httpx_provider)
    abort_signal = ManualAbortSignal()
    aborted_stream = stream(model, context, StreamOptions(api_key=api_key, signal=abort_signal))
    aborted_events: list[dict[str, object]] = []
    async for event in aborted_stream:
        aborted_events.append(asdict(event))
        if event.type == "text_delta":
            abort_signal.cancelled = True
    aborted_message = await aborted_stream.result()

    return {
        "carrier": "httpx-thin",
        "events": aborted_events,
        "message": asdict(aborted_message),
    }


async def _run_with_timeout(name: str, func):
    try:
        return {"status": "ok", "result": await asyncio.wait_for(func(), timeout=DEFAULT_SCENARIO_TIMEOUT_SECONDS)}
    except asyncio.TimeoutError:
        return {"status": "timeout", "timeout_seconds": DEFAULT_SCENARIO_TIMEOUT_SECONDS}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["mock", "sdk", "httpx", "aborted", "real", "all"], default="all")
    args = parser.parse_args()

    results: dict[str, object] = {}
    if args.mode in ("mock", "all"):
        results["mock"] = await run_mock()
    if args.mode == "sdk":
        results["sdk"] = await _run_with_timeout("sdk", _run_sdk)
    elif args.mode == "httpx":
        results["httpx"] = await _run_with_timeout("httpx", _run_httpx)
    elif args.mode == "aborted":
        results["aborted"] = await _run_with_timeout("aborted", _run_aborted)
    elif args.mode in ("real", "all"):
        results["real"] = await run_real()

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
