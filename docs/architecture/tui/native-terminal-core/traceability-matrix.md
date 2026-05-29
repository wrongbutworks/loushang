# Traceability Matrix

This matrix connects requirements, scenarios, key designs, renderables, tests,
and development slices. Rows here are implementation-driving coverage targets.
Detailed UI part specs may add finer-grained rows later.

| ID | Requirement / Constraint | Scenarios | Key Designs | Renderables / UI Parts | Tests | Slice |
| --- | --- | --- | --- | --- | --- | --- |
| FR-RR-001 | Native terminal runtime | SC-START-001 | KD-001 | TuiRuntime, TerminalPort | test_runtime_startup.py | Slice 3 |
| FR-RR-002 | Logical screen composition | SC-CI-001 | KD-001, KD-008 | ScreenRoot, RenderLoop | test_logical_screen_composition.py | Slice 3 |
| FR-RR-003 | Differential rendering | SC-RR-001 | KD-001 | RenderLoop, ScreenBuffer | test_render_loop_diff.py | Slice 3 |
| FR-RR-004 | Bottom frame ownership | SC-CI-001, SC-LAYOUT-002 | KD-008 | BottomFrame, SurfaceHost, Composer, StatusBar | test_bottom_frame_ownership.py | Slice 5 |
| FR-RR-005 | Resize and reflow | SC-RR-001 | KD-007 | RenderLoop, ViewportTracker | test_resize_reflow.py | Slice 3 |
| FR-RR-006 | Terminal restore | SC-CI-003, SC-ERR-001 | KD-001, KD-003 | TuiRuntime, TerminalPort, InputReader | test_terminal_restore.py | Slice 3 |
| FR-RR-007 | User scrollback interaction | SC-RR-003 | KD-004, KD-007 | ViewportTracker, RenderLoop | test_user_scrollback_interaction.py | Slice 3 |
| FR-RR-008 | External stdout recovery | SC-EX-002 | KD-004, KD-007 | TerminalPort, ViewportTracker, RenderLoop | test_external_stdout_recovery.py | Slice 3 |
| FR-RR-009 | Resize repaint | SC-RR-001, SC-RR-002 | KD-001, KD-007 | RenderLoop, ScreenRoot, ViewportTracker | test_resize_repaint.py | Slice 3 |
| FR-RR-010 | Clear scrollback policy | SC-RR-004 | KD-004, KD-007 | TerminalPort, RenderLoop | test_clear_scrollback_policy.py | Slice 3 |
| FR-IC-001 | Editable composer | SC-LAYOUT-001, SC-LAYOUT-002 | KD-002, KD-008 | Composer, UndoStack | test_editable_composer.py | Slice 5 |
| FR-IC-002 | Composer soft wrapping | SC-LAYOUT-001 | KD-008 | Composer, CellWidth, AnsiWrapper | test_composer_wrapping.py | Slice 5 |
| FR-IC-003 | Explicit newlines | SC-LAYOUT-002 | KD-008 | Composer | test_composer_multiline.py | Slice 5 |
| FR-IC-004 | Cursor declaration | SC-LAYOUT-001, SC-LAYOUT-006 | KD-002 | Composer, CursorMarker | test_cursor_declaration.py | Slice 1 |
| FR-IC-005 | Slash command trigger | SC-SO-001 | KD-002, KD-005, KD-011 | Composer, SurfaceHost, CommandSurface | test_slash_command_surface.py | Slice 7 |
| FR-IC-007 | Bracketed paste | SC-LAYOUT-003 | KD-002 | InputReader, Composer | test_bracketed_paste.py | Slice 6 |
| FR-IC-008 | Paste safety | SC-LAYOUT-005 | KD-002 | InputReader, Composer, CellWidth | test_paste_safety.py | Slice 6 |
| FR-IC-009 | Large paste representation | SC-LAYOUT-004 | KD-002, KD-008 | Composer, PasteMarker, UndoStack | test_large_paste_marker.py | Slice 5 |
| FR-IC-010 | Paste undo | SC-LAYOUT-003, SC-LAYOUT-004 | KD-002 | Composer, UndoStack | test_paste_undo.py | Slice 5 |
| FR-IC-011 | Paste while running | SC-CI-004, SC-CI-005, SC-LAYOUT-003 | KD-002, KD-003 | Composer, PendingQueueView | test_paste_while_running.py | Slice 8 |
| FR-IC-012 | Editor undo stack and kill ring | SC-LAYOUT-001, SC-LAYOUT-003 | KD-002 | Composer, UndoStack, KillRing | test_editor_undo_kill_ring.py | Slice 5 |
| FR-SO-001 | Surface host | SC-SO-001, SC-SO-002 | KD-005 | SurfaceHost, Overlay, Focusable | test_surface_host.py | Slice 7 |
| FR-SO-002 | Autocomplete surface | SC-SO-001 | KD-005, KD-011 | AutocompleteSurface, Composer | test_autocomplete_surface.py | Slice 7 |
| FR-SO-003 | Command surface | SC-SO-001 | KD-005, KD-011 | CommandSurface, SelectionSurface | test_command_surface.py | Slice 7 |
| FR-SO-004 | Settings surface | SC-SO-002 | KD-005 | SettingsSurface, SettingsList | test_settings_surface.py | Slice 7 |
| FR-SO-005 | Dialog surface | SC-SO-002 | KD-005 | DialogSurface | test_dialog_surface.py | Slice 7 |
| FR-SO-006 | Surface Esc handling | SC-CI-003, SC-SO-002 | KD-002, KD-003, KD-005 | SurfaceHost, TuiRuntime | test_input_priority.py | Slice 7 |
| FR-SO-007 | Selection surface | SC-SO-001, SC-SO-002, SC-SO-004 | KD-005, KD-011 | SelectionSurface, SelectList | test_selection_surface.py | Slice 7 |
| FR-SO-008 | Approval surface | SC-SO-002, SC-CI-003 | KD-005 | ApprovalSurface, ApprovalPrompt | test_approval_surface.py | Slice 7 |
| FR-SO-009 | Surface stacking | SC-SO-005 | KD-005 | SurfaceHost, OverlayStack | test_surface_stacking.py | Slice 7 |
| FR-SO-010 | Constrained surface scrolling | SC-SO-005 | KD-005, KD-008 | SurfaceHost, SelectionSurface, SettingsSurface | test_constrained_surface_scrolling.py | Slice 7 |
| FR-CR-001 | Markdown rendering | SC-CR-001 | KD-006 | MarkdownRenderer, CellWidth | test_markdown_rendering.py | Slice 9 |
| FR-CR-002 | Code blocks | SC-CR-001 | KD-006, KD-009 | CodeBlock, CodeRenderer | test_code_block_rendering.py | Slice 9 |
| FR-CR-003 | Diff blocks | SC-CR-001 | KD-006, KD-009 | DiffBlock, DiffRenderer | test_diff_block_rendering.py | Slice 9 |
| FR-CR-004 | Image blocks | SC-CR-001 | KD-006 | ImageBlock, ImageRenderer | test_image_block_fallback.py | Slice 9 |
| FR-CR-005 | Thinking blocks | SC-CR-003 | KD-006 | AssistantMessageView, ThinkingView | test_thinking_blocks.py | Slice 8 |
| FR-CR-006 | Tool execution records | SC-CR-002 | KD-006 | ToolExecutionView | test_tool_execution_record.py | Slice 8 |
| FR-CR-007 | Error records | SC-ERR-001 | KD-006 | ErrorView, ErrorRenderer | test_error_record_rendering.py | Slice 8 |
| FR-CI-001 | Product adapter boundary | SC-EX-001 | KD-006 | PublicTuiApi, CodingAdapter | test_product_adapter_boundary.py | Slice 8 |
| FR-CI-002 | Transcript display records | SC-CI-001, SC-CI-002, SC-ERR-001 | KD-006 | CodingScreenRoot, ChatTranscript | test_coding_screen_records.py | Slice 8 |
| FR-CI-003 | Running turn chrome | SC-CI-001, SC-CI-002 | KD-003, KD-008 | WorkingLine, WorkedDivider | test_running_turn_chrome.py | Slice 8 |
| FR-CI-004 | Follow-up queue | SC-CI-004 | KD-004 | Composer, PendingQueueView, CodingScreenRoot | test_follow_up_queue.py | Slice 8 |
| FR-CI-005 | Steering messages | SC-CI-005, SC-CI-006 | KD-004 | Composer, PendingQueueView, CodingScreenRoot | test_steering_queue.py | Slice 8 |
| FR-CI-006 | Abort interaction | SC-CI-003 | KD-003 | TuiRuntime, SurfaceHost, CodingScreenRoot | test_abort_sequence.py | Slice 8 |
| FR-CI-007 | Concise errors | SC-ERR-001 | KD-006 | ErrorView | test_concise_errors.py | Slice 8 |
| FR-CI-008 | Status snapshot | SC-CI-001 | KD-008, KD-009 | StatusBar | test_status_snapshot_priority.py | Slice 5 |
| FR-EX-001 | Extension boundary | SC-EX-001, SC-EX-002 | KD-005 | PublicTuiApi, WidgetSlot | test_extension_boundary.py | Slice 10 |
| FR-EX-002 | Extension widget slots | SC-EX-001 | KD-005, KD-008 | WidgetSlot, ScreenRoot | test_extension_widget_slot.py | Slice 10 |
| FR-EX-003 | Extension surfaces | SC-SO-004, SC-SO-005 | KD-005 | SurfaceHost, PublicTuiApi | test_extension_surfaces.py | Slice 10 |
| FR-EX-004 | Extension status fields | SC-TH-001 | KD-008, KD-009 | StatusBar, ThemeResolver | test_extension_status_fields.py | Slice 10 |
| FR-EX-005 | Extension lifecycle | SC-EX-001 | KD-005 | WidgetSlot, SurfaceHost | test_extension_lifecycle.py | Slice 10 |
| FR-EX-006 | Extension renderable adapter | SC-EX-001, SC-SO-004 | KD-005 | PublicTuiApi, RenderableAdapter, SurfaceHost | test_extension_renderable_adapter.py | Slice 10 |
| FR-TH-001 | Structured theme tokens | SC-TH-001 | KD-009 | ThemeResolver, RenderTheme | test_theme_tokens.py | Slice 9 |
| FR-TH-002 | Theme capability degradation | SC-TH-001 | KD-009 | ThemeResolver, TerminalCapabilities | test_theme_capability_degradation.py | Slice 9 |
| FR-TH-003 | Theme invalidation | SC-TH-001 | KD-009 | ThemeResolver, RenderLoop | test_theme_invalidation.py | Slice 9 |
| FR-TH-004 | Product theme loading | SC-TH-001 | KD-009 | ThemeResolver, ProductAdapter | test_product_theme_loading.py | Slice 9 |
| NFR-VS-001 | No steady-state flicker | SC-CI-001, SC-RR-001 | KD-001, KD-007 | RenderLoop, TerminalPort | test_no_full_clear.py | Slice 3 |
| NFR-VS-002 | Synchronized terminal updates | SC-CI-001 | KD-001 | TerminalPort, RenderLoop | test_synchronized_flush.py | Slice 3 |
| NFR-VS-003 | Resize-stable reflow | SC-RR-001 | KD-007, KD-008 | RenderLoop, ViewportTracker, ScreenRoot, Composer, StatusBar | test_resize_stable_reflow.py | Slice 3 |
| NFR-SI-001 | Steady-state history integrity | SC-START-001, SC-CI-001, SC-RR-004 | KD-001, KD-004 | RenderLoop, ViewportTracker | test_history_integrity.py | Slice 3 |
| NFR-SI-002 | Streaming draft integrity | SC-CI-001 | KD-006 | ChatTranscript, Markdown | test_streaming_draft_commit.py | Slice 8 |
| NFR-TC-001 | Terminal width correctness | SC-LAYOUT-001, SC-LAYOUT-006 | KD-002, KD-008 | CellWidth, Composer, MarkdownRenderer | test_terminal_width_correctness.py | Slice 1 |
| NFR-TC-002 | Terminal restoration | SC-CI-003, SC-ERR-001 | KD-001, KD-002 | TerminalPort, InputReader | test_terminal_restoration.py | Slice 3 |
| NFR-EX-001 | Runtime is only terminal writer | SC-SO-001, SC-CI-001 | KD-001 | TuiRuntime, TerminalPort | test_terminal_writer_boundary.py | Slice 3 |
| NFR-LAT-001 | Responsive input | SC-CI-001, SC-LAYOUT-001 | KD-001, KD-002 | RenderScheduler, InputReader, Composer | test_responsive_input.py | Slice 6 |
| NFR-PORT-001 | Capability degradation | SC-TH-001, SC-CR-001 | KD-009 | TerminalCapabilities, ThemeResolver, ImageRenderer | test_capability_degradation.py | Slice 9 |
| NFR-PORT-002 | Clear scrollback is explicit | SC-RR-004 | KD-004, KD-007 | TerminalPort, RenderLoop | test_clear_scrollback_explicit.py | Slice 3 |
| NFR-OBS-001 | Deterministic render diagnostics | SC-RR-001, SC-CI-001 | KD-001, KD-010 | RenderLoop, PlaybackHarness | test_render_diagnostics.py | Slice 2 |
