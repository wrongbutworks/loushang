from __future__ import annotations


def sanitize_surrogates(text: str) -> str:
    """Remove unpaired UTF-16 surrogate code points from provider payload text."""
    sanitized: list[str] = []
    index = 0
    while index < len(text):
        codepoint = ord(text[index])
        if 0xD800 <= codepoint <= 0xDBFF:
            if index + 1 < len(text) and 0xDC00 <= ord(text[index + 1]) <= 0xDFFF:
                sanitized.append(text[index])
                sanitized.append(text[index + 1])
                index += 2
                continue
            index += 1
            continue
        if 0xDC00 <= codepoint <= 0xDFFF:
            index += 1
            continue
        sanitized.append(text[index])
        index += 1
    return "".join(sanitized)
