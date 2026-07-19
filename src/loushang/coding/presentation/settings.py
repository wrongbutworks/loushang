"""Product-owned setting facts for Coding presentation hosts.

This module deliberately knows nothing about terminal widgets.  It translates
the Coding settings manager's boolean controls into immutable string facts and
applies string values at the product boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CodingSettingApplyOutcome",
    "CodingSettingFact",
    "apply_coding_setting",
    "coding_settings_facts",
]


@dataclass(frozen=True, slots=True)
class CodingSettingFact:
    """A renderer-neutral Coding setting row."""

    id: str
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class CodingSettingApplyOutcome:
    """The neutral result of attempting to apply a Coding setting."""

    matched: bool
    message: str


@dataclass(frozen=True, slots=True)
class _ManagerBoolSetting:
    id: str
    label: str
    getter: str
    setter: str
    status_label: str


_MANAGER_BOOL_SETTINGS = (
    _ManagerBoolSetting(
        "terminal.progress",
        "Terminal progress",
        "get_show_terminal_progress",
        "set_show_terminal_progress",
        "Terminal progress",
    ),
    _ManagerBoolSetting(
        "terminal.show_images",
        "Show images",
        "get_show_images",
        "set_show_images",
        "Show images",
    ),
    _ManagerBoolSetting(
        "terminal.clear_on_shrink",
        "Clear on shrink",
        "get_clear_on_shrink",
        "set_clear_on_shrink",
        "Clear on shrink",
    ),
    _ManagerBoolSetting(
        "images.auto_resize",
        "Image auto-resize",
        "get_image_auto_resize",
        "set_image_auto_resize",
        "Image auto-resize",
    ),
    _ManagerBoolSetting(
        "images.block_images",
        "Block images",
        "get_block_images",
        "set_block_images",
        "Block images",
    ),
    _ManagerBoolSetting(
        "retry.enabled",
        "Retry",
        "get_retry_enabled",
        "set_retry_enabled",
        "Retry",
    ),
)


def coding_settings_facts(
    settings_manager: object | None,
) -> tuple[CodingSettingFact, ...]:
    """Read the available Coding boolean settings as immutable facts."""

    if settings_manager is None:
        return ()
    facts = []
    for setting in _MANAGER_BOOL_SETTINGS:
        getter = getattr(settings_manager, setting.getter, None)
        if callable(getter):
            facts.append(
                CodingSettingFact(
                    id=setting.id,
                    label=setting.label,
                    value=_bool_text(bool(getter())),
                )
            )
    return tuple(facts)


def apply_coding_setting(
    settings_manager: object | None,
    item_id: str,
    value: str,
) -> CodingSettingApplyOutcome:
    """Apply one Coding-owned boolean setting by id.

    ``matched`` distinguishes a known Coding setting (including invalid or
    unavailable attempts) from an id owned by another presentation feature.
    """

    setting = _setting_for_id(item_id)
    if setting is None:
        return CodingSettingApplyOutcome(False, f"Unknown setting: {item_id}")

    enabled = _as_bool(value)
    if enabled is None:
        return CodingSettingApplyOutcome(True, f"Invalid {setting.label} value.")

    setter = getattr(settings_manager, setting.setter, None)
    if not callable(setter):
        return CodingSettingApplyOutcome(
            True, f"{setting.status_label} is not available."
        )

    setter(enabled)
    return CodingSettingApplyOutcome(
        True,
        f"{setting.status_label}: {'on' if enabled else 'off'}",
    )


def _setting_for_id(item_id: str) -> _ManagerBoolSetting | None:
    for setting in _MANAGER_BOOL_SETTINGS:
        if setting.id == item_id:
            return setting
    return None


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _as_bool(value: str) -> bool | None:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None
