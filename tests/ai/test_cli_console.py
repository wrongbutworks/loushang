from __future__ import annotations

import pytest

from loushang.ai.cli.__main__ import main
from loushang.ai.model.domain import Auth, Capabilities, Endpoint, Model, Provider
from loushang.ai.model.registry import ModelRegistry
from loushang.ai.types import AssistantMessage, Usage


def _build_registry() -> ModelRegistry:
    endpoint = Endpoint(
        id="openai-completions",
        provider="moonshot",
        api="openai-completions",
        auth=Auth(api_key_env="MOONSHOT_API_KEY"),
        models={
            "kimi-a": Model(
                id="kimi-a",
                provider="moonshot",
                endpoint="openai-completions",
                capabilities=Capabilities(
                    input=("text",), output=("text",), stream=True
                ),
            ),
            "kimi-b": Model(
                id="kimi-b",
                provider="moonshot",
                endpoint="openai-completions",
                capabilities=Capabilities(
                    input=("text",), output=("text",), stream=True
                ),
            ),
        },
    )
    provider = Provider(
        id="moonshot",
        name="Moonshot AI",
        auth=Auth(api_key_env="MOONSHOT_API_KEY"),
        endpoints={endpoint.id: endpoint},
    )
    return ModelRegistry.from_providers({"moonshot": provider})


def _assistant_message(text: str) -> AssistantMessage:
    del text
    return AssistantMessage(
        role="assistant",
        content=[],
        api="openai-completions",
        provider="moonshot",
        model="kimi-a",
        response_id="resp_1",
        usage=Usage(
            input=1,
            output=1,
            cache_read=0,
            cache_write=0,
            total_tokens=2,
            cost={},
        ),
        stop_reason="stop",
        error_message=None,
        timestamp=0.0,
    )


@pytest.fixture(autouse=True)
def _patch_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "loushang.ai.cli.__main__.get_default_model_registry", _build_registry
    )
    monkeypatch.setattr(
        "loushang.ai.cli.__main__.register_builtin_oauth_providers", lambda: None
    )


def test_console_uses_env_api_key_for_selected_binding(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "env-key")
    inputs = iter(["1", "", "1", "hi", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    captured: list[tuple[str, object | None]] = []

    async def _fake_turn(model, context, options, *, as_json):
        captured.append((model.id, options))
        return _assistant_message("ok")

    monkeypatch.setattr("loushang.ai.cli.__main__._run_console_turn", _fake_turn)

    with pytest.raises(SystemExit) as exc_info:
        main(["console"])

    assert exc_info.value.code == 0
    assert captured
    assert captured[0][0] == "kimi-a"
    assert getattr(captured[0][1], "api_key", None) == "env-key"
    output = capsys.readouterr().out
    assert "Loushang AI Console" in output
    assert (
        "Manual credentials entered in console are kept in memory only and are not saved."
        in output
    )
    assert (
        "Context is kept during the current run, but exiting console does not preserve a session."
        in output
    )
    assert "Current model: moonshot:openai-completions:kimi-a" in output


def test_console_prompts_for_api_key_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    inputs = iter(["1", "", "1", "hi", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": "typed-key")

    captured: list[object | None] = []

    async def _fake_turn(model, context, options, *, as_json):
        del model, context, as_json
        captured.append(options)
        return _assistant_message("ok")

    monkeypatch.setattr("loushang.ai.cli.__main__._run_console_turn", _fake_turn)

    with pytest.raises(SystemExit):
        main(["console"])

    assert captured
    assert getattr(captured[0], "api_key", None) == "typed-key"
    output = capsys.readouterr().out
    assert "Current model: moonshot:openai-completions:kimi-a" in output


def test_console_authenticates_after_endpoint_before_model_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    events: list[str] = []
    inputs = iter(["1", "", "1", "hi", "/exit"])

    def fake_input(_prompt=""):
        events.append("input")
        return next(inputs)

    def fake_getpass(_prompt=""):
        events.append("getpass")
        return "typed-key"

    async def _fake_turn(model, context, options, *, as_json):
        del model, context, options, as_json
        raise SystemExit(0)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr("getpass.getpass", fake_getpass)
    monkeypatch.setattr("loushang.ai.cli.__main__._run_console_turn", _fake_turn)

    with pytest.raises(SystemExit):
        main(["console"])

    assert events[:3] == ["input", "getpass", "input"]


def test_console_can_switch_model(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "env-key")
    inputs = iter(["1", "", "1", "hi", "/switch-model", "2", "hi again", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    seen_models: list[str] = []

    async def _fake_turn(model, context, options, *, as_json):
        del context, options, as_json
        seen_models.append(model.id)
        return _assistant_message("ok")

    monkeypatch.setattr("loushang.ai.cli.__main__._run_console_turn", _fake_turn)

    with pytest.raises(SystemExit):
        main(["console"])

    assert seen_models == ["kimi-a", "kimi-b"]
    output = capsys.readouterr().out
    assert "Current model: moonshot:openai-completions:kimi-b" in output


def test_console_debug_outputs_api_and_auth_source(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "env-key")
    inputs = iter(["1", "", "1", "hi", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    async def _fake_turn(model, context, options, *, as_json):
        del model, context, options, as_json
        return _assistant_message("ok")

    monkeypatch.setattr("loushang.ai.cli.__main__._run_console_turn", _fake_turn)

    with pytest.raises(SystemExit):
        main(["console", "--debug"])

    output = capsys.readouterr().out
    assert "DEBUG api=openai-completions auth=env:MOONSHOT_API_KEY" in output


def test_console_selection_supports_back_navigation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("MOONSHOT_API_KEY", "env-key")
    inputs = iter(["back", "1", "", "back", "", "1", "hi", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    seen_models: list[str] = []

    async def _fake_turn(model, context, options, *, as_json):
        del context, options, as_json
        seen_models.append(model.id)
        return _assistant_message("ok")

    monkeypatch.setattr("loushang.ai.cli.__main__._run_console_turn", _fake_turn)

    with pytest.raises(SystemExit):
        main(["console", "--provider", "moonshot"])

    assert seen_models == ["kimi-a"]
    output = capsys.readouterr().out
    assert "Type `back` to return to the previous step" in output
    assert "b. back" in output
