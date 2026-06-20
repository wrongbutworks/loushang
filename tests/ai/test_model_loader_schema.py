from __future__ import annotations

import json
from typing import Any

import pytest

from loushang.ai.model import SupportStatus
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


def test_model_registry_schema_accepts_endpoint_protocol_features() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {
        "roles": {"developer": "supported"},
        "streaming": {
            "usage": "supported",
            "reasoningDelta": "unsupported",
        },
        "reasoning": {"effort": "unknown", "effortMap": {"off": None, "minimal": "low"}},
        "tools": {"strictSchema": "supported"},
        "cache": {"longRetention": "supported"},
        "session": {"idHeader": "supported"},
        "store": "unsupported",
    }

    validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_endpoint_protocol_before_v2() -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {"roles": {"developer": "supported"}}

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_model_protocol_features() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    model = raw["providers"]["custom"]["endpoints"]["openai-completions"]["models"][
        "model-a"
    ]
    model["protocol"] = {"reasoning": {"effort": "supported"}}

    with pytest.raises(ValueError, match="only supported on endpoints"):
        validate_model_registry_raw(raw)


def test_model_registry_loads_legacy_reasoning_effort_map_into_protocol(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=1)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {
        "supportsReasoningEffort": True,
        "reasoningEffortMap": {"off": None, "minimal": "low"},
    }
    path = tmp_path / "models.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    assert endpoint_contract.protocol.to_raw()["reasoning"] == {
        "effort": "supported",
        "effortMap": {"off": None, "minimal": "low"},
    }
    endpoint_raw = endpoint_contract.to_raw()
    assert "protocol" not in endpoint_raw

    validate_model_registry_raw(
        {
            "schemaVersion": 1,
            "providers": {
                "custom": {
                    "endpoints": {
                        "openai-completions": endpoint_raw,
                    }
                }
            },
        }
    )


def test_model_registry_loads_explicit_protocol_into_compat_bridge(tmp_path) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["compat"] = {"supportsDeveloperRole": True}
    endpoint["protocol"] = {
        "roles": {"developer": "unsupported"},
        "streaming": {"reasoningDelta": "supported"},
        "tools": {"strictSchema": "unsupported"},
        "reasoning": {
            "effort": "supported",
            "effortMap": {"off": None, "minimal": "low"},
        },
    }
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    assert endpoint_contract.protocol.to_raw() == {
        "roles": {"developer": "unsupported"},
        "streaming": {"reasoningDelta": "supported"},
        "reasoning": {
            "effort": "supported",
            "effortMap": {"off": None, "minimal": "low"},
        },
        "tools": {"strictSchema": "unsupported"},
    }
    assert endpoint_contract.compat["supportsDeveloperRole"] is False
    assert endpoint_contract.compat["supportsStreamReasoningDelta"] is True
    assert endpoint_contract.compat["supportsReasoningEffort"] is True
    assert endpoint_contract.compat["supportsStrictMode"] is False
    assert endpoint_contract.compat["reasoningEffortMap"] == {
        "off": None,
        "minimal": "low",
    }


def test_model_registry_preserves_explicit_unknown_protocol_on_to_raw(
    tmp_path,
) -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {
        "store": "unknown",
        "roles": {"developer": "unknown"},
        "tools": {"strictSchema": "unknown"},
    }
    path = tmp_path / "models.v2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    registry = load_model_registry_from_file(path)
    endpoint_contract = registry.get_endpoint("custom", "openai-completions")

    assert endpoint_contract is not None
    endpoint_raw = endpoint_contract.to_raw()
    assert endpoint_raw["protocol"] == {
        "store": "unknown",
        "roles": {"developer": "unknown"},
        "tools": {"strictSchema": "unknown"},
    }
    assert endpoint_raw["compat"]["supportsStore"] is False
    assert endpoint_raw["compat"]["supportsDeveloperRole"] is False
    assert endpoint_raw["compat"]["supportsStrictMode"] is False

    roundtrip_path = tmp_path / "roundtrip.v2.json"
    roundtrip_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "providers": {
                    "custom": {
                        "endpoints": {
                            "openai-completions": endpoint_raw,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    roundtrip_registry = load_model_registry_from_file(roundtrip_path)
    roundtrip_endpoint = roundtrip_registry.get_endpoint(
        "custom",
        "openai-completions",
    )

    assert roundtrip_endpoint is not None
    assert roundtrip_endpoint.protocol.store is SupportStatus.UNKNOWN
    assert roundtrip_endpoint.protocol.roles.developer is SupportStatus.UNKNOWN
    assert roundtrip_endpoint.protocol.tools.strict_schema is SupportStatus.UNKNOWN


def test_model_registry_schema_rejects_invalid_protocol_status() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {"roles": {"developer": "yes"}}

    with pytest.raises(ValueError, match="invalid support status"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_unknown_protocol_key() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {"streaming": {"usageEvents": "supported"}}

    with pytest.raises(ValueError, match="unknown keys"):
        validate_model_registry_raw(raw)


def test_model_registry_schema_rejects_invalid_protocol_effort_map() -> None:
    raw = _minimal_registry_raw(schema_version=2)
    endpoint = raw["providers"]["custom"]["endpoints"]["openai-completions"]
    endpoint["protocol"] = {"reasoning": {"effortMap": {"minimal": 1}}}

    with pytest.raises(ValueError, match="string-or-null map"):
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


def test_layered_model_registry_loads_v2_overlay_protocol(tmp_path) -> None:
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
                  "protocol": {
                    "roles": {"developer": "unsupported"}
                  },
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
    endpoint = registry.get_endpoint("custom", "openai-completions")

    assert endpoint is not None
    assert endpoint.protocol.roles.developer is SupportStatus.UNSUPPORTED


def test_layered_model_registry_rejects_v1_overlay_protocol(tmp_path) -> None:
    user_dir = tmp_path / "models"
    user_dir.mkdir()
    (user_dir / "custom.json").write_text(
        """
        {
          "schemaVersion": 1,
          "providers": {
            "custom": {
              "endpoints": {
                "openai-completions": {
                  "api": "openai-completions",
                  "protocol": {
                    "roles": {"developer": "unsupported"}
                  },
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

    with pytest.raises(ValueError, match="requires schemaVersion 2"):
        load_layered_model_registry(user_dir=user_dir)


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
