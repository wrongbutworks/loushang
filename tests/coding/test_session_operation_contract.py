from __future__ import annotations

from loushang.coding.ui.product_binding import (
    build_coding_session_operation_resolver,
)
from loushang.harness.session import SessionOperationAvailability
from tests.harness.session.operation_contract import (
    CurrentSessionSlot,
    SessionOperationContract,
)


class TestCodingSessionOperationContract(SessionOperationContract):
    @staticmethod
    def resolver_factory(
        slot: CurrentSessionSlot,
        availability: SessionOperationAvailability | None,
    ):
        return build_coding_session_operation_resolver(
            session=slot.current_session,
            runtime=slot,
            availability=availability,
        )
