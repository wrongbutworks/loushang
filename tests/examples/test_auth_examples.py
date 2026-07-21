from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


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
