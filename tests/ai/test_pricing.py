from __future__ import annotations

from loushang.ai.model import Model, Pricing
from loushang.ai.pricing import calculate_cost, calculate_usage_cost
from loushang.ai.types import Usage


def _usage(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> Usage:
    return Usage(
        input=input_tokens,
        output=output_tokens,
        cache_read=cache_read_tokens,
        cache_write=cache_write_tokens,
        total_tokens=(
            input_tokens + output_tokens + cache_read_tokens + cache_write_tokens
        ),
        cost=None,
    )


def test_calculate_cost_returns_none_without_model_pricing() -> None:
    model = Model(id="custom", provider="custom", endpoint="openai-completions")

    assert calculate_cost(model, _usage(input_tokens=1000)) is None


def test_calculate_usage_cost_preserves_explicit_zero_prices() -> None:
    cost = calculate_usage_cost(
        Pricing(input=0, output=0, cache_read=0, cache_write=0),
        _usage(input_tokens=1000, output_tokens=1000),
    )

    assert cost == {
        "input": 0.0,
        "output": 0.0,
        "cacheRead": 0.0,
        "cacheWrite": 0.0,
        "total": 0.0,
    }


def test_calculate_usage_cost_returns_none_for_unknown_used_component() -> None:
    cost = calculate_usage_cost(
        Pricing(input=1.0, output=2.0),
        _usage(input_tokens=1000, output_tokens=1000, cache_read_tokens=1000),
    )

    assert cost is None


def test_calculate_usage_cost_returns_none_for_unallocated_total_tokens() -> None:
    cost = calculate_usage_cost(
        Pricing(input=1.0, output=2.0, cache_read=0, cache_write=0),
        Usage(
            input=0,
            output=0,
            cache_read=0,
            cache_write=0,
            total_tokens=1000,
            cost=None,
        ),
    )

    assert cost is None


def test_calculate_usage_cost_ignores_unknown_unused_component() -> None:
    cost = calculate_usage_cost(
        Pricing(input=1.0, output=2.0),
        _usage(input_tokens=1000, output_tokens=1000),
    )

    assert cost == {
        "input": 0.001,
        "output": 0.002,
        "cacheRead": 0.0,
        "cacheWrite": 0.0,
        "total": 0.003,
    }


def test_calculate_usage_cost_ignores_unknown_unused_input_and_output() -> None:
    cost = calculate_usage_cost(
        Pricing(cache_read=0.5, cache_write=0.25),
        _usage(cache_read_tokens=1000, cache_write_tokens=1000),
    )

    assert cost == {
        "input": 0.0,
        "output": 0.0,
        "cacheRead": 0.0005,
        "cacheWrite": 0.00025,
        "total": 0.00075,
    }
