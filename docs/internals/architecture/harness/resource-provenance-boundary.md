# Harness Resource Provenance Boundary

## Status

Status: accepted for `lane/harness`.

This document defines product-neutral resource source metadata and resource
diagnostic records as `loushang.harness.resources` responsibilities. Coding
keeps resource discovery policy, executable installation diagnostics, and
product-facing diagnostic behavior.

## Decision

Harness owns two focused records:

- `loushang.harness.resources.source` owns `SourceInfo`, `SourceScope`, and
  `SourceOrigin`.
- `loushang.harness.resources.diagnostics` owns `ResourceDiagnostic`.

`SourceInfo` is generic over its path representation. Harness preserves the
path and base-directory values supplied by an adapter rather than choosing a
filesystem or serialization representation. Coding command surfaces may use
`SourceInfo[str]`, while extension runtime surfaces may use
`SourceInfo[pathlib.Path]`; both are instances of the same harness-owned class.

`ResourceDiagnostic` carries a code, message, optional source path and resource
identity, an opaque source-kind string, and neutral metadata. Harness does not
define coding resource kinds, resource-check phase/source assignment,
remediation text, or display policy.

## Compatibility

Accepted coding paths remain available:

```python
from loushang.coding.source_info import SourceInfo
from loushang.coding.extensions import SourceInfo
from loushang.coding.loader import ResourceDiagnostic
```

These paths re-export the same harness-owned classes. Harness-owned classes
keep their harness `__module__`; compatibility paths preserve imports, not
duplicate implementations or coding-owned class identity.

`loushang.coding.source_info` remains a product adapter. It keeps string path
projection for command/RPC surfaces, descriptor-to-source mapping, executable
installation identity, Git discovery, and user-facing formatting.

## Coding-Owned Behavior

This migration does not move or redesign:

- `ResourceSourceKind` or `ResourceSourceScope`;
- prompt, skill, theme, or extension descriptors;
- search roots, source precedence, merge decisions, or conflict policy;
- executable entrypoint, package installation, virtual environment, or Git
  identity discovery;
- resource check selection, phase/source assignment, or emission timing;
- product remediation messages, UI projection, or session recording policy.

General diagnostic vocabulary, records, queries, aggregation, and fingerprints
are owned by `loushang.harness.diagnostics`. Resource-specific check selection
and emission policy remain in Coding.

## Dependency Direction

The target direction is:

```text
coding loaders / extensions / commands / sessions
  -> loushang.harness.resources.source
coding loaders / extensions / commands / sessions
  -> loushang.harness.resources.diagnostics
loushang.harness.diagnostics.service
  -> loushang.harness.resources.diagnostics
```

The two harness modules are independent neutral records. They must not import
coding, method, work, TUI, AI, provider, or product packages. No provenance or
diagnostic symbols are added to top-level `loushang.harness.__all__`.

## Validation

The migration must prove:

- string and `Path` source representations are preserved without coercion;
- coding source-info and extension paths share the harness class identity;
- coding loader diagnostic paths share the harness class identity;
- existing descriptor projection and executable identity behavior is unchanged;
- coding internal consumers import the focused harness owners;
- harness import boundaries and top-level export discipline still pass.
