# UI Part Spec Inventory

This directory will hold detailed specs for concrete visible UI parts. UI parts
are built from renderables but are described at the product-facing UI level.

## Initial UI Parts

| Family | UI Parts |
| --- | --- |
| Basic | [Text, TruncatedText, Spacer, Box, Rule, DynamicBorder, Loader, CancellableLoader, WorkedDivider](./basic.md) |
| Frame | BottomFrame, StatusBar, WorkingLine, PendingQueueView, WidgetSlot |
| Input | Composer, TextInput, AutocompleteSurface |
| Navigation | Tabs, [TabGroup, TabPage](./tabgroup-content-switcher.md) |
| Lists | SelectList, [SearchableList](./tabgroup-content-switcher.md) |
| Surfaces | CommandSurface, SelectionSurface, SettingsSurface, ApprovalSurface, DialogSurface, HelpViewer, ChangelogViewer |
| Transcript | ChatTranscript, UserPromptView, AssistantMessageView, ThinkingView, ToolExecutionView, ErrorView, WorkedDivider |
| Content | MarkdownBlock, CodeBlock, DiffBlock, ImageBlock |

## Spec Template

Each UI part spec should include:

- purpose
- inputs and state
- render constraints
- focus behavior
- intents emitted
- layout and wrapping behavior
- theme tokens
- test obligations
