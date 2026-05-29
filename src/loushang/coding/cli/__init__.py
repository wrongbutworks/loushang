from typing import Any

from loushang.coding.cli.args import CliArgs, parse_args

__all__ = ["CliArgs", "main", "parse_args", "run_cli"]


def __getattr__(name: str) -> Any:
    if name in {"main", "run_cli"}:
        from loushang.coding.cli import __main__

        return getattr(__main__, name)
    raise AttributeError(name)
