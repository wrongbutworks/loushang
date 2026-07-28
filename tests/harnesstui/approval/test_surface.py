from __future__ import annotations

from loushang.harness.approval import (
    ApprovalPermission,
    ApprovalPermissionsSnapshot,
)
from loushang.harnesstui.approval import build_permissions_surface_view
from loushang.tui import InputEvent, InputIntent


def test_permissions_surface_reopens_pending_and_revokes_grants() -> None:
    view = build_permissions_surface_view(
        ApprovalPermissionsSnapshot(
            pending=(
                ApprovalPermission(
                    kind="pending",
                    permission_id="approval-1",
                    actor_id="root",
                    capability="bash",
                    summary="Filesystem content would be deleted",
                ),
            ),
            grants=(
                ApprovalPermission(
                    kind="grant",
                    permission_id="grant-1",
                    actor_id="root",
                    capability="git.publish_refs",
                    summary="Publish non-force refs to origin",
                ),
            ),
        )
    )

    assert view.purpose == "permissions"
    assert view.title == "Permissions"
    assert view.content.items[0].description == (
        "Root · Filesystem content would be deleted"
    )
    assert view.content.items[1].description == (
        "Root · Publish non-force refs to origin"
    )
    assert view.handle_input(InputEvent(kind="key", key="enter")) == InputIntent(
        kind="select",
        text="reopen:approval-1",
    )
    view.handle_input(InputEvent(kind="key", key="down"))
    assert view.handle_input(InputEvent(kind="key", key="enter")) == InputIntent(
        kind="select",
        text="revoke:grant-1",
    )


def test_permissions_surface_identifies_child_incarnations() -> None:
    view = build_permissions_surface_view(
        ApprovalPermissionsSnapshot(
            pending=(
                ApprovalPermission(
                    kind="pending",
                    permission_id="approval-child",
                    actor_id="/root/reviewer#2",
                    capability="bash",
                    summary="Publish a release",
                ),
            ),
        )
    )

    assert view.content.items[0].description == (
        "/root/reviewer#2 · Publish a release"
    )
