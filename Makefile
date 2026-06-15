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

.PHONY: bootstrap test test-ai check-ai test-tui test-tui-v1 lint-ai fmt-ai typecheck-ai typecheck-tui build-binary install-binary clean-binary vendor-ai-moonshot-anthropic-stream vendor-ai-moonshot-anthropic-complete vendor-ai-moonshot-anthropic-tools vendor-ai-moonshot-openai-stream vendor-ai-moonshot-openai-complete vendor-ai-moonshot-openai-tools vendor-ai-dashscope-openai-responses-stream vendor-ai-dashscope-openai-responses-tools vendor-ai-moonshot-custom-base-url-openai vendor-ai-openai-codex-complete example-ai-model-lookup example-ai-complete example-ai-stream example-ai-tools example-ai-typed-context example-ai-advanced-faux-stream example-ai-advanced-context-tools example-ai-advanced-tool-result-roundtrip example-ai-advanced-openai-codex-login example-ai-kimi-anthropic-stream example-ai-kimi-anthropic-complete example-ai-kimi-anthropic-tools example-ai-kimi-openai-stream example-ai-kimi-openai-complete example-ai-kimi-openai-tools example-ai-dashscope-openai-responses-stream example-ai-dashscope-openai-responses-tools example-ai-custom-base-url-openai-advanced example-ai-faux-stream example-ai-context-tools-minimal example-ai-tool-result-roundtrip

bootstrap:
	test -d .venv || uv venv .venv
	. .venv/bin/activate && uv pip install -e .[dev]

test:
	. .venv/bin/activate && uv run pytest tests -q

test-ai:
	. .venv/bin/activate && uv run pytest tests/ai tests/providers -q

check-ai: lint-ai typecheck-ai test-ai

test-tui:
	. .venv/bin/activate && python -m pytest tests/tui -q

test-tui-v1:
	uv --cache-dir .uv-cache run python scripts/check_tui_v1.py

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

vendor-ai-moonshot-custom-base-url-openai:
	uv run pytest tests/ai/vendors/moonshot/test_custom_base_url_openai_live.py -q -s

vendor-ai-openai-codex-complete:
	uv run pytest tests/ai/vendors/openai_codex/test_complete_live.py -q -s

example-ai-model-lookup:
	uv run python examples/ai/model_lookup.py

example-ai-complete:
	uv run python examples/ai/complete.py

example-ai-stream:
	uv run python examples/ai/stream.py

example-ai-tools:
	uv run python examples/ai/tools.py

example-ai-typed-context:
	uv run python examples/ai/typed_context.py

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
