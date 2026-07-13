from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import cast


class JsonConfigStore:
    def __init__(
        self,
        *,
        encoding: str = "utf-8",
        ensure_ascii: bool = False,
        indent: int = 2,
        sort_keys: bool = True,
    ) -> None:
        self.encoding = encoding
        self.ensure_ascii = ensure_ascii
        self.indent = indent
        self.sort_keys = sort_keys

    def load(self, path: Path) -> Mapping[str, object]:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding=self.encoding))
        if not isinstance(payload, Mapping):
            raise ValueError(f"Config payload must be a JSON object: {path}")
        return cast(Mapping[str, object], payload)

    def save(self, path: Path, patch: Mapping[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            temp_path.write_text(
                json.dumps(
                    dict(patch),
                    ensure_ascii=self.ensure_ascii,
                    indent=self.indent,
                    sort_keys=self.sort_keys,
                ),
                encoding=self.encoding,
            )
            temp_path.replace(path)
        except BaseException:
            with suppress(FileNotFoundError):
                temp_path.unlink()
            raise


__all__ = ["JsonConfigStore"]
