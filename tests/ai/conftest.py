from __future__ import annotations

import os

import pytest

from loushang.ai.api_registry import get_default_api_provider_registry
from loushang.ai.bootstrap import register_builtin_ai_providers


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.getenv("LOUSHANG_AI_LIVE") == "1":
        return
    skip_live = pytest.mark.skip(reason="set LOUSHANG_AI_LIVE=1 to run live AI tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def _isolate_default_api_provider_registry():
    registry = get_default_api_provider_registry()
    registry.clear_api_providers()
    register_builtin_ai_providers(registry)
    yield
    registry.clear_api_providers()
    register_builtin_ai_providers(registry)
