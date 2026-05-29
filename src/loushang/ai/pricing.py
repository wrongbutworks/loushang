from loushang.ai.model.domain import Model
from loushang.ai.types import Usage


def calculate_usage_cost(
    pricing, usage: Usage, *, multiplier: float = 1.0
) -> dict[str, float]:
    input_cost = float(pricing.input) * usage.input / 1_000_000
    output_cost = float(pricing.output) * usage.output / 1_000_000
    cache_read_cost = float(pricing.cache_read) * usage.cache_read / 1_000_000
    cache_write_cost = float(pricing.cache_write) * usage.cache_write / 1_000_000
    if multiplier != 1.0:
        input_cost *= multiplier
        output_cost *= multiplier
        cache_read_cost *= multiplier
        cache_write_cost *= multiplier
    total_cost = input_cost + output_cost + cache_read_cost + cache_write_cost
    return {
        "input": input_cost,
        "output": output_cost,
        "cacheRead": cache_read_cost,
        "cacheWrite": cache_write_cost,
        "total": total_cost,
    }


def models_are_equal(left: Model | None, right: Model | None) -> bool:
    if left is None or right is None:
        return False
    return (
        left.id == right.id
        and left.provider_id == right.provider_id
        and left.endpoint_id == right.endpoint_id
    )


def calculate_cost(model: Model, usage: Usage) -> dict[str, float]:
    return calculate_usage_cost(model.pricing, usage)
