from __future__ import annotations

from loushang.ai.providers.provider_helpers import (
    get_header_case_insensitive,
    set_header_case_insensitive,
)


class AnthropicOAuthBridge:
    SDK_USER_AGENT = "loushang-ai"
    SDK_APP_ID = "sdk"
    _BETA_FEATURES = (
        "claude-code-20250219",
        "oauth-2025-04-20",
        "fine-grained-tool-streaming-2025-05-14",
    )
    _TOOL_NAMES = (
        "Read",
        "Write",
        "Edit",
        "Bash",
        "Grep",
        "Glob",
        "AskUserQuestion",
        "EnterPlanMode",
        "ExitPlanMode",
        "KillShell",
        "NotebookEdit",
        "Skill",
        "Task",
        "TaskOutput",
        "TodoWrite",
        "WebFetch",
        "WebSearch",
    )
    _TOOL_LOOKUP = {name.lower(): name for name in _TOOL_NAMES}

    @classmethod
    def apply_identity_headers(
        cls, existing_headers: dict[str, str] | None
    ) -> dict[str, str]:
        out = dict(existing_headers or {})
        current = get_header_case_insensitive(out, "anthropic-beta")
        features = list(cls._BETA_FEATURES)
        if current:
            for item in current.split(","):
                feature = item.strip()
                if feature and feature not in features:
                    features.append(feature)
        set_header_case_insensitive(out, "anthropic-beta", ",".join(features))
        if get_header_case_insensitive(out, "user-agent") is None:
            set_header_case_insensitive(out, "user-agent", cls.SDK_USER_AGENT)
        if get_header_case_insensitive(out, "x-app") is None:
            set_header_case_insensitive(out, "x-app", cls.SDK_APP_ID)
        return out

    @classmethod
    def to_provider_tool_name(cls, name: str) -> str:
        return cls._TOOL_LOOKUP.get(name.lower(), name)

    @classmethod
    def from_provider_tool_name(
        cls, name: str, tools: list[object] | None = None
    ) -> str:
        lower_name = name.lower()
        for tool in tools or []:
            tool_name = (
                getattr(tool, "name", None)
                if not isinstance(tool, dict)
                else tool.get("name")
            )
            if isinstance(tool_name, str) and tool_name.lower() == lower_name:
                return tool_name
        return name
