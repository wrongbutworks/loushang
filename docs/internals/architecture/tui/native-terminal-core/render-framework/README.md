# Render Framework Spec Inventory

This directory holds detailed API specs for framework-level render contracts.

## Available Specs

| Spec | Purpose | Depends On |
| --- | --- | --- |
| `render-loop.md` | Logical screen diffing, strategy selection, operations, synchronized flush. | terminal-port, screen-root |
| `managed-viewport.md` | Viewport top, previous viewport top, recovery rules, protected append. | render-loop |

## Remaining Required Specs

| Spec | Purpose | Depends On |
| --- | --- | --- |
| `renderable.md` | Render protocol, constraints, render result, invalidation. | cell-width model |
| `container.md` | Ordered child renderables, constraint propagation, focus traversal. | renderable |
| `focusable.md` | Routed input handling and cursor declaration. | renderable, input events |
| `terminal-port.md` | The only terminal writer abstraction. | terminal capability model |
| `repaint-policy.md` | Full repaint, resize repaint, recovery repaint, and clear-scrollback policy. | render-loop, managed-viewport |
| `screen-root.md` | Screen region stack composition. | container, bottom-frame |
| `surface-host.md` | Surface lifecycle, focus capture, overlay stack. | focusable, container |

## Boundary

Render framework specs must stay product-neutral. Coding concepts belong in
`loushang.coding.ui` adapter specs or UI part specs.
