# Internal Specs

## Status

Dated implementation specs.

Specs describe a particular implementation slice at the time it was designed.
They are useful for understanding why code exists, what tests were expected, and
which tradeoffs were made during an iteration.

## Reading Rule

- Use specs as historical implementation rationale.
- Prefer current code/tests for behavior.
- Prefer live architecture docs and accepted ARDs for current boundaries.
- Specs may contain old paths such as `docs/architecture/...` or historical
  method resource layouts such as `methods/**/SKILL.md`; those references are
  preserved when they describe the original implementation slice.
- Do not treat a dated spec as a migration task unless a current plan or ARD
  reactivates it.

Current live references:

- [Coding Product Boundaries](../architecture/coding/ARD-001-coding-product-boundaries.md)
- [Coding Component Interfaces](../architecture/coding/loushang-coding-component-interfaces.md)
- [Coding Core Data Objects](../architecture/coding/loushang-coding-core-data-objects.md)
