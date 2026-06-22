"""Offline response usage observation example."""

from __future__ import annotations

import json

from loushang.ai import UsageObservation, usage_observation_payload


def inspect_usage_observation() -> dict[str, object]:
    usage = UsageObservation(
        input=120,
        output=30,
        cache_read=10,
        cache_write=0,
        total_tokens=160,
        cost=None,
    )
    return usage_observation_payload(usage)


def main() -> None:
    print(json.dumps(inspect_usage_observation(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
