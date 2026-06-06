# `method` compatibility note

## Role

- compatibility entry for older links that referenced a coding `method` component
- canonical coding component is now [`domain`](domain.md)
- method resources, method registry, method compiler, and method projector belong to `loushang.method`

## Current Boundary

`loushang.coding` owns only the coding-specific domain bridge:

- `CodingDomainRequest`
- `CodingDomainPreparedTurn`
- `MethodPolicy`
- `CodingDomainApp.prepare_turns(...)`

The full boundary is documented in [domain.md](domain.md).

## Related Architecture Decisions

- [ARD-006: TUI Method Integration Constraints](../ARD-006-tui-method-integration-constraints.md)
- [Coding Product Boundaries](../ARD-001-coding-product-boundaries.md)
