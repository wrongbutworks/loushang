"""Offline reasoning options example."""

from __future__ import annotations

import json

from loushang.ai import CallOptions, ReasoningOptions


def inspect_reasoning() -> dict[str, object]:
    options = CallOptions(
        reasoning=ReasoningOptions(
            effort="medium",
            budget_tokens=2048,
            expose_summary=True,
        ),
    )
    reasoning = options.reasoning
    assert isinstance(reasoning, ReasoningOptions)
    return {
        "reasoning": reasoning.effort,
        "budgetTokens": reasoning.budget_tokens,
        "events": [
            {"type": "thinking_delta", "delta": "reasoning trace"},
            {"type": "text_delta", "delta": "mock hello from offline fixture"},
        ],
        "stopReason": "stop",
    }


def main() -> None:
    print(json.dumps(inspect_reasoning(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
