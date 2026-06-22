"""Offline simple reasoning options example."""

from __future__ import annotations

import json

from loushang.ai import SimpleCallOptions


def inspect_reasoning() -> dict[str, object]:
    options = SimpleCallOptions(
        reasoning="medium",
        thinking_budgets={"medium": 2048},
    )
    return {
        "reasoning": options.reasoning,
        "budgetTokens": options.thinking_budgets["medium"],
        "events": [
            {"type": "thinking_delta", "thinking": "reasoning trace"},
            {"type": "text_delta", "text": "mock hello from offline fixture"},
        ],
        "stopReason": "stop",
    }


def main() -> None:
    print(json.dumps(inspect_reasoning(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
