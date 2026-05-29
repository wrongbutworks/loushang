from __future__ import annotations

import pytest

from loushang.ai.model.loader import load_model_registry, validate_model_registry_raw


def test_builtin_model_registry_matches_schema() -> None:
    registry = load_model_registry()

    assert registry.list_models()


def test_model_registry_schema_rejects_unknown_compat_key() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "compat": {"supportsReasoningEffortTypo": True},
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                }
            }
        }
    }

    with pytest.raises(ValueError, match="unknown keys"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_invalid_modality() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text", "telepathy"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                }
            }
        }
    }

    with pytest.raises(ValueError, match="invalid modalities"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_non_object_root() -> None:
    with pytest.raises(ValueError, match="<root>"):
        validate_model_registry_raw([])  # type: ignore[arg-type]
