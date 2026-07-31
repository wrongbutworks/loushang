from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass, replace
from pathlib import Path
from typing import Any, Literal, cast

from loushang.agent import ThinkingLevel
from loushang.ai.model import ModelSelection
from loushang.harness.config import (
    ConfigFieldSpec,
    ConfigLayer,
    LayeredConfig,
    SchemaConfigCodec,
    ScopedConfigRuntime,
    SettingsRuntime,
    decode_dataclass_patch,
    encode_dataclass_diff,
)
from loushang.harness.config.agent.types import (
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
    PermissionSettings,
    QueueMode,
    RetrySettings,
    SandboxSettings,
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
from loushang.harness.permissions import (
    PermissionProfileCeiling,
    PermissionProfileId,
    PermissionProfileScope,
    PermissionProfileSnapshot,
    permission_profile,
    permission_profile_snapshot,
)
from loushang.harness.resources.packages.source import (
    PackageSourceConfig,
    package_source_match_key,
)

SettingsListener = Callable[[ControlConfig], None]
SettingsScope = Literal["session", "global", "project"]
ThinkingBudgetKey = Literal["minimal", "low", "medium", "high"]


class _Unset:
    __slots__ = ()


_UNSET = _Unset()
_REMOVED_SETTING_MESSAGES = {
    "transport": "transport setting has been removed; use provider/contrib-specific configuration instead",
}


@dataclass(frozen=True)
class SettingsError:
    scope: SettingsScope
    message: str
    error: Exception


def _normalize_string_sequence(
    value: Iterable[str], field_name: str
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
    return cast(QueueMode, value)


def _deserialize_double_escape_action(value: object) -> DoubleEscapeAction:
    if value not in {"fork", "tree", "none"}:
        raise ValueError("double_escape_action must be 'fork', 'tree', or 'none'")
    return cast(DoubleEscapeAction, value)


def _deserialize_tree_filter_mode(value: object) -> TreeFilterMode:
    if value not in {"default", "no-tools", "user-only", "labeled-only", "all"}:
        raise ValueError(
            "tree_filter_mode must be 'default', 'no-tools', 'user-only', 'labeled-only', or 'all'"
        )
    return cast(TreeFilterMode, value)


def _deserialize_external_tool_policy(value: object) -> ExternalToolPolicy:
    if value not in {"never", "auto", "required"}:
        raise ValueError("external_tool_policy must be 'never', 'auto', or 'required'")
    return cast(ExternalToolPolicy, value)


def _deserialize_headless_approval_mode(value: object) -> HeadlessApprovalMode | None:
    if value is None:
        return None
    if value not in {"allow", "deny"}:
        raise ValueError("approval_mode must be 'allow', 'deny', or null")
    return cast(HeadlessApprovalMode, value)


def _deserialize_permission_profile(value: object) -> PermissionProfileId:
    if not isinstance(value, str):
        raise TypeError("permissions.profile must be a string")
    permission_profile(value)
    return cast(PermissionProfileId, value)


def _deserialize_statusline_auto_value(
    value: object, field_name: str
) -> StatusLineAutoValue:
    if value not in {"auto", "true", "false"}:
        raise ValueError(f"{field_name} must be 'auto', 'true', or 'false'")
    return cast(StatusLineAutoValue, value)


def _deserialize_statusline_separator(
    value: object, field_name: str
) -> StatusLineSeparator:
    if value not in {"pipe", "dot"}:
        raise ValueError(f"{field_name} must be 'pipe' or 'dot'")
    return cast(StatusLineSeparator, value)


def _deserialize_statusline_style(value: object, field_name: str) -> StatusLineStyle:
    if value not in {"codex-like", "muted", "plain"}:
        raise ValueError(f"{field_name} must be 'codex-like', 'muted', or 'plain'")
    return cast(StatusLineStyle, value)


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
        normalized[cast(ThinkingBudgetKey, key)] = item
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
        if key in {
            "enabled",
            "model",
            "workspace",
            "branch",
            "session",
            "permissions",
            "runtime",
        }:
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
    if not is_dataclass(value) or isinstance(value, type):
        raise TypeError("settings slice must be a dataclass or mapping")
    return dict(asdict(cast(Any, value)))


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
    return dict(_CONTROL_CONFIG_CODEC.encode(config))


def _apply_dataclass_patch(current: object, patch_value: object, field_name: str):
    return decode_dataclass_patch(
        patch_value,
        current,
        field_name=field_name,
    )


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
            normalized = _normalize_string_sequence(patch_value[key], key)
            if key == "blocked_tools":
                next_settings = replace(next_settings, blocked_tools=normalized)
            elif key == "ask_tools":
                next_settings = replace(next_settings, ask_tools=normalized)
            elif key == "blocked_substrings":
                next_settings = replace(next_settings, blocked_substrings=normalized)
            elif key == "ask_substrings":
                next_settings = replace(next_settings, ask_substrings=normalized)
            elif key == "blocked_path_substrings":
                next_settings = replace(
                    next_settings,
                    blocked_path_substrings=normalized,
                )
            else:
                next_settings = replace(
                    next_settings,
                    ask_path_substrings=normalized,
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


def _apply_permission_settings_patch(
    current: PermissionSettings,
    patch_value: object,
) -> PermissionSettings:
    if not isinstance(patch_value, Mapping):
        raise TypeError("permissions must be a JSON object")
    unknown = set(patch_value) - {"profile"}
    if unknown:
        raise ValueError(f"Unknown permission setting: permissions.{sorted(unknown)[0]}")
    if "profile" not in patch_value:
        return current
    return replace(
        current,
        profile=_deserialize_permission_profile(patch_value["profile"]),
    )


def _decode_bool(field_name: str):
    return lambda raw, current: _bool_value(raw, field_name)


def _decode_optional_string(field_name: str):
    return lambda raw, current: _optional_string(raw, field_name)


def _decode_optional_string_tuple(field_name: str):
    return lambda raw, current: _string_tuple_or_none(raw, field_name)


def _decode_string_tuple(field_name: str):
    def decode(raw: object, current: object) -> tuple[str, ...]:
        del current
        if not isinstance(raw, Sequence):
            raise TypeError(f"{field_name} must be a sequence of strings")
        return _normalize_string_sequence(raw, field_name)

    return decode


def _decode_dataclass(field_name: str):
    return lambda raw, current: _apply_dataclass_patch(current, raw, field_name)


def _encode_optional_tuple(current: object, default: object) -> object:
    del default
    return list(cast(Iterable[object], current)) if current is not None else None


def _encode_tuple(current: object, default: object) -> object:
    del default
    return list(cast(tuple[object, ...], current))


def _decode_keybinding_overlay(raw: object, current: object) -> object:
    return {
        **cast(Mapping[str, KeybindingValue], current),
        **_deserialize_keybindings(raw),
    }


def _decode_session_dir(raw: object, current: object) -> object:
    del current
    if raw is not None and not isinstance(raw, str):
        raise TypeError("session_dir must be a string or null")
    return raw


def _decode_package_sources(raw: object, current: object) -> object:
    del current
    return _normalize_package_source_sequence(raw)


def _encode_package_sources(current: object, default: object) -> object:
    del default
    return [
        _serialize_package_source(source)
        for source in cast(tuple[PackageSourceConfig, ...], current)
    ]


_CONTROL_CONFIG_CODEC = SchemaConfigCodec(
    default_factory=ControlConfig,
    fields=(
        ConfigFieldSpec(
            "default_model",
            decode=lambda raw, current: _deserialize_model_selection(raw),
            encode=lambda current, default: _serialize_model_selection(
                cast(ModelSelection | None, current)
            ),
        ),
        ConfigFieldSpec("thinking_level"),
        ConfigFieldSpec(
            "steering_mode",
            decode=lambda raw, current: _deserialize_queue_mode(raw, "steering_mode"),
        ),
        ConfigFieldSpec(
            "follow_up_mode",
            decode=lambda raw, current: _deserialize_queue_mode(raw, "follow_up_mode"),
        ),
        ConfigFieldSpec("theme", decode=_decode_optional_string("theme")),
        ConfigFieldSpec("system_prompt"),
        ConfigFieldSpec(
            "hide_thinking_block",
            decode=_decode_bool("hide_thinking_block"),
        ),
        ConfigFieldSpec("shell_path", decode=_decode_optional_string("shell_path")),
        ConfigFieldSpec("quiet_startup", decode=_decode_bool("quiet_startup")),
        ConfigFieldSpec(
            "shell_command_prefix",
            decode=_decode_optional_string("shell_command_prefix"),
        ),
        ConfigFieldSpec(
            "npm_command",
            decode=_decode_optional_string_tuple("npm_command"),
            encode=_encode_optional_tuple,
        ),
        ConfigFieldSpec(
            "collapse_changelog",
            decode=_decode_bool("collapse_changelog"),
        ),
        ConfigFieldSpec(
            "enable_install_telemetry",
            decode=_decode_bool("enable_install_telemetry"),
        ),
        ConfigFieldSpec(
            "enable_skill_commands",
            decode=_decode_bool("enable_skill_commands"),
        ),
        ConfigFieldSpec(
            "enabled_models",
            decode=_decode_optional_string_tuple("enabled_models"),
            encode=_encode_optional_tuple,
        ),
        ConfigFieldSpec(
            "double_escape_action",
            decode=lambda raw, current: _deserialize_double_escape_action(raw),
        ),
        ConfigFieldSpec(
            "tree_filter_mode",
            decode=lambda raw, current: _deserialize_tree_filter_mode(raw),
        ),
        ConfigFieldSpec(
            "show_hardware_cursor",
            decode=_decode_bool("show_hardware_cursor"),
        ),
        ConfigFieldSpec(
            "editor_padding_x",
            decode=lambda raw, current: _non_negative_small_int(
                raw,
                "editor_padding_x",
                upper_bound=3,
            ),
        ),
        ConfigFieldSpec(
            "autocomplete_max_visible",
            decode=lambda raw, current: _bounded_int(
                raw,
                "autocomplete_max_visible",
                lower_bound=3,
                upper_bound=20,
            ),
        ),
        ConfigFieldSpec(
            "keybindings",
            decode=_decode_keybinding_overlay,
            encode=lambda current, default: _serialize_keybindings(
                cast(Mapping[str, KeybindingValue], current)
            ),
        ),
        ConfigFieldSpec(
            "thinking_budgets",
            decode=lambda raw, current: _thinking_budgets(raw),
        ),
        *(
            ConfigFieldSpec(
                field_name,
                decode=_decode_dataclass(field_name),
                encode=encode_dataclass_diff,
            )
            for field_name in (
                "compaction",
                "branch_summary",
                "retry",
                "images",
                "terminal",
                "markdown",
                "warnings",
                "method",
            )
        ),
        ConfigFieldSpec(
            "permissions",
            decode=lambda raw, current: _apply_permission_settings_patch(
                cast(PermissionSettings, current), raw
            ),
            encode=encode_dataclass_diff,
            recover_errors=(TypeError, ValueError),
        ),
        ConfigFieldSpec(
            "tools",
            decode=lambda raw, current: _apply_tool_settings_patch(
                cast(ToolSettings, current), raw
            ),
            encode=encode_dataclass_diff,
        ),
        ConfigFieldSpec(
            "sandbox",
            decode=_decode_dataclass("sandbox"),
            encode=encode_dataclass_diff,
            recover_errors=(TypeError, ValueError),
        ),
        ConfigFieldSpec(
            "statusline",
            decode=lambda raw, current: _apply_statusline_settings_patch(
                cast(StatusLineControlSettings, current), raw
            ),
            encode=encode_dataclass_diff,
            recover_errors=(TypeError, ValueError),
        ),
        ConfigFieldSpec("session_dir", decode=_decode_session_dir),
        ConfigFieldSpec(
            "resource_roots",
            decode=_decode_string_tuple("resource_roots"),
            encode=_encode_tuple,
        ),
        ConfigFieldSpec(
            "package_roots",
            decode=_decode_string_tuple("package_roots"),
            encode=_encode_tuple,
        ),
        ConfigFieldSpec(
            "package_sources",
            input_keys=("packages", "package_sources"),
            output_key="package_sources",
            decode=_decode_package_sources,
            encode=_encode_package_sources,
        ),
        ConfigFieldSpec(
            "plugin_sources",
            decode=_decode_string_tuple("plugin_sources"),
            encode=_encode_tuple,
        ),
        ConfigFieldSpec(
            "disabled_skills",
            decode=_decode_string_tuple("disabled_skills"),
            encode=_encode_tuple,
        ),
        ConfigFieldSpec(
            "disabled_plugins",
            decode=_decode_string_tuple("disabled_plugins"),
            encode=_encode_tuple,
        ),
    ),
    removed_fields=_REMOVED_SETTING_MESSAGES,
    unknown_fields="ignore",
)


class SettingsManager:
    """Manage the standard settings shared by Agent-backed products."""
    def __init__(
        self,
        initial: ControlConfig | None = None,
        *,
        global_settings_path: str | Path | None = None,
        project_settings_path: str | Path | None = None,
        permission_profile_ceiling: PermissionProfileCeiling | None = None,
    ) -> None:
        global_path = (
            Path(global_settings_path) if global_settings_path is not None else None
        )
        project_path = (
            Path(project_settings_path) if project_settings_path is not None else None
        )
        self._adapter_errors: list[SettingsError] = []
        self._permission_profile_ceiling = (
            permission_profile_ceiling or PermissionProfileCeiling()
        )
        self._config = SettingsRuntime(
            ScopedConfigRuntime(
                LayeredConfig(
                    codec=_CONTROL_CONFIG_CODEC,
                    layers=(
                        ConfigLayer("global", global_path, persistent=True),
                        ConfigLayer("project", project_path, persistent=True),
                        ConfigLayer("session"),
                    ),
                    initial={"session": initial} if initial is not None else None,
                )
            )
        )

    @property
    def _settings(self) -> ControlConfig:
        return self._config.value

    def reload(self) -> None:
        self._config.reload()

    async def flush(self) -> None:
        return None

    def apply_overrides(self, overrides: Mapping[str, Any] | ControlConfig) -> None:
        patch = (
            _control_config_to_patch(overrides)
            if isinstance(overrides, ControlConfig)
            else dict(overrides)
        )
        patch = _drop_removed_settings(
            patch,
            scope="session",
            errors=self._adapter_errors,
        )
        self._config.update("session", patch)

    def drain_errors(self) -> list[SettingsError]:
        errors = list(self._adapter_errors)
        self._adapter_errors.clear()
        errors.extend(
            SettingsError(
                scope=cast(SettingsScope, issue.layer),
                message=issue.message,
                error=issue.error,
            )
            for issue in self._config.drain_issues()
        )
        return errors

    @property
    def global_base_dir(self) -> Path | None:
        return self._config.scope("global").base_dir

    @property
    def project_base_dir(self) -> Path | None:
        return self._config.scope("project").base_dir

    def update_settings(
        self,
        *,
        scope: SettingsScope = "session",
        default_model: ModelSelection | None | _Unset = _UNSET,
        thinking_level: ThinkingLevel | _Unset = _UNSET,
        steering_mode: QueueMode | _Unset = _UNSET,
        follow_up_mode: QueueMode | _Unset = _UNSET,
        theme: str | None | _Unset = _UNSET,
        system_prompt: str | _Unset = _UNSET,
        hide_thinking_block: bool | _Unset = _UNSET,
        shell_path: str | None | _Unset = _UNSET,
        quiet_startup: bool | _Unset = _UNSET,
        shell_command_prefix: str | None | _Unset = _UNSET,
        npm_command: Sequence[str] | None | _Unset = _UNSET,
        collapse_changelog: bool | _Unset = _UNSET,
        enable_install_telemetry: bool | _Unset = _UNSET,
        enable_skill_commands: bool | _Unset = _UNSET,
        enabled_models: Sequence[str] | None | _Unset = _UNSET,
        double_escape_action: DoubleEscapeAction | _Unset = _UNSET,
        tree_filter_mode: TreeFilterMode | _Unset = _UNSET,
        show_hardware_cursor: bool | _Unset = _UNSET,
        editor_padding_x: float | int | _Unset = _UNSET,
        autocomplete_max_visible: float | int | _Unset = _UNSET,
        keybindings: Mapping[str, object] | _Unset = _UNSET,
        thinking_budgets: ThinkingBudgetMap | None | _Unset = _UNSET,
        compaction: CompactionSettings | _Unset = _UNSET,
        branch_summary: BranchSummarySettings | _Unset = _UNSET,
        retry: RetrySettings | _Unset = _UNSET,
        images: ImageSettings | _Unset = _UNSET,
        terminal: TerminalSettings | _Unset = _UNSET,
        markdown: MarkdownSettings | _Unset = _UNSET,
        warnings: WarningSettings | _Unset = _UNSET,
        method: MethodSettings | Mapping[str, object] | _Unset = _UNSET,
        permissions: PermissionSettings | Mapping[str, object] | _Unset = _UNSET,
        tools: ToolSettings | Mapping[str, object] | _Unset = _UNSET,
        sandbox: SandboxSettings | Mapping[str, object] | _Unset = _UNSET,
        statusline: StatusLineControlSettings | Mapping[str, object] | _Unset = _UNSET,
        session_dir: str | None | _Unset = _UNSET,
        resource_roots: Iterable[str] | _Unset = _UNSET,
        package_roots: Iterable[str] | _Unset = _UNSET,
        package_sources: Iterable[PackageSourceConfig | str | Mapping[str, object]]
        | _Unset = _UNSET,
        plugin_sources: Iterable[str] | _Unset = _UNSET,
        disabled_skills: Iterable[str] | _Unset = _UNSET,
        disabled_plugins: Iterable[str] | _Unset = _UNSET,
    ) -> None:
        patch: dict[str, Any] = {}
        if not isinstance(default_model, _Unset):
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
        if permissions is not _UNSET:
            patch["permissions"] = _serialize_settings_slice(permissions)
        if tools is not _UNSET:
            patch["tools"] = _serialize_tool_settings(tools)
        if sandbox is not _UNSET:
            patch["sandbox"] = _serialize_settings_slice(sandbox)
        if statusline is not _UNSET:
            patch["statusline"] = _serialize_statusline_settings(statusline)
        if session_dir is not _UNSET:
            patch["session_dir"] = session_dir
        if not isinstance(resource_roots, _Unset):
            patch["resource_roots"] = list(
                _normalize_string_sequence(resource_roots, "resource_roots")
            )
        if not isinstance(package_roots, _Unset):
            patch["package_roots"] = list(
                _normalize_string_sequence(package_roots, "package_roots")
            )
        if not isinstance(package_sources, _Unset):
            patch["packages"] = [
                _serialize_package_source(source)
                for source in _normalize_package_source_sequence(
                    list(package_sources), "package_sources"
                )
            ]
        if not isinstance(plugin_sources, _Unset):
            patch["plugin_sources"] = list(
                _normalize_string_sequence(plugin_sources, "plugin_sources")
            )
        if not isinstance(disabled_skills, _Unset):
            patch["disabled_skills"] = list(
                _normalize_string_sequence(disabled_skills, "disabled_skills")
            )
        if not isinstance(disabled_plugins, _Unset):
            patch["disabled_plugins"] = list(
                _normalize_string_sequence(disabled_plugins, "disabled_plugins")
            )

        layer = scope if scope in {"global", "project"} else "session"
        self._config.update(layer, patch)

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

    def get_permission_profile_id(self) -> PermissionProfileId:
        return self._settings.permissions.profile

    def get_permission_profile_ceiling(self) -> PermissionProfileCeiling:
        return self._permission_profile_ceiling

    def get_permission_profile_snapshot(self) -> PermissionProfileSnapshot:
        return permission_profile_snapshot(
            self.get_permission_profile_id(),
            self._permission_profile_ceiling,
        )

    def set_permission_profile(
        self,
        profile_id: PermissionProfileId | str,
        *,
        scope: PermissionProfileScope = "session",
    ) -> None:
        resolved_id = _deserialize_permission_profile(profile_id)
        if not self._permission_profile_ceiling.allows(resolved_id):
            raise PermissionError(
                self._permission_profile_ceiling.reason
                or (
                    "Permission profile is disabled by the managed ceiling: "
                    f"{resolved_id}"
                )
            )
        settings_scope: SettingsScope = (
            "global" if scope == "user" else cast(SettingsScope, scope)
        )
        settings = PermissionSettings(profile=resolved_id)
        self.update_settings(scope=settings_scope, permissions=settings)

    def get_tool_settings(self) -> ToolSettings:
        return self._settings.tools

    def get_sandbox_settings(self) -> SandboxSettings:
        return self._settings.sandbox

    def set_sandbox_settings(
        self,
        settings: SandboxSettings | Mapping[str, object],
        *,
        scope: SettingsScope = "global",
    ) -> None:
        self.update_settings(scope=scope, sandbox=settings)

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
        return self._config.scope("global").patch

    def get_project_settings(self) -> dict[str, Any]:
        return self._config.scope("project").patch

    def get_session_settings(self) -> dict[str, Any]:
        return self._config.scope("session").patch

    def subscribe(self, listener: SettingsListener) -> Callable[[], None]:
        return self._config.subscribe(listener)


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
