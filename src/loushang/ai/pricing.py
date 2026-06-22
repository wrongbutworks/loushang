from decimal import Decimal

from loushang.ai.model.domain import Model, Pricing
from loushang.ai.types import Usage, UsageCost


def calculate_usage_cost(
    pricing: Pricing | None, usage: Usage, *, multiplier: float = 1.0
) -> UsageCost | None:
    if pricing is None:
        return None
    known_component_tokens = (
        usage.input + usage.output + usage.cache_read + usage.cache_write
    )
    if usage.total_tokens > known_component_tokens:
        return None
    input_cost = _component_cost(pricing.input, usage.input)
    output_cost = _component_cost(pricing.output, usage.output)
    cache_read_cost = _component_cost(pricing.cache_read, usage.cache_read)
    cache_write_cost = _component_cost(pricing.cache_write, usage.cache_write)
    if (
        input_cost is None
        or output_cost is None
        or cache_read_cost is None
        or cache_write_cost is None
    ):
        return None
    if multiplier != 1.0:
        multiplier_decimal = Decimal(str(multiplier))
        input_cost *= multiplier_decimal
        output_cost *= multiplier_decimal
        cache_read_cost *= multiplier_decimal
        cache_write_cost *= multiplier_decimal
    total_cost = input_cost + output_cost + cache_read_cost + cache_write_cost
    return {
        "input": float(input_cost),
        "output": float(output_cost),
        "cacheRead": float(cache_read_cost),
        "cacheWrite": float(cache_write_cost),
        "total": float(total_cost),
    }


def _component_cost(
    price_per_million: float | int | None,
    tokens: int,
) -> Decimal | None:
    if tokens <= 0:
        return Decimal("0")
    if price_per_million is None:
        return None
    return Decimal(str(price_per_million)) * Decimal(tokens) / Decimal(1_000_000)


def models_are_equal(left: Model | None, right: Model | None) -> bool:
    if left is None or right is None:
        return False
    return (
        left.id == right.id
        and left.provider_id == right.provider_id
        and left.endpoint_id == right.endpoint_id
    )


def calculate_cost(model: Model, usage: Usage) -> UsageCost | None:
    return calculate_usage_cost(model.pricing, usage)
