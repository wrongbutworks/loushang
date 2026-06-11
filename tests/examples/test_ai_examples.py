from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_model_lookup_example_targets_public_kimi_model() -> None:
    module = _load_module(Path("examples/ai/model_lookup.py"), "examples_ai_model_lookup")

    assert module.PROVIDER_ID == "moonshot"
    assert module.ENDPOINT_ID == "openai-completions"
    assert module.MODEL_ID == "kimi-k2.5"


def test_provider_matrix_example_targets_new_provider_models() -> None:
    module = _load_module(
        Path("examples/ai/provider_matrix.py"), "examples_ai_provider_matrix"
    )

    examples = {
        (item.provider_id, item.endpoint_id, item.model_id): item.env_vars
        for item in module.PROVIDER_EXAMPLES
    }

    assert examples[("openrouter", "openai-completions", "openai/gpt-oss-120b_free")]
    assert examples[("azure-openai-responses", "azure-openai-responses", "gpt-4o-mini")]
    assert examples[
        (
            "amazon-bedrock",
            "bedrock-converse-stream",
            "anthropic.claude-sonnet-4-5-20250929-v1_0",
        )
    ]


def test_provider_matrix_example_formats_upstream_model_id() -> None:
    module = _load_module(
        Path("examples/ai/provider_matrix.py"), "examples_ai_provider_matrix_format"
    )

    line = module._format_model_line(module.PROVIDER_EXAMPLES[0])

    assert "openai/gpt-oss-120b_free" in line
    assert "upstream=openai/gpt-oss-120b:free" in line


def test_complete_example_builds_expected_context() -> None:
    module = _load_module(Path("examples/ai/complete.py"), "examples_ai_complete")

    context = module._build_context()

    assert context["system_prompt"]
    assert context["messages"][0]["role"] == "user"


def test_tools_example_declares_add_tool() -> None:
    module = _load_module(Path("examples/ai/tools.py"), "examples_ai_tools")

    tools = module._build_tools()

    assert tools[0]["name"] == "add"
    assert tools[0]["parameters"]["required"] == ["a", "b"]


def test_typed_context_example_uses_public_types() -> None:
    module = _load_module(Path("examples/ai/typed_context.py"), "examples_ai_typed_context")

    context = module._build_context()

    assert context.system_prompt is not None
    assert context.messages[0].role == "user"
    assert context.tools is not None
    assert context.tools[0].name == "add"
