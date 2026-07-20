from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from types import ModuleType


class _FakeImage:
    mode = "RGB"

    def __init__(self, width: int, height: int, *, byte_scale: int = 1) -> None:
        self.width = width
        self.height = height
        self.byte_scale = byte_scale
        self.closed = False

    def __enter__(self) -> "_FakeImage":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        self.closed = True

    def copy(self) -> "_FakeImage":
        return _FakeImage(self.width, self.height, byte_scale=self.byte_scale)

    def convert(self, mode: str) -> "_FakeImage":
        converted = self.copy()
        converted.mode = mode
        return converted

    def thumbnail(self, size: tuple[int, int], resample: object = None) -> None:
        del resample
        max_width, max_height = size
        scale = min(max_width / self.width, max_height / self.height, 1)
        self.width = max(1, round(self.width * scale))
        self.height = max(1, round(self.height * scale))

    def save(
        self, buffer, *, format: str, quality: int | None = None, optimize: bool = False
    ) -> None:
        del format, quality, optimize
        buffer.write(b"x" * (self.width * self.height * self.byte_scale))


def _install_fake_pillow(
    monkeypatch, image: _FakeImage, *, transpose_to: _FakeImage | None = None
) -> list[_FakeImage]:
    opened_images: list[_FakeImage] = []
    pil_module = ModuleType("PIL")
    image_module = ModuleType("PIL.Image")
    image_ops_module = ModuleType("PIL.ImageOps")

    class Resampling:
        LANCZOS = object()

    def open_image(_payload) -> _FakeImage:
        opened_images.append(image)
        return image

    def exif_transpose(opened: _FakeImage) -> _FakeImage:
        return transpose_to if transpose_to is not None else opened

    image_module.open = open_image  # type: ignore[attr-defined]
    image_module.Resampling = Resampling  # type: ignore[attr-defined]
    image_ops_module.exif_transpose = exif_transpose  # type: ignore[attr-defined]
    pil_module.Image = image_module  # type: ignore[attr-defined]
    pil_module.ImageOps = image_ops_module  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "PIL", pil_module)
    monkeypatch.setitem(sys.modules, "PIL.Image", image_module)
    monkeypatch.setitem(sys.modules, "PIL.ImageOps", image_ops_module)
    return opened_images


def test_pillow_resizer_progressively_reduces_dimensions_until_payload_fits(
    monkeypatch,
) -> None:
    from loushang.harness.tools.workspace import PillowReadImageResizer

    _install_fake_pillow(monkeypatch, _FakeImage(16, 16))
    resizer = PillowReadImageResizer(
        max_width=8,
        max_height=8,
        max_base64_bytes=20,
        jpeg_qualities=(80,),
    )

    result = resizer.resize_image(
        b"payload", mime_type="image/png", dimensions=(16, 16)
    )

    assert result is not None
    assert result.original_dimensions == (16, 16)
    assert result.dimensions == (3, 3)
    assert result.was_resized is True


def test_pillow_resizer_applies_exif_transpose_before_resizing(monkeypatch) -> None:
    from loushang.harness.tools.workspace import PillowReadImageResizer

    opened = _FakeImage(16, 8)
    transposed = _FakeImage(8, 16)
    _install_fake_pillow(monkeypatch, opened, transpose_to=transposed)
    resizer = PillowReadImageResizer(
        max_width=8,
        max_height=8,
        max_base64_bytes=200,
        jpeg_qualities=(80,),
    )

    result = resizer.resize_image(
        b"payload", mime_type="image/jpeg", dimensions=(16, 8)
    )

    assert result is not None
    assert result.original_dimensions == (8, 16)
    assert result.dimensions == (4, 8)
    assert result.was_resized is True


def test_default_pillow_resizer_backend_is_available_from_runtime_dependency() -> None:
    from loushang.harness.tools.workspace import PillowReadImageResizer

    assert PillowReadImageResizer().is_available() is True


def test_pillow_is_declared_as_runtime_dependency() -> None:
    project_root = Path(__file__).resolve().parents[2]
    pyproject = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = pyproject["project"]["dependencies"]

    assert any(dependency.lower().startswith("pillow") for dependency in dependencies)
