"""Provider catalog and configuration lookup example.

This example does not call any remote API. It only reads the built-in model
catalog and prints the provider/endpoint/model facts needed before a real call.
"""

from __future__ import annotations

from dataclasses import dataclass

from loushang.ai import get_model, list_models


@dataclass(frozen=True)
class ProviderExample:
    provider_id: str
    endpoint_id: str
    model_id: str
    env_vars: tuple[str, ...]


PROVIDER_EXAMPLES = (
    ProviderExample(
        "openrouter",
        "openai-completions",
        "openai/gpt-oss-120b_free",
        ("OPENROUTER_API_KEY",),
    ),
    ProviderExample(
        "cloudflare-ai-gateway",
        "openai-completions",
        "workers-ai/@cf/moonshotai/kimi-k2.5",
        ("CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_GATEWAY_ID"),
    ),
    ProviderExample(
        "cloudflare-workers-ai",
        "openai-completions",
        "@cf/openai/gpt-oss-120b",
        ("CLOUDFLARE_API_KEY", "CLOUDFLARE_ACCOUNT_ID"),
    ),
    ProviderExample(
        "mistral",
        "openai-completions",
        "mistral-large-latest",
        ("MISTRAL_API_KEY",),
    ),
    ProviderExample(
        "google",
        "openai-completions",
        "gemini-2.5-flash",
        ("GEMINI_API_KEY",),
    ),
    ProviderExample(
        "google-vertex",
        "openai-completions",
        "gemini-2.5-flash",
        ("GOOGLE_VERTEX_ACCESS_TOKEN", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"),
    ),
)


def _format_model_line(example: ProviderExample) -> str:
    model = get_model(example.provider_id, example.endpoint_id, example.model_id)
    upstream = model.upstream_id
    suffix = f" upstream={upstream}" if isinstance(upstream, str) else ""
    env = ",".join(example.env_vars)
    return (
        f"{model.provider_id}:{model.endpoint_id}:{model.id} "
        f"api={model.api} env={env}{suffix}"
    )


def main() -> None:
    print(f"TOTAL models={len(list_models())}")
    for example in PROVIDER_EXAMPLES:
        print(_format_model_line(example))


if __name__ == "__main__":
    main()
