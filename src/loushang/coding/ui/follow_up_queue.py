from __future__ import annotations

from loushang.harnesstui.conversation.control import (
    ActiveRunControl as Lifecycle,
)
from loushang.harnesstui.conversation.control import (
    FollowUpActionHandler,
    StableEmit,
    TraceFn,
)
from loushang.harnesstui.conversation.control import (
    FollowUpController as Controller,
)
from loushang.harnesstui.conversation.control import (
    StatusRenderer as Renderer,
)


class FollowUpQueueHandler(FollowUpActionHandler):
    """Supply Coding status copy to shared follow-up action control."""

    def __init__(
        self,
        *,
        lifecycle: Lifecycle,
        controller: Controller,
        renderer: Renderer,
        emit: StableEmit,
        trace: TraceFn,
    ) -> None:
        super().__init__(
            lifecycle=lifecycle,
            controller=controller,
            renderer=renderer,
            emit=emit,
            trace=trace,
            idle_status_message=(
                "Follow-up is only available while a run is active."
            ),
            queued_status_message="Follow-up queued.",
        )


__all__ = ["FollowUpQueueHandler"]
