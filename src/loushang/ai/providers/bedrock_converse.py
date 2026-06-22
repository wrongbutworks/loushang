from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import json
import os
from collections.abc import AsyncIterator, Mapping
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from loushang.ai.event_stream import AssistantMessageEventStream, RawAssembler
from loushang.ai.options import get_timeout_seconds
from loushang.ai.output_budget import resolve_output_token_budget
from loushang.ai.provider import resolve_provider_request
from loushang.ai.provider.cancellation import is_signal_cancelled
from loushang.ai.provider.errors import provider_error_part
from loushang.ai.types import AssistantMessage, TextPart, UserMessage

SERVICE = "bedrock"


class BedrockConverseProvider:
    api = "bedrock-converse-stream"

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def stream(self, model, context, options, request=None):
        resolved = resolve_provider_request(
            self.api,
            model,
            options=options,
            request=request,
        )
        stream = AssistantMessageEventStream()
        assembler = RawAssembler(
            stream=stream,
            api=resolved.api,
            provider=model.provider_id,
            model=model.id,
            pricing=getattr(model, "pricing", None),
        )

        async def _run() -> None:
            signal = getattr(options, "signal", None) if options is not None else None
            if is_signal_cancelled(signal):
                assembler.feed({"type": "aborted"})
                return
            try:
                async for part in self._stream_raw_parts(
                    model, context, options, resolved
                ):
                    if is_signal_cancelled(signal):
                        assembler.feed({"type": "aborted"})
                        return
                    assembler.feed(part)
            except Exception as error:
                assembler.feed(provider_error_part(error, source=self.api))

        stream.attach_task(asyncio.create_task(_run()))
        return stream

    async def stream_simple(self, model, context, options, request=None):
        return await self.stream(model, context, options, request)

    async def _stream_raw_parts(
        self, model, context, options, request=None
    ) -> AsyncIterator[dict]:
        resolved = resolve_provider_request(
            self.api,
            model,
            options=options,
            request=request,
        )
        normalized = context
        if not resolved.base_url:
            raise ValueError("Bedrock base URL is required")
        upstream_model_id = getattr(resolved, "upstream_model_id", None) or model.id
        body = _build_converse_body(model, normalized, resolved, options)
        url = (
            resolved.base_url.rstrip("/")
            + "/model/"
            + quote(upstream_model_id, safe="")
            + "/converse"
        )
        credentials = _resolve_aws_credentials()
        headers = _sign_request(
            method="POST",
            url=url,
            body=json.dumps(body, separators=(",", ":")).encode("utf-8"),
            credentials=credentials,
        )
        headers["content-type"] = "application/json"
        timeout = get_timeout_seconds(options)
        client = self._client or httpx.AsyncClient(timeout=timeout or 120)
        close_client = self._client is None
        try:
            response = await client.post(
                url, content=headers.pop("_body"), headers=headers
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if close_client:
                await client.aclose()

        yield {
            "type": "response_start",
            "response_id": response.headers.get("x-amzn-requestid", ""),
        }
        text = _extract_output_text(payload)
        if text:
            yield {"type": "text_delta", "text": text}
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(usage, dict):
            input_tokens = int(usage.get("inputTokens") or 0)
            output_tokens = int(usage.get("outputTokens") or 0)
            yield {
                "type": "usage_delta",
                "input": input_tokens,
                "output": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }
        yield {
            "type": "stop_reason",
            "stop_reason": _map_stop_reason(payload.get("stopReason")),
        }
        yield {"type": "response_done"}


def _build_converse_body(
    model,
    normalized: Mapping[str, Any],
    resolved,
    options,
) -> dict[str, Any]:
    body: dict[str, Any] = {"messages": _build_bedrock_messages(normalized)}
    system_prompt = normalized.get("system_prompt")
    if isinstance(system_prompt, str) and system_prompt:
        body["system"] = [{"text": system_prompt}]
    inference_config: dict[str, Any] = {
        "maxTokens": resolve_output_token_budget(model, resolved).value
    }
    temperature = getattr(options, "temperature", None) if options is not None else None
    if isinstance(temperature, int | float):
        inference_config["temperature"] = temperature
    body["inferenceConfig"] = inference_config
    return body


def _build_bedrock_messages(normalized: Mapping[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for message in normalized.get("messages", []):
        if isinstance(message, UserMessage):
            messages.append(
                {"role": "user", "content": [{"text": _text_content(message.content)}]}
            )
        elif isinstance(message, AssistantMessage):
            messages.append(
                {"role": "assistant", "content": [{"text": _assistant_text(message)}]}
            )
    if not messages:
        messages.append({"role": "user", "content": [{"text": ""}]})
    return messages


def _text_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts)
    return str(content)


def _assistant_text(message: AssistantMessage) -> str:
    parts: list[str] = []
    for part in message.content:
        if isinstance(part, TextPart):
            parts.append(part.text)
    return "\n".join(parts)


def _extract_output_text(payload: dict[str, Any]) -> str:
    message = (payload.get("output") or {}).get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return ""
    parts = [entry.get("text") for entry in content if isinstance(entry, dict)]
    return "\n".join(part for part in parts if isinstance(part, str))


def _map_stop_reason(value: object) -> str:
    if value == "max_tokens":
        return "length"
    if value == "tool_use":
        return "toolUse"
    return "stop"


def _resolve_aws_credentials() -> dict[str, str]:
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        raise ValueError(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are required for Bedrock"
        )
    credentials = {"access_key": access_key, "secret_key": secret_key}
    token = os.getenv("AWS_SESSION_TOKEN")
    if token:
        credentials["session_token"] = token
    return credentials


def _sign_request(
    *,
    method: str,
    url: str,
    body: bytes,
    credentials: dict[str, str],
) -> dict[str, str]:
    parsed = urlparse(url)
    region = _region_from_host(parsed.netloc)
    now = dt.datetime.now(dt.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    canonical_uri = parsed.path or "/"
    payload_hash = hashlib.sha256(body).hexdigest()
    headers = {
        "host": parsed.netloc,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    session_token = credentials.get("session_token")
    if session_token:
        headers["x-amz-security-token"] = session_token
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
    canonical_request = "\n".join(
        [
            method,
            canonical_uri,
            parsed.query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ]
    )
    credential_scope = f"{date_stamp}/{region}/{SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _signing_key(credentials["secret_key"], date_stamp, region)
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    headers["authorization"] = (
        "AWS4-HMAC-SHA256 "
        f"Credential={credentials['access_key']}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    headers["_body"] = body.decode("utf-8")
    return headers


def _signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    key = ("AWS4" + secret_key).encode("utf-8")
    for value in (date_stamp, region, SERVICE, "aws4_request"):
        key = hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()
    return key


def _region_from_host(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and parts[0] == "bedrock-runtime":
        return parts[1]
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
