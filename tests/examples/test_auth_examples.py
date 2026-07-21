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
                "calls": 2,
                "environmentResolved": True,
                "explicitResolved": True,
                "requestAuthTypes": ["ApiKeyAuth", "ApiKeyAuth"],
            },
        ),
        (
            "oauth_credential_file_example.py",
            {
                "credentialFile": "example-oauth-auth.json",
                "authorizationResolved": True,
                "extraHeaderResolved": True,
                "requestAuthType": "OAuthBearerAuth",
                "lifecycleCredentialCleared": True,
            },
        ),
        (
            "oauth_status_login_example.py",
            {
                "before": "missing",
                "loginReturnedProvider": "example-oauth",
                "afterLogin": "valid",
                "authenticated": True,
                "logoutDeletedCredential": True,
                "afterLogout": "missing",
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
