from __future__ import annotations

from loushang.harness.session.cwd_audit import audit_cwd_bound_services


def test_cwd_audit_reports_project_root_mismatch(tmp_path) -> None:
    session_cwd = tmp_path / "project" / "src"
    project_root = tmp_path / "other"

    result = audit_cwd_bound_services(
        session_cwd=session_cwd,
        project_root=project_root,
    )

    assert result.ok is False
    assert result.issues[0].code == "settings_project_cwd_mismatch"


def test_cwd_audit_accepts_matching_resource_cwd(tmp_path) -> None:
    cwd = tmp_path / "project"

    result = audit_cwd_bound_services(session_cwd=cwd, resource_cwd=cwd)

    assert result.ok is True
