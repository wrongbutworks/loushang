# Detect OS
ifeq ($(OS),Windows_NT)
    DETECTED_OS := Windows
    EXE_EXT := .exe
    RM := del /Q
    RMDIR := rmdir /S /Q
    INSTALL_DIR := $(USERPROFILE)/bin
else
    DETECTED_OS := $(shell uname -s)
    EXE_EXT :=
    RM := rm -f
    RMDIR := rm -rf
    INSTALL_DIR := $(HOME)/.local/bin
endif

BINARY_NAME := loushang$(EXE_EXT)
DIST_BINARY := dist/$(BINARY_NAME)
AI_OFFLINE_ENV := env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u ANTHROPIC_OAUTH_TOKEN -u ANTHROPIC_BASE_URL -u ARK_API_KEY -u BAIDU_QIANFAN_API_KEY -u COPILOT_GITHUB_TOKEN -u DASHSCOPE_API_KEY -u DEEPSEEK_API_KEY -u GH_TOKEN -u GITHUB_TOKEN -u HUNYUAN_API_KEY -u MINIMAX_API_KEY -u MOONSHOT_API_KEY -u OPENAI_API_KEY -u QIANFAN_API_KEY -u STEPFUN_API_KEY -u STEP_API_KEY -u ZAI_API_KEY

HARNESSTUI_SHARED_SOURCES := \
	src/loushang/tui/clipboard_image.py \
	src/loushang/tui/playback_suite.py \
	src/loushang/tui/settings.py \
	src/loushang/tui/terminal_diagnostics.py \
	src/loushang/harnesstui
HARNESSTUI_CODING_ADAPTERS := \
	src/loushang/coding/platform/__init__.py \
	src/loushang/coding/platform/clipboard_image.py \
	src/loushang/coding/testing/tui \
	src/loushang/coding/ui/abort.py \
	src/loushang/coding/ui/command_list.py \
	src/loushang/coding/ui/completion.py \
	src/loushang/coding/ui/conversation_event_adapter.py \
	src/loushang/coding/ui/event_stream.py \
	src/loushang/coding/ui/follow_up_queue.py \
	src/loushang/coding/ui/handlers.py \
	src/loushang/coding/ui/lifecycle.py \
	src/loushang/coding/ui/model_list.py \
	src/loushang/coding/ui/pending_queue.py \
	src/loushang/coding/ui/perf_probe.py \
	src/loushang/coding/ui/plain_app.py \
	src/loushang/coding/ui/plain_events.py \
	src/loushang/coding/ui/plain_renderer.py \
	src/loushang/coding/ui/plain_toolbar.py \
	src/loushang/coding/ui/playback.py \
	src/loushang/coding/ui/playback_fakes.py \
	src/loushang/coding/ui/playback_runner.py \
	src/loushang/coding/ui/playback_scenarios \
	src/loushang/coding/ui/playback_suite.py \
	src/loushang/coding/ui/prompt_dispatch.py \
	src/loushang/coding/ui/prompt_result.py \
	src/loushang/coding/ui/run_context.py \
	src/loushang/coding/ui/screen_app.py \
	src/loushang/coding/ui/screen_events.py \
	src/loushang/coding/ui/screen_input.py \
	src/loushang/coding/ui/screen_loop.py \
	src/loushang/coding/ui/screen_state.py \
	src/loushang/coding/ui/screen_surfaces.py \
	src/loushang/coding/ui/settings_common.py \
	src/loushang/coding/ui/settings_config.py \
	src/loushang/coding/ui/settings_page.py \
	src/loushang/coding/ui/settings_status_line.py \
	src/loushang/coding/ui/status_line.py \
	src/loushang/coding/ui/steer.py \
	src/loushang/coding/ui/tool_blocks.py \
	src/loushang/coding/ui/transcript_projection.py \
	src/loushang/coding/ui/transcript_style.py \
	src/loushang/coding/ui/transcript_reader.py \
	src/loushang/coding/ui/transcript_source.py
