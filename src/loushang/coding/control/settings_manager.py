from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal

from loushang.agent import ThinkingLevel
from loushang.coding.control.settings_store import (
    load_settings_patch,
    save_settings_patch,
)
from loushang.coding.control.types import (
    BranchSummarySettings,
    CompactionSettings,
    ControlConfig,
    DoubleEscapeAction,
    ExternalToolPolicy,
    HeadlessApprovalMode,
    ImageSettings,
    KeybindingValue,
    MarkdownSettings,
    MethodSettings,
    QueueMode,
    RetrySettings,
    StatusLineAutoValue,
    StatusLineControlSettings,
    StatusLineSeparator,
    StatusLineStyle,
    TerminalSettings,
    ThinkingBudgetMap,
    ToolSettings,
    TreeFilterMode,
    WarningSettings,
)
from loushang.coding.package import PackageSourceConfig
from loushang.coding.package.source import package_source_match_key
from loushang.coding.types import ModelSelection

SettingsListener = Callable[[ControlConfig], None]
SettingsScope = Literal["session", "global", "project"]
_UNSET = object()
_REMOVED_SETTING_MESSAGES = {
    "transport": "transport setting has been removed; use provider/contrib-specific configuration instead",
}


@dataclass(frozen=True)
class SettingsError:
    scope: SettingsScope
    message: str
    error: Exception


def _normalize_string_sequence(
    value: Sequence[str], field_name: str
) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence of strings, not a string")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} must only contain strings")
        normalized.append(item)
    return tuple(normalized)


