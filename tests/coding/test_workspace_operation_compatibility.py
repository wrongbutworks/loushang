from __future__ import annotations


def test_coding_operation_protocols_preserve_harness_owner_identity() -> None:
    import loushang.coding as coding
    import loushang.coding.tools as coding_tools
    from loushang.coding.tools import operations as coding_operations
    from loushang.harness.workspace import operations as harness_operations

    protocol_names = (
        "EditOperations",
        "FindOperations",
        "GrepOperations",
        "LsOperations",
        "ReadOperations",
        "WriteOperations",
    )
    for name in protocol_names:
        harness_protocol = getattr(harness_operations, name)
        assert getattr(coding_operations, name) is harness_protocol
        assert getattr(coding_tools, name) is harness_protocol
        assert getattr(coding, name) is harness_protocol
        assert harness_protocol.__module__ == "loushang.harness.workspace.operations"

    assert coding_operations.ToolOperations is coding_tools.ToolOperations is harness_operations.ToolOperations


def test_coding_local_backend_preserves_harness_owner_identity() -> None:
    import loushang.coding.tools as coding_tools
    from loushang.coding.tools import operations as coding_operations
    from loushang.harness.workspace import operations as harness_operations

    assert (
        coding_operations.LocalToolOperations
        is coding_tools.LocalToolOperations
        is harness_operations.LocalToolOperations
    )
    assert (
        coding_operations.LOCAL_TOOL_OPERATIONS
        is coding_tools.LOCAL_TOOL_OPERATIONS
        is harness_operations.LOCAL_TOOL_OPERATIONS
    )
    assert coding_operations.resolve_operation is harness_operations.resolve_operation
    assert harness_operations.LocalToolOperations.__module__ == "loushang.harness.workspace.operations"
