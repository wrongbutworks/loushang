from __future__ import annotations


def normalize_user_content(content: object) -> list[dict]:
    if isinstance(content, list):
        return list(content)
    if isinstance(content, dict):
        return [content]
    raise TypeError(f"Unsupported user content type: {type(content)!r}")


def clamp_max_tokens(requested: int | None, max_allowed: int | None) -> int | None:
    if requested is None:
        return max_allowed
    if max_allowed is None:
        return requested
    return min(requested, max_allowed)


def compute_remaining_context(
    context_window: int | None, used_tokens: int, *, safety_margin: int = 0
) -> int | None:
    if context_window is None:
        return None
    remaining = context_window - max(0, used_tokens) - max(0, safety_margin)
    return max(0, remaining)


def estimate_tokens_simple_from_messages(messages: list[object]) -> int:
    # Very rough estimator: count visible text length and divide by 4
    total_chars = 0
    for m in messages:
        content = (
            getattr(m, "content", None) if not isinstance(m, dict) else m.get("content")
        )
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                text = (
                    getattr(part, "text", None)
                    if not isinstance(part, dict)
                    else part.get("text")
                )
                if isinstance(text, str):
                    total_chars += len(text)
        elif isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str):
                total_chars += len(text)
    # guard
    if total_chars <= 0:
        return 0
    return max(1, total_chars // 4)
