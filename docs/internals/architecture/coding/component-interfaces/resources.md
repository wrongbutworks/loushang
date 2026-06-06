# `resources`

## Role

- coding resource descriptor and loaded-resource projection boundary
- shared vocabulary for prompts, skills, themes, extensions, and package provenance

## Owns

- resource descriptor naming and provenance conventions
- loaded resource result shapes consumed by `loader`, `prompt`, `extensions`, and `plugin`
- package-aware resource source metadata

## Depends On

- filesystem/package roots as inputs
- `loader` for discovery orchestration

## Commands

- none as a standalone runtime component

## Queries

- resource descriptors are queried through `loader`

## Events

- no stable external event surface

## Key Data

- `ResourceBundle`
- `PackageResourceSummary`
- prompt/skill/theme/extension descriptors
- `source_kind`
- `source_scope`
- `source_root`
- package provenance metadata

## Out Of Scope

- discovering resources on disk
- prompt assembly
- extension execution
- package lifecycle state mutation

## Reference Implementation Alignment

- Keeps reference-style resource discovery data explicit in Python objects.
- Avoids making `loader` the owner of every descriptor schema detail.
- Package provenance is carried by descriptors and serialized by CLI/RPC/TUI adapters; adapters should not re-infer package origin.
