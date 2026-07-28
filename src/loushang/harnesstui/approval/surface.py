"""Product-neutral `/permissions` surface."""

from __future__ import annotations

from loushang.harness.approval import ApprovalPermissionsSnapshot
from loushang.harnesstui.surface.view import ScreenSurfaceView
from loushang.tui import SelectionSurface, SelectItem


def build_permissions_surface_view(
    snapshot: ApprovalPermissionsSnapshot,
) -> ScreenSurfaceView:
    """Show safe approval summaries without exposing raw commands or arguments."""

    items = [
        SelectItem(
            label=f"Pending · {permission.capability}",
            value=f"reopen:{permission.permission_id}",
            description=_permission_description(
                actor_id=permission.actor_id,
                summary=permission.summary,
            ),
        )
        for permission in snapshot.pending
    ]
    items.extend(
        SelectItem(
            label=f"Session · {permission.capability}",
            value=f"revoke:{permission.permission_id}",
            description=_permission_description(
                actor_id=permission.actor_id,
                summary=permission.summary,
            ),
        )
        for permission in snapshot.grants
    )
    return ScreenSurfaceView(
        title="Permissions",
        subtitle=(
            f"{len(snapshot.pending)} pending · "
            f"{len(snapshot.grants)} session grants"
        ),
        purpose="permissions",
        content=SelectionSurface(
            items=items,
            max_visible=12,
            empty_text="No pending approvals or session grants",
        ),
        footer="Enter reopen/revoke · Esc close",
        presentation="page",
    )


def _permission_description(*, actor_id: str, summary: str) -> str:
    requester = "Root" if actor_id == "root" else actor_id
    return f"{requester} · {summary}"


__all__ = ["build_permissions_surface_view"]
