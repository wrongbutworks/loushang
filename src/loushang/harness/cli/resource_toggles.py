"""Shared resource toggle mutation over an injected settings manager."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


class ResourceToggleError(RuntimeError):
    """Raised after a resource toggle operation reports an actionable error."""

    def __init__(self, message: str, *, messages: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.messages = messages


@dataclass(frozen=True, slots=True)
class ResourceToggleRequest:
    enable_skills: tuple[str, ...] = ()
    disable_skills: tuple[str, ...] = ()
    add_plugin_sources: tuple[str, ...] = ()
    remove_plugin_sources: tuple[str, ...] = ()
    enable_plugins: tuple[str, ...] = ()
    disable_plugins: tuple[str, ...] = ()

    @property
    def has_operations(self) -> bool:
        return any(
            (
                self.enable_skills,
                self.disable_skills,
                self.add_plugin_sources,
                self.remove_plugin_sources,
                self.enable_plugins,
                self.disable_plugins,
            )
        )


@dataclass(frozen=True, slots=True)
class ResourceToggleResult:
    messages: tuple[str, ...] = ()


def apply_resource_toggles(
    settings_manager: object,
    request: ResourceToggleRequest,
    *,
    evaluate_plugin_source: Callable[[str], str | None] | None = None,
    is_remote_plugin_source: Callable[[str], bool] | None = None,
    on_policy_denied: Callable[[str, str | None], None] | None = None,
) -> ResourceToggleResult:
    """Apply toggles while keeping settings ownership in the Product port."""

    messages: list[str] = []
    try:
        for name in request.disable_skills:
            _call(settings_manager, "disable_skill", name, scope="project")
            messages.append(f"disabled skill\t{name}")
        for name in request.enable_skills:
            _call(settings_manager, "enable_skill", name, scope="project")
            messages.append(f"enabled skill\t{name}")
        for source in request.remove_plugin_sources:
            removed = _call(
                settings_manager,
                "remove_plugin_source",
                source,
                scope="project",
            )
            if removed is False:
                raise ResourceToggleError(
                    f"no matching plugin source found: {source}",
                    messages=tuple(messages),
                )
            messages.append(f"removed plugin source\t{source}")
        for source in request.add_plugin_sources:
            reason = (
                evaluate_plugin_source(source)
                if evaluate_plugin_source is not None
                else None
            )
            if reason is not None:
                if on_policy_denied is not None:
                    on_policy_denied(source, reason)
                raise ResourceToggleError(reason, messages=tuple(messages))
            added = _call(
                settings_manager,
                "add_plugin_source",
                source,
                scope="project",
            )
            if added is False:
                raise ResourceToggleError(
                    f"plugin source already exists: {source}",
                    messages=tuple(messages),
                )
            label = (
                "remote plugin source"
                if is_remote_plugin_source is not None
                and is_remote_plugin_source(source)
                else "plugin source"
            )
            messages.append(f"added {label}\t{source}")
        for name in request.disable_plugins:
            _call(settings_manager, "disable_plugin", name, scope="project")
            messages.append(f"disabled plugin\t{name}")
        for name in request.enable_plugins:
            _call(settings_manager, "enable_plugin", name, scope="project")
            messages.append(f"enabled plugin\t{name}")
    except ResourceToggleError:
        raise
    except Exception as error:
        raise ResourceToggleError(str(error), messages=tuple(messages)) from error
    return ResourceToggleResult(tuple(messages))


def _call(settings_manager: object, name: str, *args: object, **kwargs: object) -> object:
    method = getattr(settings_manager, name, None)
    if not callable(method):
        raise ResourceToggleError(f"settings operation is not available: {name}")
    return method(*args, **kwargs)


__all__ = [
    "ResourceToggleError",
    "ResourceToggleRequest",
    "ResourceToggleResult",
    "apply_resource_toggles",
]
