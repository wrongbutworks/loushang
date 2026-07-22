"""Coding's policy profile over the shared Harness evaluator."""

from __future__ import annotations

from loushang.harness.policy_engine import PolicyEngine as _PolicyEngine


class PolicyEngine(_PolicyEngine):
    """Keep Coding's historic rule-id namespace while reusing Harness logic."""

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("rule_id_prefix", "coding")
        super().__init__(**kwargs)


__all__ = ["PolicyEngine"]
