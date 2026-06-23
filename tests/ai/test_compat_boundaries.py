from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_COMPAT_HELPERS = frozenset({"compat_bool", "compat_str"})
RAW_COMPAT_ATTRS = frozenset({"adapter_compat", "compat"})
RAW_COMPAT_RECEIVER_NAMES = frozenset(
    {"ctx", "provider_request", "request", "resolved", "resolved_request"}
)
CODEX_RUNTIME_COMPAT_KEYS = frozenset(
    {
        "codexIncludeClientRequestId",
        "codexIncludeConversationId",
        "codexPromptCacheRetention",
        "codexOriginator",
        "codexUserAgent",
    }
)
LOADER_COMPAT_HELPER_PATHS = frozenset(
    {
        "src/loushang/ai/model/compat_schema.py",
        "src/loushang/ai/model/loader.py",
    }
)
PROVIDER_COMPAT_SCHEMA_IMPORT_PATHS = frozenset()


def test_legacy_compat_helpers_are_loader_only() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "src/loushang/ai").rglob("*.py")):
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        if relative_path in LOADER_COMPAT_HELPER_PATHS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        offenders.extend(_legacy_helper_accesses(relative_path, tree))

    assert offenders == []


def test_legacy_compat_helper_detection_rejects_module_aliases() -> None:
    tree = ast.parse(
        "\n".join(
            (
                "import loushang.ai.model.compat_schema as schema",
                "from loushang.ai.model import compat_schema",
                "schema.compat_bool({}, 'x')",
                "compat_schema.compat_str({}, 'x')",
            )
        )
    )

    offenders = _legacy_helper_accesses("example.py", tree)

    assert "example.py imports loushang.ai.model.compat_schema" in offenders
    assert (
        "example.py imports loushang.ai.model.compat_schema via loushang.ai.model"
        in (offenders)
    )
    assert "example.py calls schema.compat_bool" in offenders
    assert "example.py calls compat_schema.compat_str" in offenders


def test_provider_compat_schema_detection_rejects_constant_imports() -> None:
    tree = ast.parse(
        "\n".join(
            (
                "from loushang.ai.model.compat_schema import CODEX_USER_AGENT",
                "import loushang.ai.model.compat_schema",
                "from loushang.ai.model import compat_schema as schema",
            )
        )
    )

    offenders = _compat_schema_imports("src/loushang/ai/providers/example.py", tree)

    assert (
        "src/loushang/ai/providers/example.py imports "
        "loushang.ai.model.compat_schema.CODEX_USER_AGENT"
    ) in offenders
    assert (
        "src/loushang/ai/providers/example.py imports loushang.ai.model.compat_schema"
    ) in offenders
    assert (
        "src/loushang/ai/providers/example.py imports "
        "loushang.ai.model.compat_schema via loushang.ai.model"
    ) in offenders


def test_provider_adapter_compat_detection_rejects_getattr() -> None:
    tree = ast.parse(
        "\n".join(
            (
                "adapter_compat = getattr(resolved, 'adapter_compat', {})",
                "compat = getattr(resolved, 'compat', {})",
                "provider_request_compat = provider_request.adapter_compat",
                "ctx_compat = ctx.compat",
                "alias = resolved",
                "alias_compat = alias.adapter_compat",
                "other = model.compat",
            )
        )
    )

    offenders = _adapter_compat_accesses("src/loushang/ai/providers/example.py", tree)

    assert "src/loushang/ai/providers/example.py reads adapter_compat" in offenders
    assert "src/loushang/ai/providers/example.py reads compat" in offenders
    assert (
        offenders.count("src/loushang/ai/providers/example.py reads adapter_compat")
        == 3
    )
    assert offenders.count("src/loushang/ai/providers/example.py reads compat") == 2
    assert "src/loushang/ai/providers/example.py reads model.compat" not in offenders


def test_raw_compat_key_detection_rejects_codex_runtime_keys() -> None:
    tree = ast.parse('CODEX_USER_AGENT = "codexUserAgent"')

    offenders = _raw_compat_key_literals("src/loushang/ai/providers/example.py", tree)

    assert (
        "src/loushang/ai/providers/example.py owns raw compat key codexUserAgent"
    ) in offenders


def test_provider_core_codex_runtime_detection_rejects_config_types() -> None:
    tree = ast.parse(
        "\n".join(
            (
                "from loushang.ai.model.compat_schema import CODEX_USER_AGENT",
                "value = OpenAICodexRuntimeConfig()",
                "other = resolve_openai_codex_runtime_config({}, None)",
            )
        )
    )

    offenders = _codex_runtime_core_accesses(
        "src/loushang/ai/provider/example.py",
        tree,
    )

    assert (
        "src/loushang/ai/provider/example.py imports "
        "loushang.ai.model.compat_schema.CODEX_USER_AGENT"
    ) in offenders
    assert (
        "src/loushang/ai/provider/example.py owns OpenAICodexRuntimeConfig"
    ) in offenders
    assert (
        "src/loushang/ai/provider/example.py owns resolve_openai_codex_runtime_config"
    ) in offenders


def test_providers_do_not_import_legacy_compat_schema() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "src/loushang/ai/providers").rglob("*.py")):
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        if relative_path in PROVIDER_COMPAT_SCHEMA_IMPORT_PATHS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        offenders.extend(_compat_schema_imports(relative_path, tree))

    assert offenders == []


def test_providers_do_not_read_legacy_adapter_compat() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "src/loushang/ai/providers").rglob("*.py")):
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        offenders.extend(_adapter_compat_accesses(relative_path, tree))

    assert offenders == []


