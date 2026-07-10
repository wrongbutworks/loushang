from __future__ import annotations

from importlib import resources
from typing import is_typeddict


def test_tool_input_and_details_types_are_exported() -> None:
    from loushang.coding.tools import (
        BashToolDetails,
        BashToolInput,
        DownloadingExternalToolResolver,
        EditToolDetails,
        EditToolInput,
        ExternalToolDownloader,
        ExternalToolDownloadTransport,
        ExternalToolName,
        ExternalToolPolicy,
        ExternalToolResolver,
        FindToolDetails,
        FindToolInput,
        GitHubReleaseExternalToolDownloader,
        GrepToolDetails,
        GrepToolInput,
        LsToolDetails,
        LsToolInput,
        ManagedExternalToolInstall,
        ReadImageResizeResult,
        ReadToolDetails,
        ReadToolInput,
        Tool,
        ToolDef,
        ToolDownloadConfig,
        ToolResultPresentation,
        UrllibExternalToolDownloadTransport,
        WriteToolDetails,
        WriteToolInput,
        allToolNames,
        createAllToolDefinitions,
        createAllTools,
        createBashTool,
        createCodingToolDefinitions,
        createCodingTools,
        createEditTool,
        createFindTool,
        createGrepTool,
        createLsTool,
        createReadOnlyToolDefinitions,
        createReadOnlyTools,
        createReadTool,
        createTool,
        createToolDefinition,
        createToolDefinitionFromAgentTool,
        createWriteTool,
        default_external_tools_dir,
        ensure_external_tool,
        expandPath,
        formatSize,
        get_managed_external_tool_install,
        get_tool_text_output,
        normalize_display_text,
        render_tool_result_presentation,
        render_tool_result_text,
        resolveReadPath,
        resolveToCwd,
        run_with_file_mutation_queue,
        truncateHead,
        truncateLine,
        truncateTail,
        with_file_mutation_queue,
        withFileMutationQueue,
        wrapToolDefinition,
        wrapToolDefinitions,
    )

    for exported_type in (
        BashToolDetails,
        BashToolInput,
        EditToolDetails,
        EditToolInput,
        FindToolDetails,
        FindToolInput,
        GrepToolDetails,
        GrepToolInput,
        LsToolDetails,
        LsToolInput,
        ReadToolDetails,
        ReadToolInput,
        WriteToolDetails,
        WriteToolInput,
    ):
        assert is_typeddict(exported_type)

    assert DownloadingExternalToolResolver is not None
    assert ExternalToolDownloadTransport is not None
    assert ExternalToolDownloader is not None
    assert ExternalToolName is not None
    assert ExternalToolPolicy is not None
    assert ExternalToolResolver is not None
    assert GitHubReleaseExternalToolDownloader is not None
    assert ToolDownloadConfig is not None
    assert ManagedExternalToolInstall is not None
    assert UrllibExternalToolDownloadTransport is not None
    assert default_external_tools_dir is not None
    assert get_managed_external_tool_install is not None
    assert ensure_external_tool is not None
    assert Tool is not None
    assert ToolDef is not None
    assert ToolResultPresentation is not None
    assert get_tool_text_output is not None
    assert normalize_display_text is not None
    assert render_tool_result_presentation is not None
    assert render_tool_result_text is not None
    assert allToolNames == {"read", "bash", "edit", "write", "grep", "find", "ls"}
    assert createToolDefinition is not None
    assert createTool is not None
    assert createReadTool is not None
    assert createBashTool is not None
    assert createEditTool is not None
    assert createWriteTool is not None
    assert createGrepTool is not None
    assert createFindTool is not None
    assert createLsTool is not None
    assert createCodingToolDefinitions is not None
    assert createReadOnlyToolDefinitions is not None
    assert createAllToolDefinitions is not None
    assert createCodingTools is not None
    assert createReadOnlyTools is not None
    assert createAllTools is not None
    assert createToolDefinitionFromAgentTool is not None
    assert wrapToolDefinition is not None
    assert wrapToolDefinitions is not None
    assert formatSize is not None
    assert truncateHead is not None
    assert truncateTail is not None
    assert truncateLine is not None
    assert expandPath is not None
    assert resolveToCwd is not None
    assert resolveReadPath is not None
    assert run_with_file_mutation_queue is withFileMutationQueue
    assert with_file_mutation_queue is not None
    assert ReadImageResizeResult is not None


