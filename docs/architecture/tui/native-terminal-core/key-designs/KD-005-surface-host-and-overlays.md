# KD-005: Surface Host And Overlays

## Purpose

Define temporary interactive UI without nested terminal applications.

## Design

SurfaceHost owns surface lifecycle, focus capture, close reasons, overlay stack,
and focus restoration. A surface is a renderable. It may be laid out in the
surface area or presented as an overlay. Overlay geometry and z-order are runtime
concerns, not product adapter concerns.

Surfaces return semantic intents and close reasons. The product adapter owns the
meaning of commands, settings, model choices, approvals, and selected values.

## Stacking And Focus

Surfaces are stacked in open order unless a surface handle explicitly changes
focus. The top focused capturing surface receives keyboard input first.
Non-capturing overlays may render above other content without stealing composer
focus.

When a top surface closes, focus returns to the next focused surface in the stack
or to the previously focused renderable, normally the composer. Composer text is
preserved while a surface is active unless the product adapter explicitly
replaces or clears it through an intent.

## Constrained Surface Content

Surface content that exceeds available height must scroll internally, paginate,
or truncate according to the surface type. A surface must not push the composer
minimum row or status row out of the bottom-frame budget.

Surfaces own their internal scroll state and receive normalized input events for
navigation. SurfaceHost owns focus, z-order, and layout constraints; it does not
provide a generic scroll container that interprets item semantics for every
surface.

## Overlay Composition

Overlay composition follows the stable render order: base logical lines are rendered
first, active overlays are composited into those lines, and the combined current
logical lines are compared against previous rendered lines.

When an overlay needs to cover rows that do not yet exist in the base logical
screen, the compositor pads the current logical screen to the minimum height
needed for overlay geometry, normally at least the visible terminal height. This
padding is part of current logical lines for diff planning; it is not committed
transcript content.

## Extension Surfaces

Extension-provided surfaces are adapted to the same surface protocol as built-in
surfaces. They may contribute renderables or UI parts and receive normalized
input events, but SurfaceHost still owns focus capture, z-order, close reasons,
and terminal writer boundaries.

## Required Surface Families

- autocomplete surface
- command surface
- selection surface
- settings surface
- approval surface
- dialog surface
- help and changelog viewer surfaces

## Test Obligations

- only the top focused surface receives keyboard input
- non-capturing overlays do not steal composer focus
- closing a surface restores previous focus
- approval surfaces cannot execute guarded actions directly
- surface render output remains bounded by its render constraints
- oversized surfaces scroll internally or truncate without displacing composer
  and status minimum rows
- overlay composition pads logical lines before diffing when geometry requires it
