"""Offline stable error serialization example."""

from __future__ import annotations

import json

from loushang.ai import AIError, AIErrorInfo


def inspect_error_serialization() -> dict[str, object]:
    error = AIError(
        AIErrorInfo(
            code="authentication",
            message="Missing API key.",
            source="client",
            retryable=False,
            provider="moonshot",
            endpoint="openai-completions",
            model="kimi-k2.5",
            details={
                "hint": "Set MOONSHOT_API_KEY.",
                "Authorization": "Bearer secret-token",
                "nested": {"refresh_token": "refresh-secret"},
            },
        )
    )
    return error.to_dict()


def main() -> None:
    print(json.dumps(inspect_error_serialization(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
