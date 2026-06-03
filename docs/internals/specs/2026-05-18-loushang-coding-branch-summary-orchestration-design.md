# Loushang Coding Branch Summary Orchestration Design

## Goal

Make session tree navigation in `loushang-coding` product-usable by adding `session`-level branch summary orchestration aligned with `pi`'s `navigateTree(...)` semantics.

## Problem

`loushang-coding` already has:

- append-only branch/tree persistence in `SessionManager`
- `BranchSummaryEntry` and `BranchSummaryMessage`
- pure branch-summary helpers in `loushang.coding.compaction.branch_summarization`

What it does not yet have is the session behavior that turns these pieces into a usable feature. Today the system can persist a branch summary entry, but it cannot:

- navigate from one tree position to another with optional summary generation
- decide where the summary should be attached
- update the active leaf and rebuild agent context
- expose branch-summary lifecycle to modes and future extensions

That missing layer is `branch summary orchestration`.

## Purpose And Meaning

Branch summary exists to make multi-branch sessions usable.

When leaving one branch and navigating to another, the system should be able to compress the important work from the old branch into a single summary entry so that:

- the new branch does not need to inherit the entire old branch transcript
- important conclusions from the old branch are not lost
- tree navigation remains explainable and context-budget aware

This is different from compaction:

- compaction compresses the current branch so work can continue on the same line
- branch summary compresses the branch being left so a different branch can be resumed without losing context

## Alignment Target

The target semantic model is `pi`'s `navigateTree(...)` plus branch summarization flow:

- navigation is a `session` responsibility
- branch summarization remains a `compaction`-adjacent capability component
- the summary is attached at the navigation target position, not written back onto the abandoned branch
- summary generation may later be overridden by extensions, but default orchestration stays in `session`

`loushang` does not need to copy `pi`'s full complexity in the first phase, but it should align with the same boundary split.

## Component Boundaries

### `session`

Owns:

- `navigate_tree(...)`
- `abort_branch_summary()`
- navigation lifecycle
- deciding whether summary generation runs
- choosing the new leaf position
- rebuilding runtime context after navigation
- emitting branch-summary lifecycle events

Does not own:

- branch summary prompt construction details
- summary generation algorithm internals
- transcript persistence internals

### `compaction`

Owns:

- `collect_entries_for_branch_summary(...)`
- `prepare_branch_entries(...)`
- `generate_branch_summary(...)`
- branch-summary prompt and token-budget logic
- result/details objects

Does not own:

- leaf switching
- session state mutation
- session event dispatch

### `store`

Owns:

- tree traversal primitives
- `branch(...)`
- `reset_leaf()`
- `branch_with_summary(...)`
- append-only persistence of `BranchSummaryEntry`
- projection of branch summaries into runtime context

## Phase 1 Scope

Phase 1 adds the minimal session-level orchestration that makes branch summary usable:

- `AgentSession.navigate_tree(...)`
- `AgentSession.abort_branch_summary()`
- default branch summary generation through the compaction layer
- `branch_summary_start` / `branch_summary_end` session events
- correct leaf switching and context rebuild
- support for summarizing or non-summarizing navigation

Phase 1 does not include:

- file-operation tracking in `BranchSummaryDetails`
- full `pi` extension override semantics
- retry integration
- UI/editor integration beyond returning `editor_text`
- labels and custom instructions replacement unless explicitly needed during implementation

## Target API

### `AgentSession.navigate_tree(...)`

```python
async def navigate_tree(
    self,
    target_id: str,
    *,
    summarize: bool = False,
    custom_instructions: str | None = None,
    replace_instructions: bool = False,
    label: str | None = None,
) -> TreeNavigationResult:
    ...
```

### `TreeNavigationResult`

```python
@dataclass(frozen=True)
class TreeNavigationResult:
    cancelled: bool
    aborted: bool = False
    editor_text: str | None = None
    summary_entry_id: str | None = None
```

Phase 1 only requires `cancelled`, `aborted`, `editor_text`, and a stable reference to the created summary entry.

### `AgentSession.abort_branch_summary()`

```python
def abort_branch_summary(self) -> None:
    ...
```

This cancels only in-flight branch summary generation, not the active agent run.

## Navigation Semantics

### No-op

If `target_id` is already the current leaf, `navigate_tree(...)` returns success without changing state.

### Target Resolution

If `target_id` does not exist, `navigate_tree(...)` fails immediately.

### Summary Input

When summarization is requested, `session`:

1. records the old leaf id
2. collects entries between the old leaf and the common ancestor with the target
3. prepares branch-summary messages subject to token budget
4. generates summary text

### New Leaf Rules

These should match `pi`'s high-level meaning:

- if target is a `user` message:
  - leaf becomes the target's parent
  - extracted user text is returned as `editor_text`
- if target is a `custom_message`:
  - leaf becomes the target's parent
  - extracted text content is returned as `editor_text`
- otherwise:
  - leaf becomes `target_id`

### Summary Placement

If summary generation succeeds, the summary is attached at the navigation target position using `branch_with_summary(...)`.

This means:

- navigation target determines the new location
- summary entry becomes the new leaf
- the old branch remains unchanged

### No Summary Case

If summarization is disabled or there are no entries worth summarizing:

- navigate to the computed leaf directly
- do not create a summary entry

## Events

Phase 1 introduces two new `session/event` lifecycle events:

### `branch_summary_start`

```python
{
    "type": "branch_summary_start",
    "target_id": str,
    "old_leaf_id": str | None,
    "summarize": bool,
}
```

### `branch_summary_end`

```python
{
    "type": "branch_summary_end",
    "target_id": str,
    "old_leaf_id": str | None,
    "new_leaf_id": str | None,
    "summary_entry_id": str | None,
    "cancelled": bool,
    "aborted": bool,
    "error_message": str | None,
}
```

These are for mode/UI visibility and future orchestration observability. They are not replacements for extension hooks.

## Data Flow

Phase 1 flow:

1. `AgentSession.navigate_tree(...)`
2. validate target and compute `old_leaf_id`
3. emit `branch_summary_start`
4. call `collect_entries_for_branch_summary(...)`
5. if summary requested:
   - call `generate_branch_summary(...)`
6. compute `new_leaf_id`
7. write via `branch_with_summary(...)` or `branch(...)` / `reset_leaf()`
8. rebuild `SessionContext`
9. replace `agent.state.messages`
10. emit `branch_summary_end`

## Error And Cancellation Model

Phase 1 keeps a narrow model:

- invalid target: raise
- no model available when summary is requested: raise
- abort during summary generation:
  - return `cancelled=True`, `aborted=True`
  - do not change leaf
- summary generation error:
  - emit `branch_summary_end` with `error_message`
  - re-raise

Phase 1 does not retry branch summary generation.

## Future Extensions

This design intentionally leaves room for the full `pi` shape:

- extension decision hooks such as `session_before_tree`
- extension-provided summaries
- labels attached to summary entries or target entries
- richer `BranchSummaryDetails`
- file read/modified tracking
- integration with retry and broader tree-navigation workflows

## Implementation Strategy

Implement in two layers:

1. finish the missing pure compaction-side API:
   - `generate_branch_summary(...)`
   - `BranchSummaryDetails`
2. add `session` orchestration:
   - `navigate_tree(...)`
   - `abort_branch_summary()`
   - event emission
   - context rebuild and store updates

This preserves the current architecture rule:

- capability in `compaction`
- orchestration in `session`
- persistence in `store`
