from __future__ import annotations

import ast
from pathlib import Path


def test_legacy_agent_harness_package_reexports_top_level_harness() -> None:
    import loushang.agent.harness as legacy_harness
    import loushang.harness as canonical_harness

    assert legacy_harness.__all__ == [
        "AgentEventSink",
        "AgentRunMode",
        "AgentRunResult",
        "AgentRunSpec",
        "AgentRunStatus",
        "run_agent",
    ]
    for name in legacy_harness.__all__:
        assert getattr(legacy_harness, name) is getattr(canonical_harness, name)


def test_legacy_agent_harness_types_reexports_top_level_harness_types() -> None:
    import loushang.agent.harness.types as legacy_types
    import loushang.harness as canonical_harness

    assert legacy_types.__all__ == [
        "AgentEventSink",
        "AgentRunMode",
        "AgentRunResult",
        "AgentRunSpec",
        "AgentRunStatus",
    ]
    for name in legacy_types.__all__:
        assert getattr(legacy_types, name) is getattr(canonical_harness, name)


def test_legacy_agent_harness_runner_reexports_top_level_runner() -> None:
    import loushang.agent.harness.runner as legacy_runner
    import loushang.harness as canonical_harness

    assert legacy_runner.__all__ == ["run_agent"]
    for name in legacy_runner.__all__:
        assert getattr(legacy_runner, name) is getattr(canonical_harness, name)


def test_agent_run_contract_has_single_source_definition() -> None:
    definitions: list[str] = []
    for path in sorted(Path("src/loushang").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in {
                "AgentRunSpec",
                "AgentRunResult",
            }:
                definitions.append(f"{path.as_posix()}:{node.name}")

    assert definitions == [
        "src/loushang/harness/types.py:AgentRunSpec",
        "src/loushang/harness/types.py:AgentRunResult",
    ]
