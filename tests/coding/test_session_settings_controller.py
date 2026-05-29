from __future__ import annotations


def test_session_settings_controller_returns_defaults_without_manager() -> None:
    from loushang.coding.control import CompactionSettings, RetrySettings
    from loushang.coding.session.session_settings_controller import SessionSettingsController

    controller = SessionSettingsController(settings_manager=None)

    assert controller.get_settings_manager() is None
    assert controller.get_compaction_settings() == CompactionSettings()
    assert controller.get_retry_settings() == RetrySettings()
    assert controller.auto_retry_enabled is controller.get_retry_settings().enabled
    assert controller.auto_compaction_enabled is controller.get_compaction_settings().enabled


def test_session_settings_controller_lazily_creates_manager_for_auto_flags() -> None:
    from loushang.coding.session.session_settings_controller import SessionSettingsController

    controller = SessionSettingsController(settings_manager=None)

    controller.set_auto_retry_enabled(False)
    controller.set_auto_compaction_enabled(False)

    manager = controller.get_settings_manager()
    assert manager is not None
    assert manager.get_retry_settings().enabled is False
    assert manager.get_settings().compaction.enabled is False


def test_session_settings_controller_persists_queue_modes_to_existing_manager(tmp_path) -> None:
    from loushang.coding.control import SettingsManager
    from loushang.coding.session.session_settings_controller import SessionSettingsController

    settings_path = tmp_path / "settings.json"
    controller = SessionSettingsController(
        settings_manager=SettingsManager(global_settings_path=settings_path)
    )

    controller.persist_queue_mode("steering", "all")
    controller.persist_queue_mode("follow_up", "all")

    reloaded = SettingsManager(global_settings_path=settings_path)
    assert reloaded.get_settings().steering_mode == "all"
    assert reloaded.get_settings().follow_up_mode == "all"