HARNESSTUI_TEST_PATHS := \
	tests/harnesstui \
	tests/tui/test_clipboard_image.py \
	tests/tui/test_import_boundaries.py \
	tests/tui/test_playback_suite.py \
	tests/tui/test_settings.py \
	tests/tui/test_terminal_diagnostics.py \
	tests/architecture/test_import_boundaries.py \
	tests/coding/test_coding_tui_playback_compatibility.py \
	tests/coding/test_playback_suite_compatibility.py \
	tests/coding/test_platform_utils.py \
	tests/coding/test_terminal_diagnostics_compatibility.py \
	tests/coding/test_ui_handlers.py \
	tests/coding/test_ui_abort.py \
	tests/coding/test_ui_event_stream.py \
	tests/coding/test_ui_follow_up_queue.py \
	tests/coding/test_ui_lifecycle.py \
	tests/coding/test_ui_pending_queue.py \
	tests/coding/test_ui_pending_queue_compatibility.py \
	tests/coding/test_ui_perf_probe_compatibility.py \
	tests/coding/test_ui_prompt_dispatch.py \
	tests/coding/test_ui_prompt_result.py \
	tests/coding/test_ui_run_context.py \
	tests/coding/test_ui_steer.py \
	tests/coding/test_ui_import_boundaries.py \
	tests/coding/test_screen_coding_tui_app.py \
	tests/coding/test_screen_coding_tui_events.py \
	tests/coding/test_screen_coding_tui_input.py \
	tests/coding/test_screen_coding_tui_loop.py \
	tests/coding/test_screen_coding_tui_mode.py \
	tests/coding/test_screen_coding_tui_perf_probe.py \
	tests/coding/test_screen_coding_tui_state.py \
	tests/coding/test_screen_coding_tui_surfaces.py \
	tests/coding/test_screen_settings_page.py \
	tests/coding/test_screen_tui_playback_runner.py \
	tests/coding/test_screen_tui_transcript_reader.py \
	tests/coding/test_tool_transcript_blocks.py \
	tests/coding/test_ui_command_list.py \
	tests/coding/test_ui_completion.py \
	tests/coding/test_ui_conversation_event_adapter.py \
	tests/coding/test_ui_control_compatibility.py \
	tests/coding/test_ui_dispatch_compatibility.py \
	tests/coding/test_ui_model_list.py \
	tests/coding/test_ui_plain_app.py \
	tests/coding/test_ui_plain_toolbar.py \
	tests/coding/test_ui_plain_renderer.py \
	tests/coding/test_ui_status_line.py \
	tests/coding/test_ui_status_provider.py \
	tests/coding/test_ui_transcript_projection.py \
	tests/coding/test_ui_transcript_style_compatibility.py \
	tests/coding/test_ui_transcript_source.py \
	tests/coding/ui/test_screen_input.py

.PHONY: bootstrap test test-ai check-ai test-tui test-tui-render-contract lint-ai fmt-ai typecheck-ai typecheck-tui build-binary install-binary clean-binary vendor-ai-moonshot-anthropic-stream vendor-ai-moonshot-anthropic-complete vendor-ai-moonshot-anthropic-tools vendor-ai-moonshot-openai-stream vendor-ai-moonshot-openai-complete vendor-ai-moonshot-openai-tools vendor-ai-dashscope-openai-responses-stream vendor-ai-dashscope-openai-responses-tools vendor-ai-openai-codex-complete example-ai-model-lookup example-ai-complete example-ai-stream example-ai-tools example-ai-typed-context example-ai-advanced-faux-stream example-ai-advanced-context-tools example-ai-advanced-tool-result-roundtrip example-ai-advanced-openai-codex-login example-ai-kimi-anthropic-stream example-ai-kimi-anthropic-complete example-ai-kimi-anthropic-tools example-ai-kimi-openai-stream example-ai-kimi-openai-complete example-ai-kimi-openai-tools example-ai-dashscope-openai-responses-stream example-ai-dashscope-openai-responses-tools example-ai-custom-base-url-openai-advanced example-ai-faux-stream example-ai-context-tools-minimal example-ai-tool-result-roundtrip
.PHONY: check-ai-catalog check-ai-examples check-ai-imports check-ai-coverage
.PHONY: check-harnesstui lint-harnesstui typecheck-harnesstui test-harnesstui

bootstrap:
	test -d .venv || uv venv .venv
	. .venv/bin/activate && uv pip install -e .[dev]

test:
	. .venv/bin/activate && uv run pytest tests -q

test-ai:
	. .venv/bin/activate && $(AI_OFFLINE_ENV) uv run pytest tests/ai tests/providers -m "not live" -q

check-ai: lint-ai typecheck-ai check-ai-catalog check-ai-imports check-ai-examples check-ai-coverage

check-ai-catalog:
	uv run python scripts/ai/check_catalog.py

check-ai-imports:
	uv run python scripts/ai/check_import_boundaries.py

check-ai-examples:
	$(AI_OFFLINE_ENV) uv run python scripts/ai/check_examples.py

check-ai-coverage:
	mkdir -p .artifacts/ai
	. .venv/bin/activate && $(AI_OFFLINE_ENV) uv run pytest tests/ai tests/providers -m "not live" --cov=src/loushang/ai --cov-report=term-missing:skip-covered --cov-report=xml:.artifacts/ai/coverage.xml --cov-fail-under=80 -q
	uv run python scripts/ai/check_coverage_targets.py .artifacts/ai/coverage.xml

check-harnesstui: lint-harnesstui typecheck-harnesstui test-harnesstui

lint-harnesstui:
	uv --cache-dir .uv-cache run --extra dev ruff check $(HARNESSTUI_SHARED_SOURCES) $(HARNESSTUI_CODING_ADAPTERS) src/loushang/coding/ui/status_provider.py $(HARNESSTUI_TEST_PATHS)

