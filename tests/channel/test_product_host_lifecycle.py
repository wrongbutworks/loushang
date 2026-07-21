from __future__ import annotations

from io import StringIO

from loushang.channel import ProductHostLifecycle


def test_product_host_lifecycle_resolves_injected_streams() -> None:
    stdin = StringIO("input\n")
    stdout = StringIO()
    stderr = StringIO()

    lifecycle = ProductHostLifecycle.resolve(
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
    )

    assert lifecycle.streams.stdin is stdin
    assert lifecycle.streams.stdout is stdout
    assert lifecycle.streams.stderr is stderr


def test_product_host_lifecycle_output_guard_is_optional() -> None:
    lifecycle = ProductHostLifecycle.resolve(
        stdout=StringIO(),
        stderr=StringIO(),
    )

    with lifecycle.output_guard(enabled=False):
        assert lifecycle.streams.stdout.getvalue() == ""
