from loushang.coding.ui import pending_queue as coding_queue
from loushang.harnesstui.conversation import queue as shared_queue


def test_coding_pending_queue_exports_shared_implementations_by_identity() -> None:
    assert coding_queue.cleared_queue_messages is shared_queue.cleared_queue_messages
    assert coding_queue.pending_queue_view is shared_queue.pending_queue_view
    assert coding_queue.restore_queued_messages is shared_queue.restore_queued_messages
    assert coding_queue.session_pending_messages is shared_queue.session_pending_messages
