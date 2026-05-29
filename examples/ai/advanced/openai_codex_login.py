"""OpenAI Codex 手工登录示例。

推荐直接使用：

- `uv run python -m loushang.ai.cli auth login openai-codex`

这个脚本只是对 CLI 入口的薄包装。
"""

from __future__ import annotations

import subprocess
import sys


if __name__ == "__main__":
    try:
        raise SystemExit(
            subprocess.call(
                [sys.executable, "-m", "loushang.ai.cli", "auth", "login", "openai-codex"]
            )
        )
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
