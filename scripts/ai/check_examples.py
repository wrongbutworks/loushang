from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples/ai"
LIVE_ENV_NAMES = (
    "ANTHROPIC_API_KEY",
    "ARK_API_KEY",
    "BAIDU_QIANFAN_API_KEY",
    "DASHSCOPE_API_KEY",
    "DEEPSEEK_API_KEY",
    "HUNYUAN_API_KEY",
    "MINIMAX_API_KEY",
    "MOONSHOT_API_KEY",
    "OPENAI_API_KEY",
    "QIANFAN_API_KEY",
    "STEPFUN_API_KEY",
    "STEP_API_KEY",
    "ZAI_API_KEY",
)


def main() -> int:
    errors = run_offline_examples()
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    print(f"OK offline examples={len(_offline_examples())}")
    return 0


def run_offline_examples() -> list[str]:
    errors: list[str] = []
    env = os.environ.copy()
    for env_name in LIVE_ENV_NAMES:
        env.pop(env_name, None)

    with TemporaryDirectory() as home:
        env["HOME"] = home
        for path in _offline_examples():
            completed = subprocess.run(
                [sys.executable, str(path)],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
            if completed.returncode != 0:
                errors.append(
                    f"{path.relative_to(REPO_ROOT)} failed with {completed.returncode}: "
                    f"{completed.stderr.strip() or completed.stdout.strip()}"
                )
                continue
            if not completed.stdout.strip():
                errors.append(f"{path.relative_to(REPO_ROOT)} produced no output")
    return errors


def _offline_examples() -> list[Path]:
    return [
        *sorted(EXAMPLES_DIR.glob("[0-9][0-9]_*.py")),
        EXAMPLES_DIR / "custom_model_file.py",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
