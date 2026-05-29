# Experimental / Exploration Documents

> **WARNING**: This directory contains experimental and exploratory design documents.
> They are **NOT** part of the project's stable architecture and **MUST NOT** affect
> the build, test suite, or production behavior.
>
> Documents here represent ideas in flux, design alternatives under discussion,
> and reference materials from related projects. They may be moved, rewritten,
> or deleted without notice.

## Purpose

This space is for:
- Architecture explorations before they are accepted into the main design
- Reference materials from related projects (e.g., `loushang-ts` methodology system)
- Design discussions and alternative approaches
- Draft specifications that have not yet been validated by implementation

## Directory Layout

```
experimental/
├── README.md                           # This file
└── methodology/                        # SPEM 2.0-aligned methodology design (from loushang-ts)
    ├── domain-taxonomy-design.md
    ├── llm-conductor-design.md
    ├── meta-phase.md
    ├── meta-roles-5plus1.md
    ├── methodology-adaptation.md
    ├── methodology-file-structure.md
    ├── multi-agent-scenarios.md              # Multi-agent collaboration scenarios
    ├── methodology-orchestration-extension.md # Orchestration mode extension to SPEM 2.0
    └── superpowers-methodology-redesign.md
```

## Related Documents (outside this directory)

- `../session-controller-architecture.md` — Multi-terminal / multi-interface support design
  (currently in review; may be revised based on methodology integration)

## How to Use

1. Read these documents for **context and inspiration**
2. Do **not** import or reference them from production code
3. When a design stabilizes, it should be promoted out of this directory
   (e.g., into `../architecture/` or the codebase itself)
4. When a design is rejected, delete it — do not keep obsolete drafts

## Origin of Methodology Documents

The `methodology/` subdirectory contains reference materials from the
`loushang-ts` project (`/Users/zhnt/workspace/loushang-ts/docs/methodology/`),
copied here for cross-project design alignment. They describe:

- SPEM 2.0-aligned method element types (phase, activity, task, role, guidance, workproduct)
- The 5 meta-phases (PLAN, EXPLORE, DESIGN, BUILD, VERIFY)
- The 5+1 meta-roles (PLANNER, EXPLORER, DESIGNER, DELIVER, VALIDATOR + CONDUCTOR)
- LLM-based conductor scheduling
- Domain taxonomy and methodology adaptation mechanisms

These concepts are being evaluated for integration with the SessionController
architecture and multi-agent collaboration scenarios.