typecheck-harnesstui:
	uv --cache-dir .uv-cache run --extra dev mypy --follow-imports=silent $(HARNESSTUI_SHARED_SOURCES) $(HARNESSTUI_CODING_ADAPTERS) src/loushang/coding/ui/status_provider.py

test-harnesstui:
	uv --cache-dir .uv-cache run --extra dev pytest $(HARNESSTUI_TEST_PATHS) -m "not tui_render_contract" -q

test-tui:
	. .venv/bin/activate && python -m pytest tests/tui -q

test-tui-render-contract:
	uv --cache-dir .uv-cache run pytest tests/tui tests/harnesstui tests/coding -m tui_render_contract -q

lint-ai:
	. .venv/bin/activate && uv run ruff check src/loushang/ai tests/ai tests/providers

fmt-ai:
	. .venv/bin/activate && uv run ruff format src/loushang/ai tests/ai tests/providers

typecheck-ai:
	. .venv/bin/activate && uv run mypy

vendor-ai-moonshot-anthropic-stream:
	uv run pytest tests/ai/vendors/moonshot/test_kimi_anthropic_stream_live.py -q -s

typecheck-tui:
	. .venv/bin/activate && mypy src/loushang/tui

example-ai-kimi-anthropic-stream:
	uv run python examples/ai/kimi_anthropic_stream.py

vendor-ai-moonshot-anthropic-complete:
	uv run pytest tests/ai/vendors/moonshot/test_kimi_anthropic_complete_live.py -q -s

vendor-ai-moonshot-anthropic-tools:
	uv run pytest tests/ai/vendors/moonshot/test_kimi_anthropic_tools_live.py -q -s

vendor-ai-moonshot-openai-complete:
	uv run pytest tests/ai/vendors/moonshot/test_kimi_openai_complete_live.py -q -s

vendor-ai-moonshot-openai-stream:
	uv run pytest tests/ai/vendors/moonshot/test_kimi_openai_stream_live.py -q -s

vendor-ai-moonshot-openai-tools:
	uv run pytest tests/ai/vendors/moonshot/test_kimi_openai_tools_live.py -q -s

vendor-ai-dashscope-openai-responses-stream:
	uv run pytest tests/ai/vendors/dashscope/test_openai_responses_stream_live.py -q -s

vendor-ai-dashscope-openai-responses-tools:
	uv run pytest tests/ai/vendors/dashscope/test_openai_responses_tools_live.py -q -s

vendor-ai-openai-codex-complete:
	uv run pytest tests/ai/vendors/openai_codex/test_complete_live.py -q -s

.PHONY: example-ai-offline example-ai-provider-matrix example-ai-provider-smoke

example-ai-offline:
	for path in examples/ai/[0-9][0-9]_*.py; do uv run python "$$path"; done

example-ai-model-lookup: example-ai-provider-matrix

example-ai-provider-matrix:
	uv run python examples/ai/11_provider_matrix.py

example-ai-provider-smoke:
	uv run python examples/ai/12_provider_smoke.py

example-ai-complete:
	uv run python examples/ai/01_complete.py

example-ai-stream:
	uv run python examples/ai/02_stream.py

example-ai-tools:
	uv run python examples/ai/04_tools.py

example-ai-typed-context:
	uv run python examples/ai/03_typed_context.py

example-ai-advanced-faux-stream:
	uv run python examples/ai/advanced/faux_stream.py

example-ai-advanced-context-tools:
	uv run python examples/ai/advanced/context_tools_minimal.py

example-ai-advanced-tool-result-roundtrip:
	uv run python examples/ai/advanced/tool_result_roundtrip.py

example-ai-advanced-openai-codex-login:
	uv run python examples/ai/advanced/openai_codex_login.py

# ---------------------------------------------------------------------------
# Binary build / install (cross-platform)
# ---------------------------------------------------------------------------

build-binary: bootstrap
	uv pip install --python .venv/bin/python pyinstaller
	. .venv/bin/activate && uv run python -m PyInstaller --onefile --name loushang --collect-data loushang --paths src src/loushang/coding/cli/__main__.py

install-binary: build-binary
ifeq ($(DETECTED_OS),Windows)
	@if not exist "$(INSTALL_DIR)" mkdir "$(INSTALL_DIR)"
	copy /Y "$(DIST_BINARY)" "$(INSTALL_DIR)\$(BINARY_NAME)"
	@echo Installed to $(INSTALL_DIR)\$(BINARY_NAME)
else
	mkdir -p $(INSTALL_DIR)
	cp $(DIST_BINARY) $(INSTALL_DIR)/$(BINARY_NAME)
	@echo Installed to $(INSTALL_DIR)/$(BINARY_NAME)
	@echo 'Make sure $(INSTALL_DIR) is in your $$PATH'
endif

clean-binary:
	$(RMDIR) build/
	$(RM) dist/$(BINARY_NAME)
