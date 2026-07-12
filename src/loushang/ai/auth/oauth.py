from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import inspect
import secrets
import threading
import time
from collections.abc import Awaitable
from typing import Literal, TypedDict, cast
from urllib.parse import parse_qs, urlparse

from loushang.ai.auth.types import OAuthCredentials
from loushang.ai.errors import AIAuthenticationError


class OAuthError(AIAuthenticationError):
    default_source = "loushang.ai.auth"


class OAuthReauthenticationRequiredError(OAuthError):
    pass


AuthorizationInputSource = Literal["callback", "manual"]


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def create_s256_code_challenge(verifier: str) -> str:
    return _base64url_encode(hashlib.sha256(verifier.encode("utf-8")).digest())


def generate_pkce_pair() -> tuple[str, str]:
    verifier = _base64url_encode(secrets.token_bytes(32))
    return verifier, create_s256_code_challenge(verifier)


def create_oauth_state() -> str:
    return _base64url_encode(secrets.token_bytes(32))


def _secrets_match(left: str, right: str) -> bool:
    try:
        return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
    except UnicodeError:
        return False


def _single_query_value(
    params: dict[str, list[str]],
    name: str,
) -> str | None:
    values = params.get(name)
    if values is None or len(values) != 1:
        return None
    return values[0]


def validate_oauth_flow_values(
    verifier: str,
    challenge: str,
    state: str,
    *,
    provider: str,
) -> None:
    values_are_non_empty = all(
        isinstance(value, str) and bool(value) for value in (verifier, challenge, state)
    )
    challenge_is_valid = values_are_non_empty and _secrets_match(
        challenge,
        create_s256_code_challenge(verifier),
    )
    state_is_independent = values_are_non_empty and not _secrets_match(
        state,
        verifier,
    )
    if not challenge_is_valid or not state_is_independent:
        raise OAuthError(
            "OAuth login could not initialize independent PKCE and state values.",
            provider=provider,
        )


def resolve_authorization_code(
    input_text: str,
    *,
    expected_state: str,
    source: AuthorizationInputSource,
    provider: str,
    provider_name: str,
) -> tuple[str, bool]:
    value = input_text.strip()
    code: str | None = None
    returned_state: str | None = None
    is_structured_response = False

    if value:
        parsed = urlparse(value)
        if parsed.scheme and parsed.netloc:
            params = parse_qs(parsed.query, keep_blank_values=True)
            code = _single_query_value(params, "code")
            returned_state = _single_query_value(params, "state")
            is_structured_response = True
        elif "#" in value:
            code, returned_state = value.split("#", 1)
            is_structured_response = True
        else:
            params = parse_qs(value.removeprefix("?"), keep_blank_values=True)
            if "code" in params or "state" in params:
                code = _single_query_value(params, "code")
                returned_state = _single_query_value(params, "state")
                is_structured_response = True
            else:
                code = value

    if not isinstance(code, str) or not code.strip():
        raise OAuthError(
            f"{provider_name} OAuth login did not receive an authorization code",
            provider=provider,
        )
    code = code.strip()

    if is_structured_response:
        if not returned_state or not _secrets_match(
            returned_state,
            expected_state,
        ):
            raise OAuthError(
                f"{provider_name} OAuth state mismatch",
                provider=provider,
            )
        return code, True

    if source != "manual":
        raise OAuthError(
            f"{provider_name} OAuth callback did not return a state-bound redirect",
            provider=provider,
        )
    return code, False


class GetOAuthApiKeyResult(TypedDict):
    newCredentials: OAuthCredentials
    apiKey: str


def get_oauth_api_key(
    provider: str, credentials_map: dict[str, OAuthCredentials]
) -> GetOAuthApiKeyResult | None:
    creds = credentials_map.get(provider)
    if creds is None:
        return None
    now = time.time()
    needs_refresh = creds.expires_at is not None and creds.expires_at <= now
    if needs_refresh:
        require_refresh_token(creds, provider=provider)
        refreshed = refresh_oauth_token(provider, creds)
        refreshed_token = _non_empty_token(refreshed.access_token)
        if refreshed_token is None:
            return None
        return {"newCredentials": refreshed, "apiKey": refreshed_token}
    token = _non_empty_token(creds.access_token)
    if token is None:
        return None
    return {"newCredentials": creds, "apiKey": token}


def refresh_oauth_token(provider: str, creds: OAuthCredentials) -> OAuthCredentials:
    from loushang.ai.auth.registry import get_default_oauth_registry

    require_refresh_token(creds, provider=provider)
    reg = get_default_oauth_registry()
    prov = reg.get(provider)
    if prov is None:
        raise ValueError(f"OAuth provider not found: {provider}")
    rt = prov.refresh_token  # type: ignore[attr-defined]
    if rt is None:
        raise ValueError(f"OAuth provider does not support refresh: {provider}")
    maybe = rt(creds)
    if inspect.isawaitable(maybe):
        return _run_awaitable_sync(cast("Awaitable[OAuthCredentials]", maybe))
    return maybe  # type: ignore[return-value]


def _run_awaitable_sync(awaitable: Awaitable[OAuthCredentials]) -> OAuthCredentials:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await_result(awaitable))

    result: dict[str, OAuthCredentials] = {}
    errors: list[BaseException] = []

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(_await_result(awaitable))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]
    return result["value"]


async def _await_result(awaitable: Awaitable[OAuthCredentials]) -> OAuthCredentials:
    return await awaitable


def _non_empty_token(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def require_refresh_token(
    credentials: OAuthCredentials,
    *,
    provider: str,
) -> str:
    refresh_token = _non_empty_token(credentials.refresh_token)
    if refresh_token is None:
        raise OAuthReauthenticationRequiredError(
            "OAuth credentials cannot be refreshed; log in again.",
            provider=provider,
        )
    return refresh_token
