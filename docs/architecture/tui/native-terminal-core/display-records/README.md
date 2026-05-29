# Display Record Spec Inventory

Display records are product-neutral data projected by product adapters before
rendering. They are separate from UI parts and renderables.

## Initial Records

| Record | Purpose |
| --- | --- |
| UserPromptRecord | Submitted user prompt text and attachments summary. |
| AssistantMessageRecord | Assistant content with text, thinking blocks, and tool references. |
| ToolExecutionRecord | Tool lifecycle, timing marker, output, truncation, and error state. |
| ErrorRecord | Concise user-facing product, provider, runtime, or TUI error. |
| InterruptedRecord | Stable interruption marker after abort or cancellation. |
| DividerRecord | Stable visual divider. |
| WorkedDividerRecord | Run-level completion timing divider. |

## Lifecycle

Records may be draft or committed. Draft records can change between render ticks.
Committed records are stable transcript content and must not be mutated by
transient UI updates.
