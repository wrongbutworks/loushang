from __future__ import annotations

import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from _support import (
    ENV_EXAMPLES_ARTIFACT_ROOT,
    ENV_EXAMPLES_MODEL_CATALOG,
    build_kimi_model,
    describe_model,
)

_KIMI_API_KEY_PRIORITY = (
    "KIMI_CODE_API_KEY",
)


def _mask(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 10:
        return "*" * len(value)
    return f"{value[:6]}...{value[-4:]}"


def _resolve_key_source() -> tuple[str, str] | tuple[None, str]:
    for name in _KIMI_API_KEY_PRIORITY:
        value = os.environ.get(name, "").strip()
        if value:
            return name, value
    return None, ""


def main() -> None:
    print("=== Loushang Coding API Probe ===")
    print(f"cwd: {Path.cwd()}")
    print(f"{ENV_EXAMPLES_ARTIFACT_ROOT}: {os.environ.get('LOUSHANG_EXAMPLES_ARTIFACT_ROOT', '<unset>')}")
    print(f"{ENV_EXAMPLES_MODEL_CATALOG}: {os.environ.get('LOUSHANG_EXAMPLES_MODEL_CATALOG', '<unset>')}")
    from _support import _resolve_model_catalog

    catalog = _resolve_model_catalog()
    print(f"resolved catalog: {catalog}")

    key_source, key_value = _resolve_key_source()
    if key_source is None:
        print("api key source: <none>")
    else:
        print(f"api key source: {key_source} ({_mask(key_value)})")

    for endpoint_id in ("kimi-code-anthropic", "kimi-code-openai"):
        model = build_kimi_model(endpoint_id=endpoint_id)
        info = describe_model(model)
        print(
            f"model[{endpoint_id}]: "
            f"provider={info['provider']} model={info['model']} api={info['api']} base_url={info['base_url']}"
        )


if __name__ == "__main__":
    main()
