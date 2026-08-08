from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

FOUNDATION_ROOT = Path("src/loushang/foundation")
PROTOCOL_ROOT = Path("src/loushang/protocol")
OBSERVABILITY_COMPATIBILITY_ROOT = Path("src/loushang/observability")
CANONICAL_OBSERVABILITY_ROOT = FOUNDATION_ROOT / "observability"

_BASELINE_PROTOCOL_IMPORTERS = frozenset(
    {
        "src/loushang/agent/agent_loop.py",
        "src/loushang/agent/json_codec.py",
        "src/loushang/agent/tool_output.py",
        "src/loushang/agent/types.py",
        "src/loushang/ai/json_codec.py",
        "src/loushang/ai/types.py",
        "src/loushang/channel/json_codec.py",
        "src/loushang/channel/rpc_jsonl.py",
        "src/loushang/coding/session_manager.py",
        "src/loushang/harness/context/usage.py",
        "src/loushang/harness/continuity/types.py",
        "src/loushang/harness/conversation/jsonl_codec.py",
        "src/loushang/harness/conversation/types.py",
        "src/loushang/harness/events/projection.py",
        "src/loushang/harness/host/json_projection.py",
        "src/loushang/harness/host/jsonl_command_host.py",
        "src/loushang/harness/journal/jsonl.py",
        "src/loushang/harness/runtime/_profile_admission.py",
        "src/loushang/harness/runtime/_profile_binding.py",
        "src/loushang/harness/runtime/_profile_resolution.py",
        "src/loushang/harness/runtime/_profile_types.py",
        "src/loushang/harness/session/diagnostics.py",
        "src/loushang/harness/session/event_projection.py",
        "src/loushang/harness/session/event_serialization.py",
        "src/loushang/harness/session/export.py",
        "src/loushang/harness/transcript/codecs.py",
        "src/loushang/harness/transcript/committer.py",
        "src/loushang/harness/transcript/compaction.py",
        "src/loushang/harness/transcript/export/html.py",
        "src/loushang/harness/transcript/interaction.py",
        "src/loushang/harness/transcript/migration.py",
        "src/loushang/harness/transcript/product_session.py",
        "src/loushang/harness/transcript/runtime_profile.py",
        "src/loushang/harness/transcript/session.py",
        "src/loushang/harness/transcript/session_factory.py",
        "src/loushang/harness/transcript/summarization.py",
        "src/loushang/harness/transcript/types.py",
        "src/loushang/harness/transcript/unit_of_work.py",
        "src/loushang/harness/transcript/writer.py",
        "src/loushang/harnesstui/conversation/plain_mode.py",
        "src/loushang/harnesswork/event_log.py",
        "src/loushang/harnesswork/integrations/agent_session.py",
        "src/loushang/ontology/integrations/harnesswork.py",
    }
)

_BASELINE_OBSERVABILITY_IMPORTERS = frozenset(
    {
        "src/loushang/ai/errors.py",
        "src/loushang/ai/structured.py",
        "src/loushang/coding/diagnostics/debug_status.py",
        "src/loushang/coding/diagnostics/profile.py",
        "src/loushang/harness/diagnostics/observability_bridge.py",
        "src/loushang/harness/diagnostics/observability_runtime.py",
    }
)


def test_foundation_uses_only_stdlib_and_relative_imports() -> None:
    failures: list[str] = []
    for path in FOUNDATION_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    if root not in sys.stdlib_module_names:
                        failures.append(f"{path.as_posix()} imports {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level or not node.module:
                    continue
                root = node.module.split(".", 1)[0]
                if root not in sys.stdlib_module_names:
                    failures.append(f"{path.as_posix()} imports {node.module}")

    assert failures == []


def test_foundation_json_import_does_not_load_observability() -> None:
    source_root = str(Path("src").resolve())
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (source_root, environment.get("PYTHONPATH", ""))
        if value
    )
    command = (
        "import sys; import loushang.foundation.json; "
        "assert not any(name == 'loushang.observability' or "
        "name.startswith('loushang.observability.') or "
        "name == 'loushang.foundation.observability' or "
        "name.startswith('loushang.foundation.observability.') "
        "for name in sys.modules)"
    )

    subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        cwd=Path.cwd(),
        env=environment,
    )


def test_protocol_compatibility_modules_define_no_runtime_implementation() -> None:
    assert _runtime_implementation_modules(PROTOCOL_ROOT) == []


def test_observability_compatibility_modules_define_no_runtime_implementation() -> None:
    assert _runtime_implementation_modules(OBSERVABILITY_COMPATIBILITY_ROOT) == []


def test_canonical_observability_compatibility_modules_define_no_runtime_implementation() -> None:
    compatibility_modules = (
        CANONICAL_OBSERVABILITY_ROOT / "problem.py",
        CANONICAL_OBSERVABILITY_ROOT / "sinks.py",
    )

    assert _runtime_implementation_paths(compatibility_modules) == []


def test_canonical_observability_router_does_not_depend_on_concrete_sinks() -> None:
    router_imports = _relative_import_targets(
        CANONICAL_OBSERVABILITY_ROOT / "_router.py"
    )
    assert router_imports.isdisjoint({"debug_log", "logger", "runtime", "trace"})

    for module_name in ("debug_log", "trace"):
        sink_imports = _relative_import_targets(
            CANONICAL_OBSERVABILITY_ROOT / f"{module_name}.py"
        )
        assert "records" in sink_imports
        assert "_router" not in sink_imports


def test_legacy_protocol_importers_do_not_expand() -> None:
    actual_importers = {
        path.as_posix()
        for path in Path("src/loushang").rglob("*.py")
        if not path.is_relative_to(PROTOCOL_ROOT)
        if _imports_legacy_protocol(path)
    }

    assert actual_importers <= _BASELINE_PROTOCOL_IMPORTERS


def test_legacy_observability_importers_do_not_expand() -> None:
    actual_importers = {
        path.as_posix()
        for path in Path("src/loushang").rglob("*.py")
        if not path.is_relative_to(OBSERVABILITY_COMPATIBILITY_ROOT)
        if _imports_legacy_observability(path)
    }

    assert actual_importers <= _BASELINE_OBSERVABILITY_IMPORTERS


def _runtime_implementation_modules(root: Path) -> list[str]:
    return _runtime_implementation_paths(root.rglob("*.py"))


def _runtime_implementation_paths(paths) -> list[str]:
    forbidden_nodes = (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef)
    offenders: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(isinstance(node, forbidden_nodes) for node in ast.walk(tree)):
            offenders.append(path.as_posix())
    return offenders


def _relative_import_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level
    }


def _imports_legacy_protocol(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.startswith("loushang.protocol") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("loushang.protocol"):
                return True
            if node.module == "loushang" and any(
                alias.name == "protocol" for alias in node.names
            ):
                return True
    return False


def _imports_legacy_observability(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.name.startswith("loushang.observability")
                for alias in node.names
            ):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("loushang.observability"):
                return True
            if node.module == "loushang" and any(
                alias.name == "observability" for alias in node.names
            ):
                return True
    return False
