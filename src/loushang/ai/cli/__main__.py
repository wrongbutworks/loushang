from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from loushang.ai import (
    AnthropicOptions,
    OpenAICodexResponsesOptions,
    OpenAICompletionsOptions,
    OpenAIResponsesOptions,
    StreamOptions,
    complete,
    get_api_provider,
    get_env_api_key,
    list_api_providers,
    stream,
)
from loushang.ai.api_registry import get_default_api_provider_registry
from loushang.ai.auth import (
    get_env_oauth_credentials,
    get_oauth_provider,
    list_oauth_providers,
    load_credentials,
    oauth_login,
    register_builtin_oauth_providers,
)
from loushang.ai.auth.support import merge_auth_config
from loushang.ai.auth.types import OAuthAuthInfo, OAuthLoginCallbacks, OAuthPrompt
from loushang.ai.model.registry import get_default_model_registry, resolve_model_api

_OPTION_CLASS_BY_API = {
    "anthropic-messages": AnthropicOptions,
    "openai-completions": OpenAICompletionsOptions,
    "openai-responses": OpenAIResponsesOptions,
    "openai-codex-responses": OpenAICodexResponsesOptions,
}

_BACK = object()


@dataclass(frozen=True)
class ConsoleBinding:
    provider_id: str
    endpoint_id: str
    model: object
    options: object | None
    api: str
    auth_source: str


class _CliOAuthCallbacks(OAuthLoginCallbacks):
    def on_auth(self, info: OAuthAuthInfo) -> None:
        url = info.get("url")
        instructions = info.get("instructions")
        if url:
            print(f"LOGIN_URL {url}")
        if instructions:
            print(f"INSTRUCTIONS {instructions}")

    async def on_prompt(self, prompt: OAuthPrompt) -> str:
        message = prompt.get("message", "Input")
        placeholder = prompt.get("placeholder")
        if placeholder:
            print(f"PROMPT {message} [{placeholder}]")
        else:
            print(f"PROMPT {message}")
        return input("> ").strip()

    def on_progress(self, message: str) -> None:
        print(f"PROGRESS {message}")

    async def on_manual_code_input(self) -> str:
        print(
            "INPUT Paste the login result if you already have it. Press Enter to continue."
        )
        return input("> ").strip()

    @property
    def signal(self) -> object | None:
        return None


def _print(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False))
        return
    if isinstance(obj, (dict, list, tuple)):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return
    print(str(obj))


def cmd_apis(args: argparse.Namespace) -> None:
    if args.action == "list":
        _print(list_api_providers(), args.json)
        return
    if args.action == "show":
        api = args.api
        provider = get_api_provider(api)
        _print({"api": api, "provider": type(provider).__name__}, args.json)
        return


def cmd_models(args: argparse.Namespace) -> None:
    registry = get_default_model_registry()
    if args.action == "list":
        models = registry.list_models(provider=args.provider)
        if args.api:
            models = [
                model
                for model in models
                if resolve_model_api(model, registry=registry) == args.api
            ]
        items = sorted({model.id for model in models})
        _print(items, args.json)
        return
    if args.action == "show":
        try:
            model = _resolve_model_arg(
                registry,
                args.model,
                provider=getattr(args, "provider", None),
                endpoint=getattr(args, "endpoint", None),
                api=getattr(args, "api", None),
            )
        except (KeyError, ValueError) as error:
            print(str(error), file=sys.stderr)
            sys.exit(2)
        data = {
            "id": model.id,
            "provider": model.provider_id,
            "endpoint": model.endpoint_id,
            "api": resolve_model_api(model, registry=registry),
            "name": model.name,
            "family": model.family,
            "alias": model.alias,
            "capabilities": {
                "input": list(model.capabilities.input),
                "output": list(model.capabilities.output),
                "reasoning": model.capabilities.reasoning,
                "contextWindow": model.capabilities.context_window,
                "maxTokens": model.capabilities.max_tokens,
                "toolUse": model.capabilities.tool_use,
                "structuredOutput": model.capabilities.structured_output,
                "temperature": model.capabilities.temperature,
                "stream": model.capabilities.stream,
                "attachment": model.capabilities.attachment,
            },
            "defaults": model.defaults,
            "compat": model.compat,
        }
        _print(data, args.json)
        return