def test_coding_top_level_exports_pi_style_tool_api_aliases() -> None:
    from loushang.coding import (
        createBashTool,
        createEditTool,
        createFindTool,
        createGrepTool,
        createLsTool,
        createReadTool,
        createToolDefinitionFromAgentTool,
        createWriteTool,
        expandPath,
        formatSize,
        resolveReadPath,
        resolveToCwd,
        truncateHead,
        truncateLine,
        truncateTail,
        wrapToolDefinition,
        wrapToolDefinitions,
    )

    assert createReadTool is not None
    assert createBashTool is not None
    assert createEditTool is not None
    assert createWriteTool is not None
    assert createGrepTool is not None
    assert createFindTool is not None
    assert createLsTool is not None
    assert createToolDefinitionFromAgentTool is not None
    assert wrapToolDefinition is not None
    assert wrapToolDefinitions is not None
    assert formatSize is not None
    assert truncateHead is not None
    assert truncateTail is not None
    assert truncateLine is not None
    assert expandPath is not None
    assert resolveToCwd is not None
    assert resolveReadPath is not None


def test_coding_top_level_exports_exec_sdk_types() -> None:
    import loushang.coding as coding
    from loushang.coding import (
        ExecBackend,
        ExecOutputChunk,
        ExecRequest,
        ExecResult,
        ExecService,
        ExecUpdateCallback,
    )
    from loushang.harness.workspace.exec import (
        ExecBackend as HarnessExecBackend,
    )
    from loushang.harness.workspace.exec import (
        ExecOutputChunk as HarnessExecOutputChunk,
    )
    from loushang.harness.workspace.exec import (
        ExecRequest as HarnessExecRequest,
    )
    from loushang.harness.workspace.exec import (
        ExecResult as HarnessExecResult,
    )
    from loushang.harness.workspace.exec import (
        ExecService as HarnessExecService,
    )
    from loushang.harness.workspace.exec import (
        ExecUpdateCallback as HarnessExecUpdateCallback,
    )

    assert ExecBackend is not None
    assert ExecOutputChunk(stream="stdout", text="ok").text == "ok"
    assert ExecRequest(command=["git", "status"]).command == ("git", "status")
    assert ExecResult(exit_code=0).exit_code == 0
    assert ExecService is not None
    assert ExecUpdateCallback is not None
    assert ExecBackend is HarnessExecBackend
    assert ExecOutputChunk is HarnessExecOutputChunk
    assert ExecRequest is HarnessExecRequest
    assert ExecResult is HarnessExecResult
    assert ExecService is HarnessExecService
    assert ExecUpdateCallback is HarnessExecUpdateCallback
    assert ExecRequest.__module__ == "loushang.harness.workspace.exec.types"
    assert ExecService.__module__ == "loushang.harness.workspace.exec.service"
    assert {
        "ExecBackend",
        "ExecOutputChunk",
        "ExecRequest",
        "ExecResult",
        "ExecService",
        "ExecUpdateCallback",
    }.issubset(set(coding.__all__))


def test_loushang_package_declares_typed_sdk_surface() -> None:
    assert resources.files("loushang").joinpath("py.typed").is_file()


def test_tool_input_required_keys_match_tool_schemas() -> None:
    from loushang.coding.tools import (
        BashToolInput,
        EditToolInput,
        FindToolInput,
        GrepToolInput,
        LsToolInput,
        ReadToolInput,
        WriteToolInput,
    )

    assert BashToolInput.__required_keys__ == frozenset({"command"})
    assert EditToolInput.__required_keys__ == frozenset({"path", "edits"})
    assert FindToolInput.__required_keys__ == frozenset({"pattern"})
    assert GrepToolInput.__required_keys__ == frozenset({"pattern"})
    assert LsToolInput.__required_keys__ == frozenset()
    assert ReadToolInput.__required_keys__ == frozenset({"path"})
    assert WriteToolInput.__required_keys__ == frozenset({"path", "content"})


