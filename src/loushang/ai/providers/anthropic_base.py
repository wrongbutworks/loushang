from __future__ import annotations

from typing import Any, Literal

from loushang.ai.options import CacheRetention, ThinkingLevel
from loushang.ai.providers.anthropic_oauth_compat import AnthropicOAuthCompat
from loushang.ai.utils import sanitize_surrogates


class AnthropicProviderBase:
    """
    Anthropic provider shared helpers to align semantics with pi-ai across SDK/HTTPX impls.
    """

    @staticmethod
    def supports_adaptive_thinking(model_id: str) -> bool:
        return any(
            tag in model_id
            for tag in ("opus-4-6", "opus-4.6", "sonnet-4-6", "sonnet-4.6")
        )

    @staticmethod
    def map_thinking_level_to_effort(
        level: ThinkingLevel | None, model_id: str
    ) -> Literal["low", "medium", "high", "max"] | None:
        if level is None:
            return None
        if level in ("minimal", "low"):
            return "low"
        if level == "medium":
            return "medium"
        if level == "high":
            return "high"
        # xhigh
        return "max" if ("opus-4-6" in model_id or "opus-4.6" in model_id) else "high"

    @staticmethod
    def is_oauth_token(api_key: str) -> bool:
        # Anthropic OAuth tokens include this marker
        return "sk-ant-oat" in (api_key or "")

    @staticmethod
    def resolve_cache_retention(
        cache_retention: CacheRetention | None,
    ) -> CacheRetention:
        if cache_retention in ("none", "short", "long"):
            return cache_retention  # type: ignore[return-value]
        return "short"  # default

    @classmethod
    def get_cache_control(
        cls,
        base_url: str | None,
        cache_retention: CacheRetention | None,
        *,
        supports_long_cache_retention: bool | None = None,
    ):
        retention = cls.resolve_cache_retention(cache_retention)
        if retention == "none":
            return {"retention": retention, "cacheControl": None}
        supports_long = (
            supports_long_cache_retention
            if supports_long_cache_retention is not None
            else isinstance(base_url, str) and "api.anthropic.com" in base_url
        )
        ttl = "1h" if retention == "long" and supports_long else None
        cache_control = {"type": "ephemeral", **({"ttl": ttl} if ttl else {})}
        return {"retention": retention, "cacheControl": cache_control}

    @staticmethod
    def merge_headers(*sources: dict[str, str] | None) -> dict[str, str]:
        out: dict[str, str] = {}
        for s in sources:
            if s:
                out.update(s)
        return out

    @classmethod
    def apply_beta_headers(
        cls,
        *,
        existing_headers: dict[str, str] | None,
        need_interleaved_beta: bool,
        force_fine_grained_tools: bool = True,
    ) -> dict[str, str]:
        features: list[str] = []
        if force_fine_grained_tools:
            features.append("fine-grained-tool-streaming-2025-05-14")
        if need_interleaved_beta:
            features.append("interleaved-thinking-2025-05-14")
        if not features:
            return dict(existing_headers or {})
        out = dict(existing_headers or {})
        current = out.get("anthropic-beta") or out.get("Anthropic-Beta")
        if current:
            cur = {p.strip() for p in current.split(",") if p.strip()}
            for f in features:
                cur.add(f)
            out["anthropic-beta"] = ",".join(sorted(cur))
            out.pop("Anthropic-Beta", None)
        else:
            out["anthropic-beta"] = ",".join(features)
        return out

    @classmethod
    def apply_oauth_identity_headers(
        cls, existing_headers: dict[str, str] | None
    ) -> dict[str, str]:
        return AnthropicOAuthCompat.apply_identity_headers(existing_headers)

    @classmethod
    def to_oauth_tool_name(cls, name: str) -> str:
        return AnthropicOAuthCompat.to_provider_tool_name(name)

    @classmethod
    def from_oauth_tool_name(cls, name: str, tools: list[object] | None = None) -> str:
        return AnthropicOAuthCompat.from_provider_tool_name(name, tools)

    @classmethod
    def should_inject_fine_grained_tools(
        cls, *, compat: dict[str, object] | None, headers: dict[str, str] | None
    ) -> bool:
        # 若已存在 anthropic-beta，则允许合并（不强制新增）
        if headers:
            h = {k.lower(): v for k, v in headers.items()}
            if "anthropic-beta" in h:
                return True
        c = compat or {}
        # 显式开启
        if c.get("fineGrainedTools") is True:
            return True
        # 当 endpoint 声明 providerTransport 为 httpx 时默认开启
        if c.get("providerTransport") == "httpx":
            return True
        # 默认不注入，避免破坏既有单测/代理不识别 beta 的情况
        return False

    @classmethod
    def should_inject_interleaved_thinking(
        cls,
        *,
        model_id: str,
        options: object | None,
        compat: dict[str, object] | None,
    ) -> bool:
        c = compat or {}
        mode = c.get("interleavedThinking", "auto")
        if mode in (False, "off"):
            return False
        # 是否请求了思考：options.thinking_enabled / options.emit_thinking / options.reasoning
        want_thinking = False
        if options is not None:
            if getattr(options, "thinking_enabled", False):
                want_thinking = True
            if getattr(options, "emit_thinking", False):
                want_thinking = True
            if getattr(options, "reasoning", None) is not None:
                want_thinking = True
        if not want_thinking:
            return False
        # 4.6 系列内建，不注入
        if cls.supports_adaptive_thinking(model_id):
            return False
        # auto 模式：其余情况注入
        return True

    @staticmethod
    def assistant_block_to_anthropic_payload(block: object) -> dict[str, Any] | None:
        block_type = (
            getattr(block, "type", None)
            if not isinstance(block, dict)
            else block.get("type")
        )
        if block_type == "text":
            text = (
                getattr(block, "text", "")
                if not isinstance(block, dict)
                else block.get("text", "")
            )
            if isinstance(text, str) and text.strip():
                return {"type": "text", "text": sanitize_surrogates(text)}
            return None

        if block_type == "toolCall":
            tool_id = (
                getattr(block, "id", None)
                if not isinstance(block, dict)
                else block.get("id")
            )
            tool_name = (
                getattr(block, "name", None)
                if not isinstance(block, dict)
                else block.get("name")
            )
            tool_args = (
                getattr(block, "arguments", {})
                if not isinstance(block, dict)
                else (block.get("arguments") or {})
            )
            if isinstance(tool_id, str) and tool_id:
                return {
                    "type": "tool_use",
                    "id": tool_id,
                    "name": tool_name or "",
                    "input": tool_args or {},
                }
            return None

        if block_type == "thinking":
            thinking = (
                getattr(block, "thinking", "")
                if not isinstance(block, dict)
                else block.get("thinking", "")
            )
            if not isinstance(thinking, str) or not thinking.strip():
                return None

            signature = (
                getattr(block, "thinking_signature", None)
                if not isinstance(block, dict)
                else block.get("thinking_signature")
            )
            redacted = (
                getattr(block, "redacted", False)
                if not isinstance(block, dict)
                else bool(block.get("redacted"))
            )

            if redacted:
                if isinstance(signature, str) and signature.strip():
                    return {"type": "redacted_thinking", "data": signature}
                return {"type": "text", "text": sanitize_surrogates(thinking)}

            if isinstance(signature, str) and signature.strip():
                return {
                    "type": "thinking",
                    "thinking": sanitize_surrogates(thinking),
                    "signature": signature,
                }
            return {"type": "text", "text": sanitize_surrogates(thinking)}

        return None

    @staticmethod
    def tool_result_content_to_anthropic_payload(
        content: object,
    ) -> str | list[dict[str, Any]]:
        if not isinstance(content, list):
            return "(empty)"

        if all(
            (
                getattr(part, "type", None)
                if not isinstance(part, dict)
                else part.get("type")
            )
            == "text"
            for part in content
        ):
            text_parts = [
                getattr(part, "text", "")
                if not isinstance(part, dict)
                else part.get("text", "")
                for part in content
            ]
            text = "\n".join(
                part for part in text_parts if isinstance(part, str) and part.strip()
            )
            return sanitize_surrogates(text) or "(empty)"

        blocks: list[dict[str, Any]] = []
        for part in content:
            part_type = (
                getattr(part, "type", None)
                if not isinstance(part, dict)
                else part.get("type")
            )
            if part_type == "text":
                text = (
                    getattr(part, "text", "")
                    if not isinstance(part, dict)
                    else part.get("text", "")
                )
                if isinstance(text, str) and text.strip():
                    blocks.append({"type": "text", "text": sanitize_surrogates(text)})
            elif part_type == "image":
                data = (
                    getattr(part, "data", "")
                    if not isinstance(part, dict)
                    else part.get("data", "")
                )
                mime = (
                    getattr(part, "mime_type", "")
                    if not isinstance(part, dict)
                    else part.get("mimeType") or part.get("mime_type", "")
                )
                if isinstance(data, str) and data and isinstance(mime, str) and mime:
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": data,
                            },
                        }
                    )

        if not blocks:
            return "(empty)"
        if len(blocks) == 1 and blocks[0]["type"] == "text":
            return blocks[0]["text"]
        return blocks