def cmd_endpoints(args: argparse.Namespace) -> None:
    registry = get_default_model_registry()
    if args.action == "list":
        items = []
        for endpoint in registry.list_endpoints(provider=args.provider):
            items.append(f"{endpoint.provider_id}:{endpoint.id}")
        _print(sorted(items), args.json)
        return
    if args.action == "show":
        target = args.target
        if ":" not in target:
            print("format: <provider>:<endpoint>", file=sys.stderr)
            sys.exit(2)
        pkey, ekey = target.split(":", 1)
        endpoint_info = registry.get_endpoint(pkey, ekey)
        if endpoint_info is None:
            print("endpoint not found", file=sys.stderr)
            sys.exit(2)
        data = {
            "provider": pkey,
            "endpoint": ekey,
            "api": endpoint_info.api,
            "base_url": endpoint_info.base_url,
            "region": endpoint_info.region,
            "lane": endpoint_info.lane,
            "defaults": endpoint_info.defaults,
            "compat": endpoint_info.compat,
        }
        _print(data, args.json)
        return


def cmd_chat(args: argparse.Namespace) -> None:
    registry = get_default_model_registry()
    model = _resolve_model_with_env_fallback(
        registry,
        model_arg=getattr(args, "model", None),
        provider=getattr(args, "provider", None),
        endpoint=getattr(args, "endpoint", None),
        api=getattr(args, "api", None),
    )
    context = {"messages": [{"role": "user", "content": args.message}]}
    options = None

    async def run():
        ev = await stream(model, context, options, registry=get_api_provider_registry())
        if args.json:
            async for e in ev:
                print(json.dumps(e, ensure_ascii=False))
        else:
            async for e in ev:
                t = e.get("type")
                if t == "text_delta":
                    ch = e.get("delta")
                    if ch is None:
                        ch = e.get("text")
                    if isinstance(ch, str):
                        print(ch, end="", flush=True)
                elif t in {"done", "error"}:
                    print()
        res = await ev.result()
        if args.json:
            print(json.dumps(res.__dict__, ensure_ascii=False))

    return _run_async(run)


def get_api_provider_registry():
    return get_default_api_provider_registry()


def _run_async(coro_factory):
    import asyncio

    return asyncio.run(coro_factory())


def cmd_complete(args: argparse.Namespace) -> None:
    registry = get_default_model_registry()
    model = _resolve_model_with_env_fallback(
        registry,
        model_arg=getattr(args, "model", None),
        provider=getattr(args, "provider", None),
        endpoint=getattr(args, "endpoint", None),
        api=getattr(args, "api", None),
    )
    context = {"messages": [{"role": "user", "content": args.message}]}
    options = None

    async def run():
        res = await complete(
            model, context, options, registry=get_api_provider_registry()
        )
        if args.json:
            print(json.dumps(res.__dict__, ensure_ascii=False))
        else:
            print(
                "".join(
                    [p.text for p in res.content if getattr(p, "type", None) == "text"]
                )
            )

    return _run_async(run)


