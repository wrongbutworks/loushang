"""Offline response usage example."""

from __future__ import annotations

import json

from loushang.ai import Usage, usage_payload


def inspect_usage() -> dict[str, object]:
    usage = Usage(
        input=120,
        output=30,
        cache_read=10,
        cache_write=0,
        total_tokens=160,
        cost=None,
    )
    return usage_payload(usage)


def main() -> None:
    print(json.dumps(inspect_usage(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