def _normalize_package_source_sequence(
    value: object, field_name: str = "packages"
) -> tuple[PackageSourceConfig, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence")
    return tuple(_deserialize_package_source(item) for item in value)


def _deserialize_package_source(value: object) -> PackageSourceConfig:
    if isinstance(value, PackageSourceConfig):
        return value
    if isinstance(value, str):
        return PackageSourceConfig(source=value)
    if not isinstance(value, Mapping):
        raise TypeError("package source entries must be strings or objects")
    source = value.get("source")
    if not isinstance(source, str) or not source:
        raise TypeError("package source object must include a non-empty string source")
    return PackageSourceConfig(
        source=source,
        extensions=_optional_string_tuple(value.get("extensions"), "extensions"),
        skills=_optional_string_tuple(value.get("skills"), "skills"),
        prompts=_optional_string_tuple(value.get("prompts"), "prompts"),
        themes=_optional_string_tuple(value.get("themes"), "themes"),
    )


def _optional_string_tuple(value: object, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence of strings")
    return _normalize_string_sequence(value, field_name)


def _serialize_package_source(source: PackageSourceConfig) -> str | dict[str, object]:
    if not source.filtered:
        return source.source
    payload: dict[str, object] = {"source": source.source}
    if source.extensions is not None:
        payload["extensions"] = list(source.extensions)
    if source.skills is not None:
        payload["skills"] = list(source.skills)
    if source.prompts is not None:
        payload["prompts"] = list(source.prompts)
    if source.themes is not None:
        payload["themes"] = list(source.themes)
    return payload


def _serialize_model_selection(
    selection: ModelSelection | None,
) -> dict[str, str] | None:
    if selection is None:
        return None
    payload = {"provider": selection.provider, "model_id": selection.model_id}
    if selection.endpoint_id:
        payload["endpoint_id"] = selection.endpoint_id
    return payload


def _deserialize_model_selection(value: object) -> ModelSelection | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("default_model must be a JSON object or null")
    provider = value.get("provider")
    model_id = value.get("model_id")
    if not isinstance(provider, str) or not isinstance(model_id, str):
        raise TypeError(
            "default_model must include string provider and model_id values"
        )
    endpoint_id = value.get("endpoint_id") or value.get("endpointId")
    return ModelSelection(
        provider=provider,
        model_id=model_id,
        endpoint_id=endpoint_id if isinstance(endpoint_id, str) else None,
    )


def _deserialize_queue_mode(value: object, field_name: str) -> QueueMode:
    if value not in {"all", "one-at-a-time"}:
        raise ValueError(f"{field_name} must be 'all' or 'one-at-a-time'")
    return value


def _deserialize_double_escape_action(value: object) -> DoubleEscapeAction:
    if value not in {"fork", "tree", "none"}:
        raise ValueError("double_escape_action must be 'fork', 'tree', or 'none'")
    return value


def _deserialize_tree_filter_mode(value: object) -> TreeFilterMode:
    if value not in {"default", "no-tools", "user-only", "labeled-only", "all"}:
        raise ValueError(
            "tree_filter_mode must be 'default', 'no-tools', 'user-only', 'labeled-only', or 'all'"
        )
    return value


def _deserialize_external_tool_policy(value: object) -> ExternalToolPolicy:
    if value not in {"never", "auto", "required"}:
        raise ValueError("external_tool_policy must be 'never', 'auto', or 'required'")
    return value


def _deserialize_headless_approval_mode(value: object) -> HeadlessApprovalMode | None:
    if value is None:
        return None
    if value not in {"allow", "deny"}:
        raise ValueError("approval_mode must be 'allow', 'deny', or null")
    return value


def _deserialize_statusline_auto_value(
    value: object, field_name: str
) -> StatusLineAutoValue:
    if value not in {"auto", "true", "false"}:
        raise ValueError(f"{field_name} must be 'auto', 'true', or 'false'")
    return value


def _deserialize_statusline_separator(
    value: object, field_name: str
) -> StatusLineSeparator:
    if value not in {"pipe", "dot"}:
        raise ValueError(f"{field_name} must be 'pipe' or 'dot'")
    return value


def _deserialize_statusline_style(value: object, field_name: str) -> StatusLineStyle:
    if value not in {"codex-like", "muted", "plain"}:
        raise ValueError(f"{field_name} must be 'codex-like', 'muted', or 'plain'")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or null")
    return value


def _bool_value(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean")
    return value


def _string_tuple_or_none(value: object, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise TypeError(f"{field_name} must be a sequence of strings or null")
    return _normalize_string_sequence(value, field_name)


def _deserialize_keybindings(value: object) -> dict[str, KeybindingValue]:
    if not isinstance(value, Mapping):
        raise TypeError("keybindings must be a JSON object")
    normalized: dict[str, KeybindingValue] = {}
    for action, keys in value.items():
        if not isinstance(action, str):
            raise TypeError("keybinding action ids must be strings")
        if keys is None:
            normalized[action] = None
            continue
        if isinstance(keys, str):
            normalized[action] = keys
            continue
        normalized[action] = _normalize_string_sequence(keys, f"keybindings.{action}")
    return normalized


def _serialize_keybindings(value: Mapping[str, KeybindingValue]) -> dict[str, object]:
    serialized: dict[str, object] = {}
    for action, keys in value.items():
        serialized[action] = list(keys) if isinstance(keys, tuple) else keys
    return serialized


def _non_negative_small_int(
    value: object, field_name: str, *, upper_bound: int | None = None
) -> int:
    if not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    coerced = max(0, int(value))
    if upper_bound is not None:
        coerced = min(upper_bound, coerced)
    return coerced


def _bounded_int(
    value: object, field_name: str, *, lower_bound: int, upper_bound: int
) -> int:
    if not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    return max(lower_bound, min(upper_bound, int(value)))


def _thinking_budgets(value: object) -> ThinkingBudgetMap | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("thinking_budgets must be a JSON object or null")
    normalized: ThinkingBudgetMap = {}
    for key, item in value.items():
        if key not in {"minimal", "low", "medium", "high"}:
            raise ValueError(
                "thinking_budgets may only contain minimal, low, medium, or high"
            )
        if not isinstance(item, int):
            raise TypeError("thinking_budgets values must be integers")
        normalized[key] = item
    return normalized


def _serialize_settings_slice(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return _serialize_dataclass_slice(value)


def _serialize_tool_settings(value: object) -> dict[str, Any]:
    if isinstance(value, ToolSettings):
        return {
            "external_tool_policy": _deserialize_external_tool_policy(
                value.external_tool_policy
            ),
            "blocked_tools": list(value.blocked_tools),
            "ask_tools": list(value.ask_tools),
            "blocked_substrings": list(value.blocked_substrings),
            "ask_substrings": list(value.ask_substrings),
            "blocked_path_substrings": list(value.blocked_path_substrings),
            "ask_path_substrings": list(value.ask_path_substrings),
            "approval_mode": _deserialize_headless_approval_mode(value.approval_mode),
            "approval_reason": value.approval_reason,
        }
    if not isinstance(value, Mapping):
        raise TypeError("tools must be a JSON object")
    patch = dict(value)
    if "external_tool_policy" in patch:
        patch["external_tool_policy"] = _deserialize_external_tool_policy(
            patch["external_tool_policy"]
        )
    for key in (
        "blocked_tools",
        "ask_tools",
        "blocked_substrings",
        "ask_substrings",
        "blocked_path_substrings",
        "ask_path_substrings",
    ):
        if key in patch:
            patch[key] = list(_normalize_string_sequence(patch[key], key))
    if "approval_mode" in patch:
        patch["approval_mode"] = _deserialize_headless_approval_mode(
            patch["approval_mode"]
        )
    if "approval_reason" in patch:
        patch["approval_reason"] = _optional_string(
            patch["approval_reason"], "approval_reason"
        )
    return patch


def _serialize_statusline_settings(value: object) -> dict[str, Any]:
    if isinstance(value, StatusLineControlSettings):
        return _serialize_dataclass_slice(value)
    if not isinstance(value, Mapping):
        raise TypeError("statusline must be a JSON object")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        field_name = f"statusline.{key}"
        if key in {"enabled", "model", "workspace", "branch", "session", "runtime"}:
            normalized[key] = _bool_value(item, field_name)
        elif key in {"queue", "message"}:
            normalized[key] = _deserialize_statusline_auto_value(item, field_name)
        elif key == "separator":
            normalized[key] = _deserialize_statusline_separator(item, field_name)
        elif key == "style":
            normalized[key] = _deserialize_statusline_style(item, field_name)
        else:
            raise ValueError(f"Unknown statusline setting: {field_name}")
    return normalized


def _serialize_dataclass_slice(value: object) -> dict[str, Any]:
    return dict(asdict(value))


def _diff_dataclass_slice(value: object, default_value: object) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    for key, current_value in asdict(value).items():
        if current_value != getattr(default_value, key):
            diff[key] = current_value
    return diff


def _drop_removed_settings(
    patch: Mapping[str, Any],
    *,
    scope: SettingsScope,
    errors: list[SettingsError] | None,
) -> dict[str, Any]:
    normalized = dict(patch)
    for key, message in _REMOVED_SETTING_MESSAGES.items():
        if key not in normalized:
            continue
        normalized.pop(key)
        if errors is not None:
            error = ValueError(message)
            errors.append(SettingsError(scope=scope, message=message, error=error))
    return normalized


def _control_config_to_patch(config: ControlConfig) -> dict[str, Any]:
    defaults = ControlConfig()
    patch: dict[str, Any] = {}
    if config.default_model != defaults.default_model:
        patch["default_model"] = _serialize_model_selection(config.default_model)
    if config.thinking_level != defaults.thinking_level:
        patch["thinking_level"] = config.thinking_level
    if config.steering_mode != defaults.steering_mode:
        patch["steering_mode"] = config.steering_mode
    if config.follow_up_mode != defaults.follow_up_mode:
        patch["follow_up_mode"] = config.follow_up_mode
    if config.theme != defaults.theme:
        patch["theme"] = config.theme
    if config.system_prompt != defaults.system_prompt:
        patch["system_prompt"] = config.system_prompt
    if config.hide_thinking_block != defaults.hide_thinking_block:
        patch["hide_thinking_block"] = config.hide_thinking_block
    if config.shell_path != defaults.shell_path:
        patch["shell_path"] = config.shell_path
    if config.quiet_startup != defaults.quiet_startup:
        patch["quiet_startup"] = config.quiet_startup
    if config.shell_command_prefix != defaults.shell_command_prefix:
        patch["shell_command_prefix"] = config.shell_command_prefix
    if config.npm_command != defaults.npm_command:
        patch["npm_command"] = (
            list(config.npm_command) if config.npm_command is not None else None
        )
    if config.collapse_changelog != defaults.collapse_changelog:
        patch["collapse_changelog"] = config.collapse_changelog
    if config.enable_install_telemetry != defaults.enable_install_telemetry:
        patch["enable_install_telemetry"] = config.enable_install_telemetry
    if config.enable_skill_commands != defaults.enable_skill_commands:
        patch["enable_skill_commands"] = config.enable_skill_commands
    if config.enabled_models != defaults.enabled_models:
        patch["enabled_models"] = (
            list(config.enabled_models) if config.enabled_models is not None else None
        )
    if config.double_escape_action != defaults.double_escape_action:
        patch["double_escape_action"] = config.double_escape_action
    if config.tree_filter_mode != defaults.tree_filter_mode:
        patch["tree_filter_mode"] = config.tree_filter_mode
    if config.show_hardware_cursor != defaults.show_hardware_cursor:
        patch["show_hardware_cursor"] = config.show_hardware_cursor
    if config.editor_padding_x != defaults.editor_padding_x:
        patch["editor_padding_x"] = config.editor_padding_x
    if config.autocomplete_max_visible != defaults.autocomplete_max_visible:
        patch["autocomplete_max_visible"] = config.autocomplete_max_visible
    if config.keybindings != defaults.keybindings:
        patch["keybindings"] = _serialize_keybindings(config.keybindings)
    if config.thinking_budgets != defaults.thinking_budgets:
        patch["thinking_budgets"] = config.thinking_budgets
    compaction_patch = _diff_dataclass_slice(config.compaction, defaults.compaction)
    if compaction_patch:
        patch["compaction"] = compaction_patch
    branch_summary_patch = _diff_dataclass_slice(
        config.branch_summary, defaults.branch_summary
    )
    if branch_summary_patch:
        patch["branch_summary"] = branch_summary_patch
    retry_patch = _diff_dataclass_slice(config.retry, defaults.retry)
    if retry_patch:
        patch["retry"] = retry_patch
    images_patch = _diff_dataclass_slice(config.images, defaults.images)
    if images_patch:
        patch["images"] = images_patch
    terminal_patch = _diff_dataclass_slice(config.terminal, defaults.terminal)
    if terminal_patch:
        patch["terminal"] = terminal_patch
    markdown_patch = _diff_dataclass_slice(config.markdown, defaults.markdown)
    if markdown_patch:
        patch["markdown"] = markdown_patch
    warnings_patch = _diff_dataclass_slice(config.warnings, defaults.warnings)
    if warnings_patch:
        patch["warnings"] = warnings_patch
    method_patch = _diff_dataclass_slice(config.method, defaults.method)
    if method_patch:
        patch["method"] = method_patch
    tools_patch = _diff_dataclass_slice(config.tools, defaults.tools)
    if tools_patch:
        patch["tools"] = tools_patch
    statusline_patch = _diff_dataclass_slice(config.statusline, defaults.statusline)
    if statusline_patch:
        patch["statusline"] = statusline_patch
    if config.session_dir != defaults.session_dir:
        patch["session_dir"] = config.session_dir
    if config.resource_roots != defaults.resource_roots:
        patch["resource_roots"] = list(config.resource_roots)
    if config.package_roots != defaults.package_roots:
        patch["package_roots"] = list(config.package_roots)
    if config.package_sources != defaults.package_sources:
        patch["package_sources"] = [
            _serialize_package_source(source) for source in config.package_sources
        ]
    if config.plugin_sources != defaults.plugin_sources:
        patch["plugin_sources"] = list(config.plugin_sources)
    if config.disabled_skills != defaults.disabled_skills:
        patch["disabled_skills"] = list(config.disabled_skills)
    if config.disabled_plugins != defaults.disabled_plugins:
        patch["disabled_plugins"] = list(config.disabled_plugins)
    return patch


def _merge_patch(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = {**existing, **value}
            continue
        merged[key] = value
    return merged


def _apply_dataclass_patch(current: object, patch_value: object, field_name: str):
    if not isinstance(patch_value, Mapping):
        raise TypeError(f"{field_name} must be a JSON object")
    return replace(current, **dict(patch_value))


def _apply_tool_settings_patch(
    current: ToolSettings, patch_value: object
) -> ToolSettings:
    if not isinstance(patch_value, Mapping):
        raise TypeError("tools must be a JSON object")
    next_settings = current
    if "external_tool_policy" in patch_value:
        next_settings = replace(
            next_settings,
            external_tool_policy=_deserialize_external_tool_policy(
                patch_value["external_tool_policy"]
            ),
        )
    for key in (
        "blocked_tools",
        "ask_tools",
        "blocked_substrings",
        "ask_substrings",
        "blocked_path_substrings",
        "ask_path_substrings",
    ):
        if key in patch_value:
            next_settings = replace(
                next_settings,
                **{key: _normalize_string_sequence(patch_value[key], key)},
            )
    if "approval_mode" in patch_value:
        next_settings = replace(
            next_settings,
            approval_mode=_deserialize_headless_approval_mode(
                patch_value["approval_mode"]
            ),
        )
    if "approval_reason" in patch_value:
        next_settings = replace(
            next_settings,
            approval_reason=_optional_string(
                patch_value["approval_reason"], "approval_reason"
            ),
        )
    return next_settings


def _apply_statusline_settings_patch(
    current: StatusLineControlSettings,
    patch_value: object,
) -> StatusLineControlSettings:
    patch = _serialize_statusline_settings(patch_value)
    return replace(current, **patch)


def _apply_patch(
    config: ControlConfig,
    patch: Mapping[str, Any],
    *,
    scope: SettingsScope | None = None,
    errors: list[SettingsError] | None = None,
) -> ControlConfig:
    if scope is not None:
        patch = _drop_removed_settings(patch, scope=scope, errors=errors)
    next_config = config
    if "default_model" in patch:
        next_config = replace(
            next_config,
            default_model=_deserialize_model_selection(patch["default_model"]),
        )
    if "thinking_level" in patch:
        next_config = replace(next_config, thinking_level=patch["thinking_level"])
    if "steering_mode" in patch:
        next_config = replace(
            next_config,
            steering_mode=_deserialize_queue_mode(
                patch["steering_mode"], "steering_mode"
            ),
        )
    if "follow_up_mode" in patch:
        next_config = replace(
            next_config,
            follow_up_mode=_deserialize_queue_mode(
                patch["follow_up_mode"], "follow_up_mode"
            ),
        )
    if "theme" in patch:
        next_config = replace(
            next_config, theme=_optional_string(patch["theme"], "theme")
        )
    if "system_prompt" in patch:
        next_config = replace(next_config, system_prompt=patch["system_prompt"])
    if "hide_thinking_block" in patch:
        next_config = replace(
            next_config,
            hide_thinking_block=_bool_value(
                patch["hide_thinking_block"], "hide_thinking_block"
            ),
        )
    if "shell_path" in patch:
        next_config = replace(
            next_config, shell_path=_optional_string(patch["shell_path"], "shell_path")
        )
    if "quiet_startup" in patch:
        next_config = replace(
            next_config,
            quiet_startup=_bool_value(patch["quiet_startup"], "quiet_startup"),
        )
    if "shell_command_prefix" in patch:
        next_config = replace(
            next_config,
            shell_command_prefix=_optional_string(
                patch["shell_command_prefix"], "shell_command_prefix"
            ),
        )
    if "npm_command" in patch:
        next_config = replace(
            next_config,
            npm_command=_string_tuple_or_none(patch["npm_command"], "npm_command"),
        )
    if "collapse_changelog" in patch:
        next_config = replace(
            next_config,
            collapse_changelog=_bool_value(
                patch["collapse_changelog"], "collapse_changelog"
            ),
        )
    if "enable_install_telemetry" in patch:
        next_config = replace(
            next_config,
            enable_install_telemetry=_bool_value(
                patch["enable_install_telemetry"], "enable_install_telemetry"
            ),
        )
    if "enable_skill_commands" in patch:
        next_config = replace(
            next_config,
            enable_skill_commands=_bool_value(
                patch["enable_skill_commands"], "enable_skill_commands"
            ),
        )
    if "enabled_models" in patch:
        next_config = replace(
            next_config,
            enabled_models=_string_tuple_or_none(
                patch["enabled_models"], "enabled_models"
            ),
        )
    if "double_escape_action" in patch:
        next_config = replace(
            next_config,
            double_escape_action=_deserialize_double_escape_action(
                patch["double_escape_action"]
            ),
        )
    if "tree_filter_mode" in patch:
        next_config = replace(
            next_config,
            tree_filter_mode=_deserialize_tree_filter_mode(patch["tree_filter_mode"]),
        )
    if "show_hardware_cursor" in patch:
        next_config = replace(
            next_config,
            show_hardware_cursor=_bool_value(
                patch["show_hardware_cursor"], "show_hardware_cursor"
            ),
        )
    if "editor_padding_x" in patch:
        next_config = replace(
            next_config,
            editor_padding_x=_non_negative_small_int(
                patch["editor_padding_x"], "editor_padding_x", upper_bound=3
            ),
        )
    if "autocomplete_max_visible" in patch:
        next_config = replace(
            next_config,
            autocomplete_max_visible=_bounded_int(
                patch["autocomplete_max_visible"],
                "autocomplete_max_visible",
                lower_bound=3,
                upper_bound=20,
            ),
        )
    if "keybindings" in patch:
        next_config = replace(
            next_config,
            keybindings={
                **next_config.keybindings,
                **_deserialize_keybindings(patch["keybindings"]),
            },
        )
    if "thinking_budgets" in patch:
        next_config = replace(
            next_config, thinking_budgets=_thinking_budgets(patch["thinking_budgets"])
        )
    if "compaction" in patch:
        next_config = replace(
            next_config,
            compaction=_apply_dataclass_patch(
                next_config.compaction, patch["compaction"], "compaction"
            ),
        )
    if "branch_summary" in patch:
        next_config = replace(
            next_config,
            branch_summary=_apply_dataclass_patch(
                next_config.branch_summary,
                patch["branch_summary"],
                "branch_summary",
            ),
        )
    if "retry" in patch:
        next_config = replace(
            next_config,
            retry=_apply_dataclass_patch(next_config.retry, patch["retry"], "retry"),
        )
    if "images" in patch:
        next_config = replace(
            next_config,
            images=_apply_dataclass_patch(
                next_config.images, patch["images"], "images"
            ),
        )
    if "terminal" in patch:
        next_config = replace(
            next_config,
            terminal=_apply_dataclass_patch(
                next_config.terminal, patch["terminal"], "terminal"
            ),
        )
    if "markdown" in patch:
        next_config = replace(
            next_config,
            markdown=_apply_dataclass_patch(
                next_config.markdown, patch["markdown"], "markdown"
            ),
        )
    if "warnings" in patch:
        next_config = replace(
            next_config,
            warnings=_apply_dataclass_patch(
                next_config.warnings, patch["warnings"], "warnings"
            ),
        )
    if "method" in patch:
        next_config = replace(
            next_config,
            method=_apply_dataclass_patch(
                next_config.method, patch["method"], "method"
            ),
        )
    if "tools" in patch:
        next_config = replace(
            next_config,
            tools=_apply_tool_settings_patch(next_config.tools, patch["tools"]),
        )
    if "statusline" in patch:
        try:
            next_config = replace(
                next_config,
                statusline=_apply_statusline_settings_patch(
                    next_config.statusline, patch["statusline"]
                ),
            )
        except Exception as exc:
            if errors is None or scope is None:
                raise
            errors.append(SettingsError(scope=scope, message=str(exc), error=exc))
    if "session_dir" in patch:
        session_dir = patch["session_dir"]
        if session_dir is not None and not isinstance(session_dir, str):
            raise TypeError("session_dir must be a string or null")
        next_config = replace(next_config, session_dir=session_dir)
    if "resource_roots" in patch:
        resource_roots = patch["resource_roots"]
        if not isinstance(resource_roots, Sequence):
            raise TypeError("resource_roots must be a sequence of strings")
        next_config = replace(
            next_config,
            resource_roots=_normalize_string_sequence(resource_roots, "resource_roots"),
        )
    if "package_roots" in patch:
        package_roots = patch["package_roots"]
        if not isinstance(package_roots, Sequence):
            raise TypeError("package_roots must be a sequence of strings")
        next_config = replace(
            next_config,
            package_roots=_normalize_string_sequence(package_roots, "package_roots"),
        )
    packages_patch = patch.get("packages", patch.get("package_sources", _UNSET))
    if packages_patch is not _UNSET:
        next_config = replace(
            next_config,
            package_sources=_normalize_package_source_sequence(packages_patch),
        )
    if "plugin_sources" in patch:
        plugin_sources = patch["plugin_sources"]
        if not isinstance(plugin_sources, Sequence):
            raise TypeError("plugin_sources must be a sequence of strings")
        next_config = replace(
            next_config,
            plugin_sources=_normalize_string_sequence(plugin_sources, "plugin_sources"),
        )
    if "disabled_skills" in patch:
        disabled_skills = patch["disabled_skills"]
        if not isinstance(disabled_skills, Sequence):
            raise TypeError("disabled_skills must be a sequence of strings")
        next_config = replace(
            next_config,
            disabled_skills=_normalize_string_sequence(
                disabled_skills, "disabled_skills"
            ),
        )
    if "disabled_plugins" in patch:
        disabled_plugins = patch["disabled_plugins"]
        if not isinstance(disabled_plugins, Sequence):
            raise TypeError("disabled_plugins must be a sequence of strings")
        next_config = replace(
            next_config,
            disabled_plugins=_normalize_string_sequence(
                disabled_plugins, "disabled_plugins"
            ),
        )
    return next_config


class SettingsManager:
    def __init__(
        self,
        initial: ControlConfig | None = None,
        *,
        global_settings_path: str | Path | None = None,
        project_settings_path: str | Path | None = None,
    ) -> None:
        self._global_settings_path = (
            Path(global_settings_path) if global_settings_path is not None else None
        )
        self._project_settings_path = (
            Path(project_settings_path) if project_settings_path is not None else None
        )
        self._errors: list[SettingsError] = []
        self._global_patch = self._load_patch(
            "global", self._global_settings_path, previous={}
        )
        self._project_patch = self._load_patch(
            "project", self._project_settings_path, previous={}
        )
        self._session_patch = (
            _control_config_to_patch(initial) if initial is not None else {}
        )
        self._listeners: list[SettingsListener] = []
        self._settings = self._compose_settings()

    def reload(self) -> None:
        self._global_patch = self._load_patch(
            "global", self._global_settings_path, previous=self._global_patch
        )
        self._project_patch = self._load_patch(
            "project", self._project_settings_path, previous=self._project_patch
        )
        self._settings = self._compose_settings()
        self._notify()

    async def flush(self) -> None:
        return None

    def apply_overrides(self, overrides: Mapping[str, Any] | ControlConfig) -> None:
        patch = (
            _control_config_to_patch(overrides)
            if isinstance(overrides, ControlConfig)
            else dict(overrides)
        )
        patch = _drop_removed_settings(patch, scope="session", errors=self._errors)
        self._session_patch = _merge_patch(self._session_patch, patch)
        self._settings = self._compose_settings()
        self._notify()

    def drain_errors(self) -> list[SettingsError]:
        errors = list(self._errors)
        self._errors.clear()
        return errors

    @property
    def global_base_dir(self) -> Path | None:
        return (
            self._global_settings_path.parent
            if self._global_settings_path is not None
            else None
        )

    @property
    def project_base_dir(self) -> Path | None:
        return (
            self._project_settings_path.parent
            if self._project_settings_path is not None
            else None
        )

    def update_settings(
        self,
        *,
        scope: SettingsScope = "session",
        default_model: ModelSelection | None | object = _UNSET,
        thinking_level: ThinkingLevel | object = _UNSET,
        steering_mode: QueueMode | object = _UNSET,
        follow_up_mode: QueueMode | object = _UNSET,
        theme: str | None | object = _UNSET,
        system_prompt: str | object = _UNSET,
        hide_thinking_block: bool | object = _UNSET,
        shell_path: str | None | object = _UNSET,
        quiet_startup: bool | object = _UNSET,
        shell_command_prefix: str | None | object = _UNSET,
        npm_command: Sequence[str] | None | object = _UNSET,
        collapse_changelog: bool | object = _UNSET,
        enable_install_telemetry: bool | object = _UNSET,
        enable_skill_commands: bool | object = _UNSET,
        enabled_models: Sequence[str] | None | object = _UNSET,
        double_escape_action: DoubleEscapeAction | object = _UNSET,
        tree_filter_mode: TreeFilterMode | object = _UNSET,
        show_hardware_cursor: bool | object = _UNSET,
        editor_padding_x: float | int | object = _UNSET,
        autocomplete_max_visible: float | int | object = _UNSET,
        keybindings: Mapping[str, object] | object = _UNSET,
        thinking_budgets: ThinkingBudgetMap | None | object = _UNSET,
        compaction: CompactionSettings | object = _UNSET,
        branch_summary: BranchSummarySettings | object = _UNSET,
        retry: RetrySettings | object = _UNSET,
        images: ImageSettings | object = _UNSET,
        terminal: TerminalSettings | object = _UNSET,
        markdown: MarkdownSettings | object = _UNSET,
        warnings: WarningSettings | object = _UNSET,
        method: MethodSettings | Mapping[str, object] | object = _UNSET,
        tools: ToolSettings | Mapping[str, object] | object = _UNSET,
        statusline: StatusLineControlSettings | Mapping[str, object] | object = _UNSET,
        session_dir: str | None | object = _UNSET,
        resource_roots: Iterable[str] | object = _UNSET,
        package_roots: Iterable[str] | object = _UNSET,
        package_sources: Iterable[PackageSourceConfig | str | Mapping[str, object]]
        | object = _UNSET,
        plugin_sources: Iterable[str] | object = _UNSET,
        disabled_skills: Iterable[str] | object = _UNSET,
        disabled_plugins: Iterable[str] | object = _UNSET,
    ) -> None:
        patch: dict[str, Any] = {}
        if default_model is not _UNSET:
            patch["default_model"] = _serialize_model_selection(default_model)
        if thinking_level is not _UNSET:
            patch["thinking_level"] = thinking_level
        if steering_mode is not _UNSET:
            patch["steering_mode"] = _deserialize_queue_mode(
                steering_mode, "steering_mode"
            )
        if follow_up_mode is not _UNSET:
            patch["follow_up_mode"] = _deserialize_queue_mode(
                follow_up_mode, "follow_up_mode"
            )
        if theme is not _UNSET:
            patch["theme"] = _optional_string(theme, "theme")
        if system_prompt is not _UNSET:
            patch["system_prompt"] = system_prompt
        if hide_thinking_block is not _UNSET:
            patch["hide_thinking_block"] = _bool_value(
                hide_thinking_block, "hide_thinking_block"
            )
        if shell_path is not _UNSET:
            patch["shell_path"] = _optional_string(shell_path, "shell_path")
        if quiet_startup is not _UNSET:
            patch["quiet_startup"] = _bool_value(quiet_startup, "quiet_startup")
        if shell_command_prefix is not _UNSET:
            patch["shell_command_prefix"] = _optional_string(
                shell_command_prefix, "shell_command_prefix"
            )
        if npm_command is not _UNSET:
            normalized_npm_command = _string_tuple_or_none(npm_command, "npm_command")
            patch["npm_command"] = (
                list(normalized_npm_command)
                if normalized_npm_command is not None
                else None
            )
        if collapse_changelog is not _UNSET:
            patch["collapse_changelog"] = _bool_value(
                collapse_changelog, "collapse_changelog"
            )
        if enable_install_telemetry is not _UNSET:
            patch["enable_install_telemetry"] = _bool_value(
                enable_install_telemetry, "enable_install_telemetry"
            )
        if enable_skill_commands is not _UNSET:
            patch["enable_skill_commands"] = _bool_value(
                enable_skill_commands, "enable_skill_commands"
            )
        if enabled_models is not _UNSET:
            normalized_enabled_models = _string_tuple_or_none(
                enabled_models, "enabled_models"
            )
            patch["enabled_models"] = (
                list(normalized_enabled_models)
                if normalized_enabled_models is not None
                else None
            )
        if double_escape_action is not _UNSET:
            patch["double_escape_action"] = _deserialize_double_escape_action(
                double_escape_action
            )
        if tree_filter_mode is not _UNSET:
            patch["tree_filter_mode"] = _deserialize_tree_filter_mode(tree_filter_mode)
        if show_hardware_cursor is not _UNSET:
            patch["show_hardware_cursor"] = _bool_value(
                show_hardware_cursor, "show_hardware_cursor"
            )
        if editor_padding_x is not _UNSET:
            patch["editor_padding_x"] = _non_negative_small_int(
                editor_padding_x, "editor_padding_x", upper_bound=3
            )
        if autocomplete_max_visible is not _UNSET:
            patch["autocomplete_max_visible"] = _bounded_int(
                autocomplete_max_visible,
                "autocomplete_max_visible",
                lower_bound=3,
                upper_bound=20,
            )
        if keybindings is not _UNSET:
            patch["keybindings"] = _serialize_keybindings(
                _deserialize_keybindings(keybindings)
            )
        if thinking_budgets is not _UNSET:
            patch["thinking_budgets"] = _thinking_budgets(thinking_budgets)
        if compaction is not _UNSET:
            patch["compaction"] = _serialize_settings_slice(compaction)
        if branch_summary is not _UNSET:
            patch["branch_summary"] = _serialize_settings_slice(branch_summary)
        if retry is not _UNSET:
            patch["retry"] = _serialize_settings_slice(retry)
        if images is not _UNSET:
            patch["images"] = _serialize_settings_slice(images)
        if terminal is not _UNSET:
            patch["terminal"] = _serialize_settings_slice(terminal)
        if markdown is not _UNSET:
            patch["markdown"] = _serialize_settings_slice(markdown)
        if warnings is not _UNSET:
            patch["warnings"] = _serialize_settings_slice(warnings)
        if method is not _UNSET:
            patch["method"] = _serialize_settings_slice(method)
        if tools is not _UNSET:
            patch["tools"] = _serialize_tool_settings(tools)
        if statusline is not _UNSET:
            patch["statusline"] = _serialize_statusline_settings(statusline)
        if session_dir is not _UNSET:
            patch["session_dir"] = session_dir
        if resource_roots is not _UNSET:
            patch["resource_roots"] = list(
                _normalize_string_sequence(resource_roots, "resource_roots")
            )
        if package_roots is not _UNSET:
            patch["package_roots"] = list(
                _normalize_string_sequence(package_roots, "package_roots")
            )
        if package_sources is not _UNSET:
            patch["packages"] = [
                _serialize_package_source(source)
                for source in _normalize_package_source_sequence(
                    list(package_sources), "package_sources"
                )
            ]
        if plugin_sources is not _UNSET:
            patch["plugin_sources"] = list(
                _normalize_string_sequence(plugin_sources, "plugin_sources")
            )
        if disabled_skills is not _UNSET:
            patch["disabled_skills"] = list(
                _normalize_string_sequence(disabled_skills, "disabled_skills")
            )
        if disabled_plugins is not _UNSET:
            patch["disabled_plugins"] = list(
                _normalize_string_sequence(disabled_plugins, "disabled_plugins")
            )

        if scope == "global":
            self._global_patch = _merge_patch(self._global_patch, patch)
            save_settings_patch(self._global_settings_path, self._global_patch)
        elif scope == "project":
            self._project_patch = _merge_patch(self._project_patch, patch)
            save_settings_patch(self._project_settings_path, self._project_patch)
        else:
            self._session_patch = _merge_patch(self._session_patch, patch)

        self._settings = self._compose_settings()
        self._notify()

    def set_default_model(
        self, selection: ModelSelection | None, *, scope: SettingsScope = "session"
    ) -> None:
        self.update_settings(scope=scope, default_model=selection)

    def set_steering_mode(
        self, mode: QueueMode, *, scope: SettingsScope = "session"
    ) -> None:
        self.update_settings(scope=scope, steering_mode=mode)

    def set_follow_up_mode(
        self, mode: QueueMode, *, scope: SettingsScope = "session"
    ) -> None:
        self.update_settings(scope=scope, follow_up_mode=mode)

    def get_theme(self) -> str | None:
        return self._settings.theme

    def set_theme(self, theme: str | None, *, scope: SettingsScope = "global") -> None:
        self.update_settings(scope=scope, theme=theme)

    def get_hide_thinking_block(self) -> bool:
        return self._settings.hide_thinking_block

    def set_hide_thinking_block(
        self, hide: bool, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, hide_thinking_block=hide)

    def get_shell_path(self) -> str | None:
        return self._settings.shell_path

    def set_shell_path(
        self, path: str | None, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, shell_path=path)

    def get_quiet_startup(self) -> bool:
        return self._settings.quiet_startup

    def set_quiet_startup(
        self, quiet: bool, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, quiet_startup=quiet)

    def get_shell_command_prefix(self) -> str | None:
        return self._settings.shell_command_prefix

    def set_shell_command_prefix(
        self, prefix: str | None, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, shell_command_prefix=prefix)

    def get_npm_command(self) -> list[str] | None:
        return (
            list(self._settings.npm_command)
            if self._settings.npm_command is not None
            else None
        )

    def set_npm_command(
        self, command: Sequence[str] | None, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, npm_command=command)

    def get_collapse_changelog(self) -> bool:
        return self._settings.collapse_changelog

    def set_collapse_changelog(
        self, collapse: bool, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, collapse_changelog=collapse)

    def get_enable_install_telemetry(self) -> bool:
        return self._settings.enable_install_telemetry

    def set_enable_install_telemetry(
        self, enabled: bool, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, enable_install_telemetry=enabled)

    def get_enable_skill_commands(self) -> bool:
        return self._settings.enable_skill_commands

    def set_enable_skill_commands(
        self, enabled: bool, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, enable_skill_commands=enabled)

    def get_enabled_models(self) -> list[str] | None:
        return (
            list(self._settings.enabled_models)
            if self._settings.enabled_models is not None
            else None
        )

    def set_enabled_models(
        self, patterns: Sequence[str] | None, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, enabled_models=patterns)

    def get_double_escape_action(self) -> DoubleEscapeAction:
        return self._settings.double_escape_action

    def set_double_escape_action(
        self, action: DoubleEscapeAction, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, double_escape_action=action)

    def get_tree_filter_mode(self) -> TreeFilterMode:
        return self._settings.tree_filter_mode

    def set_tree_filter_mode(
        self, mode: TreeFilterMode, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, tree_filter_mode=mode)

    def get_show_hardware_cursor(self) -> bool:
        return self._settings.show_hardware_cursor

    def set_show_hardware_cursor(
        self, enabled: bool, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, show_hardware_cursor=enabled)

    def get_editor_padding_x(self) -> int:
        return self._settings.editor_padding_x

    def set_editor_padding_x(
        self, padding: float | int, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, editor_padding_x=padding)

    def get_autocomplete_max_visible(self) -> int:
        return self._settings.autocomplete_max_visible

    def set_autocomplete_max_visible(
        self, max_visible: float | int, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, autocomplete_max_visible=max_visible)

    def get_keybindings(self) -> dict[str, KeybindingValue]:
        return dict(self._settings.keybindings)

    def set_keybindings(
        self, keybindings: Mapping[str, object], *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, keybindings=keybindings)

    def get_thinking_budgets(self) -> ThinkingBudgetMap | None:
        return deepcopy(self._settings.thinking_budgets)

    def get_compaction_settings(self) -> CompactionSettings:
        return self._settings.compaction

    def get_branch_summary_settings(self) -> BranchSummarySettings:
        return self._settings.branch_summary

    def get_branch_summary_skip_prompt(self) -> bool:
        return self._settings.branch_summary.skip_prompt

    def get_provider_retry_settings(self) -> dict[str, int | None]:
        retry = self._settings.retry
        return {
            "timeout_ms": retry.provider_timeout_ms,
            "max_retries": retry.provider_max_retries,
            "max_retry_delay_ms": retry.provider_max_retry_delay_ms,
        }

    def get_show_images(self) -> bool:
        return self._settings.terminal.show_images

    def set_show_images(self, show: bool, *, scope: SettingsScope = "global") -> None:
        self.update_settings(
            scope=scope, terminal=replace(self._settings.terminal, show_images=show)
        )

    def get_image_width_cells(self) -> int:
        return max(1, int(self._settings.terminal.image_width_cells))

    def set_image_width_cells(
        self, width: float | int, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(
            scope=scope,
            terminal=replace(
                self._settings.terminal, image_width_cells=max(1, int(width))
            ),
        )

    def get_clear_on_shrink(self) -> bool:
        return self._settings.terminal.clear_on_shrink

    def set_clear_on_shrink(
        self, enabled: bool, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(
            scope=scope,
            terminal=replace(self._settings.terminal, clear_on_shrink=enabled),
        )

    def get_show_terminal_progress(self) -> bool:
        return self._settings.terminal.show_terminal_progress

    def set_show_terminal_progress(
        self, enabled: bool, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(
            scope=scope,
            terminal=replace(self._settings.terminal, show_terminal_progress=enabled),
        )

    def get_image_auto_resize(self) -> bool:
        return self._settings.images.auto_resize

    def set_image_auto_resize(
        self, enabled: bool, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(
            scope=scope, images=replace(self._settings.images, auto_resize=enabled)
        )

    def get_block_images(self) -> bool:
        return self._settings.images.block_images

    def set_block_images(
        self, enabled: bool, *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(
            scope=scope, images=replace(self._settings.images, block_images=enabled)
        )

    def get_image_settings(self) -> ImageSettings:
        return self._settings.images

    def get_terminal_settings(self) -> TerminalSettings:
        return self._settings.terminal

    def get_markdown_settings(self) -> MarkdownSettings:
        return self._settings.markdown

    def get_code_block_indent(self) -> str:
        return self._settings.markdown.code_block_indent

    def get_warnings(self) -> WarningSettings:
        return self._settings.warnings

    def get_method_settings(self) -> MethodSettings:
        return self._settings.method

    def set_method_settings(
        self,
        settings: MethodSettings | Mapping[str, object],
        *,
        scope: SettingsScope = "global",
    ) -> None:
        self.update_settings(scope=scope, method=settings)

    def get_tool_settings(self) -> ToolSettings:
        return self._settings.tools

    def get_statusline_settings(self) -> StatusLineControlSettings:
        return self._settings.statusline

    def set_statusline_settings(
        self,
        settings: StatusLineControlSettings | Mapping[str, object],
        *,
        scope: SettingsScope = "global",
    ) -> None:
        self.update_settings(scope=scope, statusline=settings)

    def get_external_tool_policy(self) -> ExternalToolPolicy:
        return self._settings.tools.external_tool_policy

    def set_external_tool_policy(
        self,
        policy: ExternalToolPolicy,
        *,
        scope: SettingsScope = "global",
    ) -> None:
        self.update_settings(
            scope=scope,
            tools=replace(
                self._settings.tools,
                external_tool_policy=_deserialize_external_tool_policy(policy),
            ),
        )

    def get_retry_settings(self) -> RetrySettings:
        return self._settings.retry

    def get_retry_enabled(self) -> bool:
        return self._settings.retry.enabled

    def set_retry_enabled(
        self, enabled: bool, *, scope: SettingsScope = "session"
    ) -> None:
        self.update_settings(
            scope=scope, retry=replace(self._settings.retry, enabled=enabled)
        )

    def get_resource_roots(self) -> list[str]:
        return list(self._settings.resource_roots)

    def set_resource_roots(
        self, roots: Iterable[str], *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, resource_roots=roots)

    def get_package_roots(self) -> list[str]:
        return list(self._settings.package_roots)

    def set_package_roots(
        self, roots: Iterable[str], *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, package_roots=roots)

    def get_package_sources(self) -> list[PackageSourceConfig]:
        return list(self._settings.package_sources)

    def set_package_sources(
        self,
        sources: Iterable[PackageSourceConfig | str | Mapping[str, object]],
        *,
        scope: SettingsScope = "global",
    ) -> None:
        self.update_settings(scope=scope, package_sources=sources)

    def add_package_source(
        self,
        source: PackageSourceConfig | str | Mapping[str, object],
        *,
        scope: SettingsScope = "project",
    ) -> bool:
        candidate = _deserialize_package_source(source)
        current_sources = self._settings.package_sources
        next_sources = _with_package_source(current_sources, candidate)
        self.update_settings(scope=scope, package_sources=next_sources)
        return next_sources != current_sources

    def remove_package_source(
        self, source: str, *, scope: SettingsScope = "project"
    ) -> bool:
        current_sources = self._settings.package_sources
        next_sources = _without_package_source(current_sources, source)
        self.update_settings(scope=scope, package_sources=next_sources)
        return next_sources != current_sources

    def get_plugin_sources(self) -> list[str]:
        return list(self._settings.plugin_sources)

    def set_plugin_sources(
        self, sources: Iterable[str], *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, plugin_sources=sources)

    def get_disabled_skills(self) -> list[str]:
        return list(self._settings.disabled_skills)

    def set_disabled_skills(
        self, names: Iterable[str], *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, disabled_skills=names)

    def get_disabled_plugins(self) -> list[str]:
        return list(self._settings.disabled_plugins)

    def set_disabled_plugins(
        self, names: Iterable[str], *, scope: SettingsScope = "global"
    ) -> None:
        self.update_settings(scope=scope, disabled_plugins=names)

    def add_plugin_source(
        self, source: str, *, scope: SettingsScope = "project"
    ) -> bool:
        current_sources = self._settings.plugin_sources
        next_sources = _with_name(current_sources, source)
        self.update_settings(scope=scope, plugin_sources=next_sources)
        return next_sources != current_sources

    def remove_plugin_source(
        self, source: str, *, scope: SettingsScope = "project"
    ) -> bool:
        current_sources = self._settings.plugin_sources
        next_sources = _without_name(current_sources, source)
        self.update_settings(scope=scope, plugin_sources=next_sources)
        return next_sources != current_sources

    def enable_skill(self, name: str, *, scope: SettingsScope = "project") -> None:
        self.update_settings(
            scope=scope,
            disabled_skills=_without_name(self._settings.disabled_skills, name),
        )

    def disable_skill(self, name: str, *, scope: SettingsScope = "project") -> None:
        self.update_settings(
            scope=scope,
            disabled_skills=_with_name(self._settings.disabled_skills, name),
        )

    def enable_plugin(self, name: str, *, scope: SettingsScope = "project") -> None:
        self.update_settings(
            scope=scope,
            disabled_plugins=_without_name(self._settings.disabled_plugins, name),
        )

    def disable_plugin(self, name: str, *, scope: SettingsScope = "project") -> None:
        self.update_settings(
            scope=scope,
            disabled_plugins=_with_name(self._settings.disabled_plugins, name),
        )

    def get_settings(self) -> ControlConfig:
        return self._settings

    def get_setting(self, key: str) -> object | None:
        return getattr(self._settings, key, None)

    def get_global_settings(self) -> dict[str, Any]:
        return deepcopy(self._global_patch)

    def get_project_settings(self) -> dict[str, Any]:
        return deepcopy(self._project_patch)

    def get_session_settings(self) -> dict[str, Any]:
        return deepcopy(self._session_patch)

    def subscribe(self, listener: SettingsListener) -> Callable[[], None]:
        self._listeners.append(listener)

        def _unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                return

        return _unsubscribe

    def _compose_settings(self) -> ControlConfig:
        config = ControlConfig()
        config = _apply_patch(
            config, self._global_patch, scope="global", errors=self._errors
        )
        config = _apply_patch(
            config, self._project_patch, scope="project", errors=self._errors
        )
        config = _apply_patch(
            config, self._session_patch, scope="session", errors=self._errors
        )
        return config

    def _load_patch(
        self,
        scope: SettingsScope,
        path: Path | None,
        *,
        previous: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return load_settings_patch(path)
        except Exception as exc:
            self._errors.append(SettingsError(scope=scope, message=str(exc), error=exc))
            return dict(previous)

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener(self._settings)


def _with_name(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    normalized = name.strip()
    if not normalized or normalized in values:
        return values
    return (*values, normalized)


def _without_name(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    normalized = name.strip()
    return tuple(value for value in values if value != normalized)


def _package_identity_key(source: str) -> str:
    return package_source_match_key(source.strip())


def _with_package_source(
    values: tuple[PackageSourceConfig, ...],
    candidate: PackageSourceConfig,
) -> tuple[PackageSourceConfig, ...]:
    normalized = candidate.source.strip()
    if not normalized:
        return values
    candidate = replace(candidate, source=normalized)
    candidate_key = _package_identity_key(candidate.source)
    for existing in values:
        if _package_identity_key(existing.source) == candidate_key:
            return values
    return (*values, candidate)


def _without_package_source(
    values: tuple[PackageSourceConfig, ...], source: str
) -> tuple[PackageSourceConfig, ...]:
    normalized = source.strip()
    if not normalized:
        return values
    target_key = _package_identity_key(normalized)
    return tuple(
        value for value in values if _package_identity_key(value.source) != target_key
    )