def cmd_auth(args: argparse.Namespace) -> None:
    register_builtin_oauth_providers()

    if args.action == "providers":
        items = [
            {"id": provider.id, "name": provider.name}
            for provider in list_oauth_providers()
        ]
        _print(items, args.json)
        return

    if args.action == "show":
        provider = get_oauth_provider(args.provider)
        if provider is None:
            print(f"OAuth provider not found: {args.provider}", file=sys.stderr)
            sys.exit(2)
        stored = load_credentials().get(args.provider)
        source = "stored" if stored is not None else None
        data = {
            "id": provider.id,
            "name": provider.name,
            "uses_callback_server": provider.uses_callback_server(),
            "has_credentials": stored is not None,
            "source": source,
            "extra": dict(stored.extra or {}) if stored is not None else None,
        }
        _print(data, args.json)
        return

    if args.action == "login":
        provider_id = args.provider
        if not provider_id:
            providers = list_oauth_providers()
            if not providers:
                print("No OAuth providers registered.", file=sys.stderr)
                sys.exit(2)
            if args.json:
                _print(
                    [
                        {"id": provider.id, "name": provider.name}
                        for provider in providers
                    ],
                    True,
                )
                return
            print("Select OAuth provider:")
            for index, item in enumerate(providers, start=1):
                print(f"{index}. {item.id} ({item.name})")
            selected = input("> ").strip()
            try:
                chosen = int(selected)
            except ValueError:
                print("Invalid selection.", file=sys.stderr)
                sys.exit(2)
            if chosen < 1 or chosen > len(providers):
                print("Invalid selection.", file=sys.stderr)
                sys.exit(2)
            provider_id = providers[chosen - 1].id

        provider = get_oauth_provider(provider_id)
        if provider is None:
            print(f"OAuth provider not found: {provider_id}", file=sys.stderr)
            sys.exit(2)

        credentials = _run_async(
            lambda: oauth_login(
                provider_id,
                _CliOAuthCallbacks(),
                persist=True,
            )
        )
        output = {
            "provider": credentials.provider,
            "stored": True,
            "source": "stored",
            "expires_at": credentials.expires_at,
            "extra": credentials.extra,
        }
        _print(output, args.json)
        return


def cmd_console(args: argparse.Namespace) -> None:
    register_builtin_oauth_providers()
    registry = get_default_model_registry()
    print("Loushang AI Console")
    print("- Interactive path: provider -> endpoint -> auth -> model -> conversation")
    print(
        "- Manual credentials entered in console are kept in memory only and are not saved."
    )
    print("- Environment variables are read only and are never overwritten.")
    print(
        "- Context is kept during the current run, but exiting console does not preserve a session."
    )
    binding = _build_console_binding(
        registry,
        provider_hint=getattr(args, "provider", None),
        endpoint_hint=getattr(args, "endpoint", None),
        model_hint=getattr(args, "model", None),
        debug=bool(getattr(args, "debug", False)),
    )
    history: list[object] = []
    system_prompt = getattr(args, "system_prompt", None) or None
    print(f"Current model: {_format_binding(binding)}")
    if getattr(args, "debug", False):
        print(f"DEBUG api={binding.api} auth={binding.auth_source}")
    print("Commands: /help /model /switch /switch-model /reset /exit")

    while True:
        try:
            raw = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not raw:
            continue
        if raw.startswith("/"):
            next_binding = _handle_console_command(raw, binding, registry, history)
            if isinstance(next_binding, ConsoleBinding):
                binding = next_binding
                if getattr(args, "debug", False):
                    print(f"DEBUG api={binding.api} auth={binding.auth_source}")
            continue

        context: dict[str, object] = {
            "messages": [*history, {"role": "user", "content": raw}]
        }
        if system_prompt:
            context["system_prompt"] = system_prompt
        message = _run_async(
            lambda: _run_console_turn(
                binding.model,
                context,
                binding.options,
                as_json=args.json,
            )
        )
        history.append({"role": "user", "content": raw})
        history.append(message)


def _handle_console_command(
    raw: str,
    binding: ConsoleBinding,
    registry,
    history: list[object],
) -> ConsoleBinding | None:
    command = raw.strip().lower()
    if command in {"/exit", "/quit"}:
        raise SystemExit(0)
    if command == "/help":
        print("Commands: /help /model /switch /switch-model /reset /exit")
        print("Notes:")
        print("- Manual credentials entered in console are not persisted.")
        print("- Context is preserved only inside this running process.")
        print("- Exiting console clears the conversation; there is no saved session.")
        return None
    if command == "/model":
        print(f"Current model: {_format_binding(binding)}")
        return None
    if command == "/reset":
        history.clear()
        print("Conversation reset.")
        return None
    if command == "/switch":
        next_binding = _build_console_binding(registry)
        history.clear()
        print(f"Current model: {_format_binding(next_binding)}")
        return next_binding
    if command == "/switch-model":
        next_binding = _switch_console_model(binding, registry)
        history.clear()
        print(f"Current model: {_format_binding(next_binding)}")
        return next_binding
    print("Unknown command. Use /help.")
    return None


