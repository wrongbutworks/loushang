# `platform`

## Role

- host platform helpers used by coding CLI/TUI/runtime surfaces
- thin boundary for terminal, clipboard, git, stdout, version, and footer helper behavior

## Owns

- clipboard text/image helpers
- stdout takeover/restore guard
- git branch helper
- changelog/version lookup helpers
- footer data provider projection helpers

## Depends On

- host OS services
- filesystem
- git executable or repository metadata when available

## Commands

- `copy_to_clipboard(...)`
- `read_clipboard_image(...)`
- `take_over_stdout(...)`
- `restore_stdout(...)`
- `write_raw_stdout(...)`
- `flush_raw_stdout(...)`

## Queries

- `is_stdout_taken_over()`
- `get_git_branch(...)`
- `check_for_new_loushang_version(...)`
- `parse_changelog(...)`
- `footer_snapshot_to_mapping(...)`

## Events

- no stable external event surface

## Key Data

- `ClipboardCopyResult`
- `ClipboardImage`
- `ChangelogEntry`
- `FooterSnapshot`
- `FooterDataProvider`

## Out Of Scope

- mode lifecycle
- TUI rendering policy
- filesystem permission policy
- session state

## Reference Implementation Alignment

- Keeps platform-specific helpers outside session/runtime business logic.
- Allows CLI/TUI/RPC surfaces to share host capability helpers without making `utils` a hidden business layer.
