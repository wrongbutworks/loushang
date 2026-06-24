from __future__ import annotations

import os

from loushang.ai.auth.types import OAuthCredentials


def _provider_env_prefix(provider: str) -> str:
    return provider.upper().replace("-", "_").replace(":", "_")


def get_env_api_key(provider: str) -> str | None:
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_OAUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")

    if provider == "github-copilot":
        return (
            os.getenv("COPILOT_GITHUB_TOKEN")
            or os.getenv("GH_TOKEN")
            or os.getenv("GITHUB_TOKEN")
        )

    env_var = {
        "openai": "OPENAI_API_KEY",
        "moonshot": "KIMI_API_KEY",
        "dashscope": "DASHSCOPE_API_KEY",
    }.get(provider)
    return os.getenv(env_var) if env_var else None


def get_env_oauth_credentials(
    provider: str,
    *,
    env: dict[str, str] | None = None,
) -> OAuthCredentials | None:
    resolved_env = os.environ if env is None else env
    prefix = _provider_env_prefix(provider)

    token_names = [
        f"{prefix}_ACCESS_TOKEN",
        f"{prefix}_TOKEN",
    ]
    account_id_names = [
        f"{prefix}_ACCOUNT_ID",
    ]
    plan_names = [
        f"{prefix}_PLAN",
    ]

    access_token = next(
        (
            value.strip()
            for name in token_names
            if isinstance((value := resolved_env.get(name)), str) and value.strip()
        ),
        None,
    )
    if not access_token:
        return None

    extra: dict[str, object] = {}
    account_id = next(
        (
            value.strip()
            for name in account_id_names
            if isinstance((value := resolved_env.get(name)), str) and value.strip()
        ),
        None,
    )
    if account_id:
        extra["account_id"] = account_id

    plan = next(
        (
            value.strip()
            for name in plan_names
            if isinstance((value := resolved_env.get(name)), str) and value.strip()
        ),
        None,
    )
    if plan:
        extra["plan"] = plan

    return OAuthCredentials(
        provider=provider,
        access_token=access_token,
        extra=extra or None,
    )
