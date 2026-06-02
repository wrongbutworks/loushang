from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from loushang.coding.domain import CodingDomainPreparedTurn, CodingDomainRequest


def test_coding_domain_request_defaults() -> None:
    request = CodingDomainRequest(
        user_input="review this change",
        cwd=Path("/tmp/project"),
    )

    assert request.user_input == "review this change"
    assert request.cwd == Path("/tmp/project")
    assert request.method is None
    assert request.metadata == {}


def test_coding_domain_prepared_turn_defaults() -> None:
    prepared = CodingDomainPreparedTurn(prepared_prompt="review this change")

    assert prepared.prepared_prompt == "review this change"
    assert prepared.method_id is None
    assert prepared.method_guidance is None
    assert prepared.metadata == {}


def test_coding_domain_types_are_frozen() -> None:
    request = CodingDomainRequest(user_input="hello", cwd=Path("/tmp/project"))

    with pytest.raises(FrozenInstanceError):
        request.user_input = "changed"  # type: ignore[misc]
