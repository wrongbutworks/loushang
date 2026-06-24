"""OpenAI Codex contrib registration example.

Codex is not part of the default model catalog or builtin provider adapters.
Register this contrib module before looking up Codex models.
"""

from __future__ import annotations

from loushang.ai import ReasoningOptions, get_model
from loushang.ai.contrib.openai_codex import (
    OpenAICodexResponsesOptions,
    register_openai_codex_contrib,
)


def load_codex_model():
    register_openai_codex_contrib()
    return get_model("openai-codex", "openai-codex-responses", "gpt-5.3-codex")


def main() -> None:
    model = load_codex_model()
    options = OpenAICodexResponsesOptions(
        reasoning=ReasoningOptions(effort="low"),
        text_verbosity="low",
    )
    print(f"{model.provider_id}:{model.endpoint_id}:{model.id}")
    print(type(options).__name__)


if __name__ == "__main__":
    main()