def _build_console_binding(
    registry,
    *,
    provider_hint: str | None = None,
    endpoint_hint: str | None = None,
    model_hint: str | None = None,
    debug: bool = False,
) -> ConsoleBinding:
    if provider_hint and endpoint_hint and model_hint:
        provider = _select_console_provider(registry, provider_hint=provider_hint)
        endpoint = _select_console_endpoint(provider, endpoint_hint=endpoint_hint)
        model = _select_console_model(endpoint, model_hint=model_hint)
        return _create_console_binding(
            provider=provider,
            endpoint=endpoint,
            model=model,
            debug=debug,
        )

    provider = None
    endpoint = None
    while True:
        if provider is None:
            provider = _select_console_provider(registry, provider_hint=provider_hint)
            provider_hint = None
        if endpoint is None:
            selected_endpoint = _select_console_endpoint(
                provider,
                endpoint_hint=endpoint_hint,
                allow_back=True,
            )
            endpoint_hint = None
            if selected_endpoint is _BACK:
                provider = None
                continue
            endpoint = selected_endpoint
        auth_result = _prepare_console_auth(
            provider,
            endpoint,
            debug=debug,
        )
        model = _select_console_model(
            endpoint,
            model_hint=model_hint,
            allow_back=True,
        )
        model_hint = None
        if model is _BACK:
            endpoint = None
            continue
        return _create_console_binding(
            provider=provider,
            endpoint=endpoint,
            model=model,
            auth_result=auth_result,
            debug=debug,
        )


def _switch_console_model(binding: ConsoleBinding, registry) -> ConsoleBinding:
    provider = registry.get_provider(binding.provider_id)
    endpoint = registry.get_endpoint(binding.provider_id, binding.endpoint_id)
    if provider is None or endpoint is None:
        return _build_console_binding(registry)
    model = _select_console_model(endpoint)
    auth_result = _prepare_console_auth(provider, endpoint, debug=False)
    api = resolve_model_api(model)
    options, auth_source = _build_console_options(
        model,
        api=api,
        auth_result=auth_result,
        debug=False,
    )
    return ConsoleBinding(
        provider_id=provider.id,
        endpoint_id=endpoint.id,
        model=model,
        options=options,
        api=api,
        auth_source=auth_source,
    )


def _select_console_provider(registry, *, provider_hint: str | None = None):
    if provider_hint:
        provider = registry.get_provider(provider_hint)
        if provider is None:
            raise ValueError(f"Provider not found: {provider_hint}")
        return provider
    return _prompt_choice(
        "Select provider:",
        registry.list_providers(),
        lambda provider: f"{provider.id} ({provider.name or provider.id})",
    )


def _select_console_endpoint(
    provider,
    *,
    endpoint_hint: str | None = None,
    allow_back: bool = False,
):
    endpoints = provider.list_endpoints()
    if endpoint_hint:
        endpoint = provider.get_endpoint(endpoint_hint)
        if endpoint is None:
            raise ValueError(f"Endpoint not found for {provider.id}: {endpoint_hint}")
        return endpoint
    return _prompt_choice(
        f"Select endpoint for {provider.id}:",
        endpoints,
        lambda endpoint: f"{endpoint.id} [{endpoint.api}]",
        allow_back=allow_back,
    )


def _select_console_model(
    endpoint, *, model_hint: str | None = None, allow_back: bool = False
):
    candidates = [
        model for model in endpoint.list_models() if _is_console_chat_model(model)
    ]
    if not candidates:
        candidates = endpoint.list_models()
    if model_hint:
        for model in candidates:
            if model.id == model_hint:
                return model
        raise ValueError(
            f"Model not found for {endpoint.provider_id}:{endpoint.id}: {model_hint}"
        )
    return _prompt_choice(
        f"Select model for {endpoint.provider_id}:{endpoint.id}:",
        candidates,
        lambda model: model.id,
        allow_back=allow_back,
    )


