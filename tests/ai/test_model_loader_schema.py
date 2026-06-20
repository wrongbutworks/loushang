from __future__ import annotations

from typing import Any

import pytest

from loushang.ai.model.loader import (
    load_layered_model_registry,
    load_model_registry,
    load_model_registry_from_directory,
    load_model_registry_from_file,
    validate_model_registry_raw,
)


def _minimal_registry_raw(*, schema_version: int | None = 1) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
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
    if schema_version is not None:
        raw["schemaVersion"] = schema_version
    return raw


def test_builtin_model_registry_matches_schema() -> None:
    registry = load_model_registry()

    assert registry.get_model("moonshot", "kimi-code-anthropic", "kimi-for-coding")


def test_model_registry_schema_accepts_implicit_v1_catalog() -> None:
    raw = _minimal_registry_raw(schema_version=None)

    validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_explicit_v1_catalog() -> None:
    raw = _minimal_registry_raw(schema_version=1)

    validate_model_registry_raw(raw)


def test_model_registry_schema_loads_v2_catalog_file(tmp_path) -> None:
    path = tmp_path / "models.v2.json"
    path.write_text(
        """
        {
          "schemaVersion": 2,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"],
                        "stream": true
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    registry = load_model_registry_from_file(path)

    model = registry.get_model("custom", "openai-completions", "model-a")
    assert model.supports_stream is True


def test_model_registry_schema_loads_v2_catalog_directory(tmp_path) -> None:
    path = tmp_path / "catalog"
    path.mkdir()
    (path / "models.v2.json").write_text(
        """
        {
          "schemaVersion": 2,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"]
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    registry = load_model_registry_from_directory(path)

    assert registry.get_model("custom", "openai-completions", "model-a")


def test_model_registry_schema_rejects_unknown_version() -> None:
    raw = _minimal_registry_raw(schema_version=3)

    with pytest.raises(ValueError, match="unsupported models registry schemaVersion"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_non_integer_version() -> None:
    raw = _minimal_registry_raw(schema_version=None)
    raw["schemaVersion"] = "2"

    with pytest.raises(ValueError, match="schemaVersion must be an integer"):
        validate_model_registry_raw(raw)


def test_layered_model_registry_loads_v2_overlay_without_version_stamping(tmp_path) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        """
        {
          "schemaVersion": 2,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "models": {
                    "model-a": {
                      "capabilities": {
                        "input": ["text"],
                        "output": ["text"]
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        encoding="utf-8",
    )

    registry = load_layered_model_registry(user_dir=user_dir)

    assert registry.get_model("custom", "openai-completions", "model-a")
    assert registry.get_model("moonshot", "kimi-code-anthropic", "kimi-for-coding")


def test_layered_model_registry_rejects_unknown_overlay_version(tmp_path) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        """
        {
          "schemaVersion": 99,
          "providers": {}
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported models registry schemaVersion"):
        load_layered_model_registry(user_dir=user_dir)


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


def test_model_registry_schema_accepts_auth_on_provider_endpoint_and_model() -> None:
    raw = {
        "providers": {
            "custom": {
                "auth": {
                    "kind": "apiKey",
                    "apiKeyEnvs": ["CUSTOM_API_KEY", "CUSTOM_FALLBACK_KEY"],
                    "extraHeaders": {"x-provider": "yes"},
                },
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "auth": {"extraHeaders": {"x-endpoint": "yes"}},
                        "models": {
                            "model-a": {
                                "auth": {"apiKeyEnv": "MODEL_API_KEY"},
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_endpoint_preferred_flag() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-responses": {
                        "api": "openai-responses",
                        "preferred": True,
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_colons_in_endpoint_keys() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions:cn:coding": {
                        "api": "openai-completions",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_colons_in_provider_keys() -> None:
    raw = {
        "providers": {
            "custom:cn": {
                "endpoints": {
                    "openai-responses": {
                        "api": "openai-responses",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    with pytest.raises(ValueError, match="must not contain ':'"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_colons_in_model_keys() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-responses": {
                        "api": "openai-responses",
                        "models": {
                            "model:a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    with pytest.raises(ValueError, match="must not contain ':'"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_non_boolean_endpoint_preferred_flag() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-responses": {
                        "api": "openai-responses",
                        "preferred": "yes",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                },
                            }
                        },
                    }
                },
            }
        }
    }

    with pytest.raises(ValueError, match="preferred"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_accepts_legacy_auth_override() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "authOverride": {"apiKeyEnv": "CUSTOM_API_KEY"},
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                },
            }
        }
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_auth_and_legacy_auth_override() -> None:
    raw = {
        "providers": {
            "custom": {
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "auth": {"apiKeyEnv": "CUSTOM_API_KEY"},
                        "authOverride": {"apiKeyEnv": "LEGACY_API_KEY"},
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                },
            }
        }
    }

    with pytest.raises(ValueError, match="both auth and authOverride"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_invalid_auth_shape() -> None:
    raw = {
        "providers": {
            "custom": {
                "auth": {
                    "apiKeyEnvs": "CUSTOM_API_KEY",
                    "extraHeaders": {"x-provider": 1},
                },
                "endpoints": {
                    "openai-completions": {
                        "api": "openai-completions",
                        "models": {
                            "model-a": {
                                "capabilities": {
                                    "input": ["text"],
                                    "output": ["text"],
                                }
                            }
                        },
                    }
                },
            }
        }
    }

    with pytest.raises(ValueError, match="apiKeyEnvs"):
        validate_model_registry_raw(raw)
