from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_openai_codex_live_example_uses_public_application_api() -> None:
    path = REPO_ROOT / "examples" / "auth" / "openai_codex_live_example.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name.startswith("loushang")
    ]

    assert imports == ["loushang.ai"]
    assert "ai.auth.get_auth(model)" in source
    assert "await ai.stream(" in source
    assert "OpenAICodexCredentialSource" not in source
    assert ".load(" not in source


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        (
            "api_key_example.py",
            {
                "calls": 1,
                "authenticated": True,
                "authType": "ApiKeyAuth",
            },
        ),
        (
            "oauth_status_login_example.py",
            {
                "beforeActions": ["login"],
                "browserOpenedByApplication": True,
                "loginProvider": "example-oauth",
                "authenticated": True,
                "requestAuthorized": True,
            },
        ),
        (
            "external_credential_source_example.py",
            {
                "authenticated": True,
                "experimental": True,
                "sourceDescription": "Use existing Codex CLI login",
                "recoveryHint": "Run codex login",
                "requestAuthorized": True,
                "accountHeaderResolved": True,
            },
        ),
    ],
)
def test_auth_example_runs(script: str, expected: dict[str, object]) -> None:
    completed = subprocess.run(
        [sys.executable, str(REPO_ROOT / "examples" / "auth" / script)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == expected