def _is_console_chat_model(model) -> bool:
    input_modalities = tuple(getattr(model, "input", ()) or ())
    output_modalities = tuple(getattr(model, "output", ()) or ())
    return "text" in input_modalities and "text" in output_modalities


def _prompt_choice(
    title: str, items: list[object], render, *, allow_back: bool = False
) -> object:
    if not items:
        raise ValueError(f"{title} no options available")
    if len(items) == 1:
        item = items[0]
        print(f"{title}\n1. {render(item)}")
        if not allow_back:
            return item
        print(
            "Type `back` to return to the previous step, or press Enter to keep this selection."
        )
        selected = input("> ").strip().lower()
        if selected in {"", "1"}:
            return item
        if selected in {"b", "back"}:
            return _BACK

    print(title)
    for index, item in enumerate(items, start=1):
        print(f"{index}. {render(item)}")
    if allow_back:
        print("b. back")

    while True:
        selected = input("> ").strip().lower()
        if allow_back and selected in {"b", "back"}:
            return _BACK
        try:
            chosen = int(selected)
        except ValueError:
            print("Invalid selection.", file=sys.stderr)
            continue
        if 1 <= chosen <= len(items):
            return items[chosen - 1]
        print("Invalid selection.", file=sys.stderr)


def _create_console_binding(
    *, provider, endpoint, model, auth_result=None, debug: bool
) -> ConsoleBinding:
    api = resolve_model_api(model)
    if auth_result is None:
        auth_result = _prepare_console_auth(provider, endpoint, debug=debug)
    options, auth_source = _build_console_options(
        model,
        api=api,
        auth_result=auth_result,
        debug=debug,
    )
    return ConsoleBinding(
        provider_id=provider.id,
        endpoint_id=endpoint.id,
        model=model,
        options=options,
        api=api,
        auth_source=auth_source,
    )


def _prepare_console_auth(
    provider, endpoint, *, debug: bool
) -> tuple[dict[str, object], str]:
    auth_config = merge_auth_config(
        getattr(provider, "auth", None), getattr(endpoint, "auth", None)
    )
    option_kwargs: dict[str, object] = {}
    auth_source = "none"
    if getattr(auth_config, "kind", "apiKey") == "oauth":
        oauth_credentials, auth_source = _resolve_console_oauth_credentials(provider.id)
        if oauth_credentials is not None:
            option_kwargs["oauth_credentials"] = oauth_credentials
    else:
        api_key, auth_source = _resolve_console_api_key(provider.id, auth_config)
        if api_key:
            option_kwargs["api_key"] = api_key
    if debug:
        print(
            "DEBUG auth-prepared "
            f"provider={provider.id} endpoint={endpoint.id} source={auth_source}"
        )
    return option_kwargs, auth_source


def _build_console_options(model, *, api: str, auth_result, debug: bool = False):
    option_kwargs, auth_source = auth_result
    if debug:
        option_kwargs["trace"] = _console_trace
    if not option_kwargs:
        return None, auth_source
    option_cls = _OPTION_CLASS_BY_API.get(api, StreamOptions)
    return option_cls(**option_kwargs), auth_source


def _resolve_console_oauth_credentials(
    provider_id: str,
) -> tuple[dict[str, object] | None, str]:
    env_credentials = get_env_oauth_credentials(provider_id)
    if env_credentials is not None:
        return {provider_id: env_credentials}, "env-oauth"

    stored = load_credentials().get(provider_id)
    if stored is not None:
        return {provider_id: stored}, "stored-oauth"

    print(f"No stored login found for {provider_id}. Starting login flow.")
    credentials = _run_async(
        lambda: oauth_login(provider_id, _CliOAuthCallbacks(), persist=False)
    )
    return {provider_id: credentials}, "interactive-oauth-memory"


def _resolve_console_api_key(provider_id: str, auth_config) -> tuple[str | None, str]:
    env_names = _console_api_key_env_names(auth_config)
    for env_name in env_names:
        value = os.getenv(env_name)
        if isinstance(value, str) and value.strip():
            return value.strip(), f"env:{env_name}"

    if not env_names:
        fallback = get_env_api_key(provider_id)
        if fallback:
            return fallback, "env:provider-default"

    label = env_names[0] if env_names else f"{provider_id.upper().replace('-', '_')}_API_KEY"
    value = getpass.getpass(f"{label}: ").strip()
    if not value:
        raise ValueError(f"Missing API key for provider: {provider_id}")
    return value, "interactive-secret"


