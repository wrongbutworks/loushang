from __future__ import annotations

from dataclasses import dataclass, replace

from loushang.coding.control import CompactionSettings, RetrySettings, SettingsManager


@dataclass
class SessionSettingsController:
    settings_manager: SettingsManager | None = None

    def get_settings_manager(self) -> SettingsManager | None:
        return self.settings_manager

    def get_compaction_settings(self) -> CompactionSettings:
        if self.settings_manager is None:
            return CompactionSettings()
        return self.settings_manager.get_settings().compaction

    def get_retry_settings(self) -> RetrySettings:
        if self.settings_manager is None:
            return RetrySettings()
        return self.settings_manager.get_retry_settings()

    def ensure_settings_manager(self) -> SettingsManager:
        if self.settings_manager is None:
            self.settings_manager = SettingsManager()
        return self.settings_manager

    @property
    def auto_retry_enabled(self) -> bool:
        return self.get_retry_settings().enabled

    def set_auto_retry_enabled(self, enabled: bool) -> None:
        self.ensure_settings_manager().set_retry_enabled(enabled)

    @property
    def auto_compaction_enabled(self) -> bool:
        return self.get_compaction_settings().enabled

    def set_auto_compaction_enabled(self, enabled: bool) -> None:
        manager = self.ensure_settings_manager()
        manager.update_settings(
            scope="session",
            compaction=replace(self.get_compaction_settings(), enabled=enabled),
        )

    def persist_queue_mode(self, kind: str, mode: str) -> None:
        if self.settings_manager is None:
            return
        try:
            if kind == "steering":
                self.settings_manager.set_steering_mode(mode, scope="global")
            else:
                self.settings_manager.set_follow_up_mode(mode, scope="global")
        except ValueError:
            if kind == "steering":
                self.settings_manager.set_steering_mode(mode, scope="session")
            else:
                self.settings_manager.set_follow_up_mode(mode, scope="session")
