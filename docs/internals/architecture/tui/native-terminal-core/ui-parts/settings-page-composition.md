# Settings Page Composition

Settings-style TUI pages should be assembled from reusable widgets instead of
embedding custom page layout in the product layer. The reference assembly is
`examples/tui/54_widgets_settings_page_assembly.py`.

## Recommended Shape

Use `PageScaffold` as the outer page shell:

- header: title plus top-level `Tabs`
- body: selected page content
- footer: global status and navigation hints
- separator and spacing: owned by `PageScaffold`

Use `SearchableList` for settings-like long lists:

- boxed search input
- `Setting` / `Value` column headers
- aligned value or description column
- overflow row such as `↓ N more below`
- local footer hint row
- structured selection results

Use `TabGroup` when a selected page needs nested tabs, such as Stats Overview /
Models. Keep only one active header focus marker in the active focus path.

## Focus Contract

The expected focus path is:

1. SearchableList search input
2. SearchableList list rows
3. top-level tab header through unhandled search `up`
4. selected page body through top-level `down` or `enter`

When a nested `TabGroup` is inside the selected body, its own header/content
focus is local to that body. An `up` from nested content should focus nested
tabs before focus returns to the top-level page header.

Top-level selected tab rendering should distinguish:

- selected page active but header unfocused: content-focus styling and `*`
- selected tab header focused: header-focus styling and `>`
- normal tabs: no selected marker

Nested selected tab rendering follows the same contract with level-aware theme
tokens.

## Ownership Boundaries

`PageScaffold` owns:

- top-level header/body/footer arrangement
- separator and page footer theme tokens
- focus movement between header and body
- cursor offsets through inserted chrome

`Tabs` and `TabGroup` own:

- tab selection
- selected-header versus selected-content visual state
- local tab keyboard navigation

`SearchableList` owns:

- search query editing
- filtering and active item repair
- search/list focus movement
- list viewport and overflow counts
- local boxed search, column headers, and list footer hint

Product pages own:

- item values and mutation
- persistence
- side effects
- global status messages
- mapping selected tabs to page content

## Code Lane Handoff

When the real Settings page is migrated, prefer this order:

1. Keep existing product data and setting ids unchanged.
2. Introduce a page-level adapter that maps product tabs to widget bodies.
3. Use `SearchableListItem.key` as the stable setting id.
4. Keep value cycling in product page adapters, not inside SearchableList.
5. Use `SearchableListSelect` to drive product actions.
6. Add playback tests for search/list/top-tab/nested-tab focus paths before
   replacing legacy page layout.

The TUI lane should extend reusable widgets only when the real page needs a
general capability that is not already expressible by `PageScaffold`,
`Tabs`/`TabGroup`, or `SearchableList`.