def test_providers_do_not_own_raw_codex_runtime_compat_keys() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "src/loushang/ai/providers").rglob("*.py")):
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        offenders.extend(_raw_compat_key_literals(relative_path, tree))

    assert offenders == []


def test_provider_core_does_not_own_codex_runtime_config() -> None:
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "src/loushang/ai/provider").rglob("*.py")):
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative_path)
        offenders.extend(_codex_runtime_core_accesses(relative_path, tree))
        offenders.extend(_raw_compat_key_literals(relative_path, tree))

    assert offenders == []


def _legacy_helper_accesses(relative_path: str, tree: ast.AST) -> list[str]:
    offenders: list[str] = []
    compat_schema_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "loushang.ai.model.compat_schema":
                    compat_schema_aliases.add(alias.asname or "loushang")
                    offenders.append(
                        f"{relative_path} imports loushang.ai.model.compat_schema"
                    )
        if isinstance(node, ast.ImportFrom):
            if node.module == "loushang.ai.model.compat_schema":
                names = {alias.name for alias in node.names}
                if "*" in names:
                    offenders.append(
                        f"{relative_path} imports all names from compat_schema"
                    )
                    continue
                for helper_name in sorted(names & LEGACY_COMPAT_HELPERS):
                    offenders.append(f"{relative_path} imports {helper_name}")
            elif node.module == "loushang.ai.model":
                for alias in node.names:
                    if alias.name == "compat_schema":
                        compat_schema_aliases.add(alias.asname or alias.name)
                        offenders.append(
                            f"{relative_path} imports "
                            "loushang.ai.model.compat_schema via loushang.ai.model"
                        )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _dotted_name(node.func)
        if call_name is None:
            continue
        if not call_name.endswith(tuple(f".{name}" for name in LEGACY_COMPAT_HELPERS)):
            continue
        if call_name.split(".", 1)[0] in compat_schema_aliases:
            offenders.append(f"{relative_path} calls {call_name}")
        elif call_name.startswith("loushang.ai.model.compat_schema."):
            offenders.append(f"{relative_path} calls {call_name}")
    return offenders


def _compat_schema_imports(relative_path: str, tree: ast.AST) -> list[str]:
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "loushang.ai.model.compat_schema":
                    offenders.append(
                        f"{relative_path} imports loushang.ai.model.compat_schema"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module == "loushang.ai.model.compat_schema":
                names = {alias.name for alias in node.names}
                if "*" in names:
                    offenders.append(
                        f"{relative_path} imports all names from compat_schema"
                    )
                    continue
                for name in sorted(names):
                    offenders.append(
                        f"{relative_path} imports "
                        f"loushang.ai.model.compat_schema.{name}"
                    )
            elif node.module == "loushang.ai.model":
                for alias in node.names:
                    if alias.name == "compat_schema":
                        offenders.append(
                            f"{relative_path} imports "
                            "loushang.ai.model.compat_schema via loushang.ai.model"
                        )
    return offenders


def _adapter_compat_accesses(relative_path: str, tree: ast.AST) -> list[str]:
    offenders: list[str] = []
    request_compat_receivers = _request_compat_receivers(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in RAW_COMPAT_ATTRS:
            receiver = _dotted_name(node.value)
            if _is_request_compat_receiver(receiver, request_compat_receivers):
                offenders.append(f"{relative_path} reads {node.attr}")
            continue
        if not isinstance(node, ast.Call):
            continue
        call_name = _dotted_name(node.func)
        if call_name != "getattr" or len(node.args) < 2:
            continue
        receiver = _dotted_name(node.args[0])
        if not _is_request_compat_receiver(receiver, request_compat_receivers):
            continue
        attr_name = node.args[1]
        if isinstance(attr_name, ast.Constant) and attr_name.value in RAW_COMPAT_ATTRS:
            offenders.append(f"{relative_path} reads {attr_name.value}")
    return offenders


def _request_compat_receivers(tree: ast.AST) -> set[str]:
    receivers = set(RAW_COMPAT_RECEIVER_NAMES)
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            source = _dotted_name(node.value)
            if not _is_request_compat_receiver(source, receivers):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id not in receivers:
                    receivers.add(target.id)
                    changed = True
    return receivers


def _is_request_compat_receiver(name: str | None, receivers: set[str]) -> bool:
    if name is None:
        return False
    return name.split(".", 1)[0] in receivers


def _raw_compat_key_literals(relative_path: str, tree: ast.AST) -> list[str]:
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in CODEX_RUNTIME_COMPAT_KEYS:
            offenders.append(f"{relative_path} owns raw compat key {node.value}")
    return offenders


def _codex_runtime_core_accesses(relative_path: str, tree: ast.AST) -> list[str]:
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in {
            "OpenAICodexRuntimeConfig",
            "resolve_openai_codex_runtime_config",
        }:
            offenders.append(f"{relative_path} owns {node.id}")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "loushang.ai.model.compat_schema":
                names = {alias.name for alias in node.names}
                for name in sorted(names):
                    if name.startswith("CODEX_"):
                        offenders.append(
                            f"{relative_path} imports "
                            f"loushang.ai.model.compat_schema.{name}"
                        )
            elif node.module == "loushang.ai.contrib.openai_codex.runtime_config":
                for alias in node.names:
                    offenders.append(
                        f"{relative_path} imports "
                        f"loushang.ai.contrib.openai_codex.runtime_config.{alias.name}"
                    )
    return offenders


def _dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        if parent is None:
            return None
        return f"{parent}.{node.attr}"
    return None