def test_coding_top_level_exports_tool_presentation_helpers() -> None:
    from loushang.coding import (
        ToolResultPresentation,
        get_tool_text_output,
        normalize_display_text,
        render_tool_result_presentation,
        render_tool_result_text,
    )

    assert ToolResultPresentation is not None
    assert get_tool_text_output is not None
    assert normalize_display_text is not None
    assert render_tool_result_presentation is not None
    assert render_tool_result_text is not None


def test_coding_top_level_exports_tool_renderer_types() -> None:
    from loushang.coding import (
        ToolDefinitionResolver,
        ToolRenderContext,
        ToolRenderOutput,
        ToolRenderResultOptions,
        ToolRenderRuntime,
    )

    assert ToolDefinitionResolver is not None
    assert ToolRenderContext is not None
    assert ToolRenderOutput is not None
    assert ToolRenderResultOptions is not None
    assert ToolRenderRuntime is not None


def test_tool_public_types_include_pi_style_compatibility_fields() -> None:
    from loushang.coding.tools import (
        BashToolDetails,
        BashToolInput,
        EditToolDetails,
        GrepToolDetails,
        GrepToolInput,
        LsToolDetails,
        ReadToolDetails,
        ReadToolInput,
    )

    assert {"timeoutSeconds", "artifactDir", "captureFullOutput", "rollingMaxBytes"} <= set(
        BashToolInput.__annotations__
    )
    assert {"full_output_path", "truncation"} <= set(BashToolDetails.__annotations__)
    assert "fullOutputPath" not in BashToolDetails.__annotations__
    assert "firstChangedLine" not in EditToolDetails.__annotations__
    assert {"ignoreCase", "ignore_case"} <= set(GrepToolInput.__annotations__)
    assert "truncation" in GrepToolDetails.__annotations__
    assert {"matchLimitReached", "linesTruncated"} & set(GrepToolDetails.__annotations__) == set()
    assert "entryLimitReached" not in LsToolDetails.__annotations__
    assert "file_path" in ReadToolInput.__annotations__
    assert {
        "image_resized",
        "original_width",
        "original_height",
        "resize_note",
        "resize_unavailable",
        "resize_reason",
    } <= set(ReadToolDetails.__annotations__)


def test_tool_details_contract_annotations_cover_stable_result_fields() -> None:
    from loushang.coding.tools import (
        BashToolDetails,
        EditToolDetails,
        FindToolDetails,
        GrepToolDetails,
        LsToolDetails,
        ReadToolDetails,
        WriteToolDetails,
    )

    expected_keys = {
        BashToolDetails: {
            "exit_code",
            "stderr",
            "stdout_total_lines",
            "stdout_total_bytes",
            "stderr_total_lines",
            "stderr_total_bytes",
            "truncated",
            "truncation",
            "full_output_path",
            "stdout_artifact_path",
            "stderr_artifact_path",
        },
        ReadToolDetails: {
            "path",
            "is_image",
            "truncated",
            "truncation",
            "image_omitted",
            "image_resized",
            "resize_unavailable",
            "resize_reason",
        },
        GrepToolDetails: {
            "path",
            "matches",
            "truncated",
            "match_limit_reached",
            "lines_truncated",
            "truncation",
        },
        FindToolDetails: {
            "path",
            "matches",
            "truncated",
            "result_limit_reached",
            "truncation",
        },
        LsToolDetails: {
            "path",
            "truncated",
            "entry_limit_reached",
            "truncation",
        },
        EditToolDetails: {"path", "applied_edit_count", "diff", "first_changed_line"},
        WriteToolDetails: {"path", "bytes_written", "operation"},
    }

    for details_type, keys in expected_keys.items():
        assert keys <= set(details_type.__annotations__)
