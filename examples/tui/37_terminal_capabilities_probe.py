from __future__ import annotations

from loushang.tui import (
    detect_terminal_capabilities,
    format_terminal_capability_diagnostics,
    terminal_environment_from_env,
)


def main() -> None:
    environment = terminal_environment_from_env()
    capabilities = detect_terminal_capabilities(environment)
    print("Loushang TUI terminal capabilities")
    print(format_terminal_capability_diagnostics(environment, capabilities))


if __name__ == "__main__":
    main()