def _console_api_key_env_names(auth_config) -> tuple[str, ...]:
    if auth_config is None:
        return ()
    names: list[str] = []
    for name in tuple(getattr(auth_config, "api_key_envs", ()) or ()):
        if isinstance(name, str) and name:
            names.append(name)
    api_key_env = getattr(auth_config, "api_key_env", None)
    if isinstance(api_key_env, str) and api_key_env:
        names.append(api_key_env)
    return tuple(dict.fromkeys(names))


def _console_trace(event: dict) -> None:
    print(f"TRACE {json.dumps(event, ensure_ascii=False)}")


async def _run_console_turn(model, context, options, *, as_json: bool):
    event_stream = await model.stream(context, options)
    if as_json:
        async for event in event_stream:
            print(json.dumps(event, ensure_ascii=False))
    else:
        printed_text = False
        async for event in event_stream:
            event_type = event.get("type")
            if event_type == "text_delta":
                delta = event.get("delta")
                if isinstance(delta, str):
                    print(delta, end="", flush=True)
                    printed_text = True
            elif event_type == "toolcall_end":
                tool_call = event.get("tool_call")
                name = getattr(tool_call, "name", None) or (
                    tool_call.get("name") if isinstance(tool_call, dict) else None
                )
                if name:
                    if printed_text:
                        print()
                    print(f"[toolUse requested: {name}]")
            elif event_type == "error":
                error = event.get("error")
                if printed_text:
                    print()
                print(f"[error] {error}")
        if printed_text:
            print()
    return await event_stream.result()


def _format_binding(binding: ConsoleBinding) -> str:
    model = binding.model
    return f"{binding.provider_id}:{binding.endpoint_id}:{getattr(model, 'id', '<unknown>')}"


def _resolve_model_arg(
    registry,
    model_arg: str,
    *,
    provider: str | None,
    endpoint: str | None,
    api: str | None,
):
    if model_arg.count(":") == 2:
        p, e, mid = model_arg.split(":", 2)
        return registry.get_model(p, e, mid)
    if provider and endpoint:
        return registry.get_model(provider, endpoint, model_arg)
    if api:
        candidates = [
            (model.provider_id, model.endpoint_id)
            for model in registry.list_models(model_id=model_arg)
            if resolve_model_api(model, registry=registry) == api
        ]
        if len(candidates) == 1:
            p, e = candidates[0]
            return registry.get_model(p, e, model_arg)
        if len(candidates) > 1:
            print(
                "Ambiguous model for api; candidates:",
                ", ".join(f"{p}:{e}:{model_arg}" for p, e in candidates),
                file=sys.stderr,
            )
            sys.exit(2)
    resolved = registry.find_model(model_arg)
    if resolved is not None:
        return resolved
    return registry.get_model(model_arg)


def _resolve_model_with_env_fallback(
    registry,
    *,
    model_arg: str | None,
    provider: str | None,
    endpoint: str | None,
    api: str | None,
):
    if isinstance(model_arg, str) and model_arg:
        return _resolve_model_arg(
            registry, model_arg, provider=provider, endpoint=endpoint, api=api
        )
    env_binding = os.getenv("LOUSHANG_BINDING")
    if env_binding and env_binding.count(":") == 2:
        p, e, mid = env_binding.split(":", 2)
        return registry.get_model(p, e, mid)
    env_model = os.getenv("LOUSHANG_MODEL")
    if env_model:
        env_api = api or os.getenv("LOUSHANG_PROTOCOL") or None
        return _resolve_model_arg(
            registry, env_model, provider=None, endpoint=None, api=env_api
        )
    _hint_and_exit_for_missing_model(registry)


