from loushang.coding.ui.follow_up_queue import FollowUpQueueHandler
from loushang.coding.ui.lifecycle import RunLifecycle
from loushang.coding.ui.steer import SteerHandler
from loushang.harnesstui.conversation.control import (
    ConversationRunControl,
    FollowUpActionHandler,
    SteerActionHandler,
)


def test_coding_action_control_names_preserve_shared_compatibility() -> None:
    assert RunLifecycle is ConversationRunControl
    assert issubclass(FollowUpQueueHandler, FollowUpActionHandler)
    assert SteerHandler is SteerActionHandler
