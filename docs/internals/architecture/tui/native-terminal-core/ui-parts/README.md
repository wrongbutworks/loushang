# UI Part Spec Inventory

This directory will hold detailed specs for concrete visible UI parts. UI parts
are built from renderables but are described at the product-facing UI level.

## Initial UI Parts

| Family | UI Parts |
| --- | --- |
| Basic | [Text, TruncatedText, Spacer, Box, Rule, DynamicBorder, Loader, CancellableLoader, WorkedDivider](./basic.md) |
| Frame | BottomFrame, StatusBar, WorkingLine, PendingQueueView, WidgetSlot |
| Input | Composer, TextInput, AutocompleteSurface |
| Navigation | Tabs, [TabGroup, TabPage](./tabgroup-content-switcher.md), [PageScaffold](./page-scaffold.md) |
| Lists | SelectList, [SearchableList](./searchable-list.md), [Table](./table.md), [TreeView](./tree.md) |
| Surfaces | CommandSurface, SelectionSurface, ApprovalSurface, DialogSurface, HelpViewer, ChangelogViewer |
| Transcript | ChatTranscript, UserPromptView, AssistantMessageView, ThinkingView, ToolExecutionView, ErrorView, WorkedDivider |
| Content | MarkdownBlock, CodeBlock, DiffBlock, ImageBlock |

## Page-Level Scaffolding

`ScreenRegionStack` is the screen-level region allocator used by larger terminal
frames. `PageScaffold` is a widget-level page shell for reusable page content:
it arranges optional header, body, and footer slots and owns focus movement
between header and body. Concrete product pages still own business state,
selected content, and actions.

Settings-style pages should compose existing widgets rather than owning custom
layout logic. See [Settings Page Composition](./settings-page-composition.md)
for the recommended `PageScaffold` + tabs + `SearchableList` shape.

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