def _hint_and_exit_for_missing_model(registry) -> None:
    sample = None
    for model in registry.list_models():
        sample = f"{model.provider_id}:{model.endpoint_id}:{model.id}"
        break
    msg = (
        "Missing model selection. Provide one of:\n"
        "  - --model provider:endpoint:modelId\n"
        "  - --model modelId [--provider P --endpoint E | --api API]\n"
        "  - env LOUSHANG_BINDING=provider:endpoint:modelId\n"
        "  - env LOUSHANG_MODEL=modelId [and optional LOUSHANG_PROTOCOL]\n"
    )
    if sample:
        msg += f'Example:\n  loushang-ai chat --model {sample} --message "hi"\n'
    print(msg, file=sys.stderr)
    sys.exit(2)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="loushang-ai", description="Loushang AI CLI")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--base-url",
        help="Override provider base URL globally (applies to built-in OpenAI/Anthropic)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_apis = sub.add_parser("apis")
    sa = p_apis.add_subparsers(dest="action", required=True)
    sa.add_parser("list")
    pas = sa.add_parser("show")
    pas.add_argument("api")
    p_apis.set_defaults(func=cmd_apis)

    p_models = sub.add_parser("models")
    sm = p_models.add_subparsers(dest="action", required=True)
    pl = sm.add_parser("list")
    pl.add_argument("--provider")
    pl.add_argument("--api")
    ps = sm.add_parser("show")
    ps.add_argument("model")
    p_models.set_defaults(func=cmd_models)

    p_eps = sub.add_parser("endpoints")
    se = p_eps.add_subparsers(dest="action", required=True)
    se.add_parser("list").add_argument("--provider")
    pes = se.add_parser("show")
    pes.add_argument("target")
    p_eps.set_defaults(func=cmd_endpoints)

    p_chat = sub.add_parser("chat")
    p_chat.add_argument(
        "--model", help="模型ID或 provider:endpoint:modelId（可省略以用环境变量）"
    )
    p_chat.add_argument("--provider", help="提供商（与 --endpoint 一起使用以消歧）")
    p_chat.add_argument("--endpoint", help="端点（与 --provider 一起使用以消歧）")
    p_chat.add_argument("--api", help="按 API 消歧（如 openai-completions）")
    p_chat.add_argument("--message", required=True)
    p_chat.set_defaults(func=cmd_chat)

    p_comp = sub.add_parser("complete")
    p_comp.add_argument(
        "--model", help="模型ID或 provider:endpoint:modelId（可省略以用环境变量）"
    )
    p_comp.add_argument("--provider", help="提供商（与 --endpoint 一起使用以消歧）")
    p_comp.add_argument("--endpoint", help="端点（与 --provider 一起使用以消歧）")
    p_comp.add_argument("--api", help="按 API 消歧（如 openai-completions）")
    p_comp.add_argument("--message", required=True)
    p_comp.set_defaults(func=cmd_complete)

    p_auth = sub.add_parser("auth")
    sauth = p_auth.add_subparsers(dest="action", required=True)
    sauth.add_parser("providers")
    p_auth_show = sauth.add_parser("show")
    p_auth_show.add_argument("provider")
    p_auth_login = sauth.add_parser("login")
    p_auth_login.add_argument("provider", nargs="?")
    p_auth.set_defaults(func=cmd_auth)

    p_console = sub.add_parser("console")
    p_console.add_argument("--provider", help="预选 provider，未提供时交互选择")
    p_console.add_argument("--endpoint", help="预选 endpoint，未提供时交互选择")
    p_console.add_argument("--model", help="预选 model，未提供时交互选择")
    p_console.add_argument("--system-prompt", help="会话级 system prompt")
    p_console.add_argument(
        "--debug", action="store_true", help="打印当前绑定、鉴权来源和 provider trace"
    )
    p_console.set_defaults(func=cmd_console)

    args = parser.parse_args(argv)
    try:
        from loushang.ai import reset_api_providers

        env_base = os.getenv("LOUSHANG_BASE_URL")
        effective_base = args.base_url or env_base
        if effective_base:
            reset_api_providers(
                openai_base_url=effective_base,
                anthropic_base_url=effective_base,
            )
        else:
            reset_api_providers()
    except Exception:
        pass
    args.func(args)


if __name__ == "__main__":
    main()
