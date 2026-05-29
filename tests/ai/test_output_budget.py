from __future__ import annotations

from types import SimpleNamespace

from loushang.ai.model.domain import Capabilities, Model
from loushang.ai.provider.output_budget import resolve_output_token_budget


def _model(max_tokens: int | None) -> Model:
	return Model(
		id="test-model",
		provider="test-provider",
		endpoint="test-endpoint",
		capabilities=Capabilities(max_tokens=max_tokens),
	)


def test_output_budget_uses_uncapped_options_override() -> None:
	budget = resolve_output_token_budget(
		_model(32768),
		SimpleNamespace(max_tokens=32000),
		SimpleNamespace(max_tokens=64000),
	)

	assert budget.value == 64000
	assert budget.source == "options"
	assert budget.explicit is True


def test_output_budget_uses_uncapped_resolved_default() -> None:
	budget = resolve_output_token_budget(
		_model(32768),
		SimpleNamespace(max_tokens=64000),
		SimpleNamespace(max_tokens=None),
	)

	assert budget.value == 64000
	assert budget.source == "defaults"
	assert budget.explicit is True


def test_output_budget_caps_model_capability_default() -> None:
	budget = resolve_output_token_budget(
		_model(32768),
		SimpleNamespace(max_tokens=None),
		SimpleNamespace(max_tokens=None),
	)

	assert budget.value == 32000
	assert budget.source == "model"
	assert budget.explicit is False


def test_output_budget_falls_back_when_model_has_no_capability() -> None:
	budget = resolve_output_token_budget(
		_model(None),
		SimpleNamespace(max_tokens=None),
		SimpleNamespace(max_tokens=None),
	)

	assert budget.value == 8192
	assert budget.source == "fallback"
	assert budget.explicit is False
