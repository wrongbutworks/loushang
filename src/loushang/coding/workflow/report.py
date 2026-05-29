from __future__ import annotations

import json

from loushang.coding.workflow.schema import WorkflowResult


def format_workflow_report(result: WorkflowResult, *, include_header: bool = True) -> str:
    lines = [f"workflow: {result.name}"] if include_header else []
    for step in result.step_results:
        status = "PASS" if step.ok else "FAIL"
        lines.append(f"[{step.index}] {status} {step.prompt}")
        if step.error:
            lines.append(f"  error: {step.error}")
        for check in step.checks:
            check_status = "ok" if check.ok else "fail"
            detail = f" - {check.detail}" if check.detail else ""
            lines.append(f"  {check_status}: {check.label}{detail}")
    lines.append("PASS" if result.ok else "FAIL")
    return "\n".join(lines) + "\n"


def format_workflow_json_report(results: tuple[WorkflowResult, ...]) -> str:
    passed = sum(1 for result in results if result.ok)
    failed = len(results) - passed
    payload = {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "workflows": [_workflow_result_payload(result) for result in results],
    }
    return json.dumps(payload, ensure_ascii=False) + "\n"


def _workflow_result_payload(result: WorkflowResult) -> dict[str, object]:
    return {
        "name": result.name,
        "ok": result.ok,
        "events": [
            {
                "type": event.type,
                "text": event.text,
                "data": dict(event.data),
            }
            for event in result.events
        ],
        "steps": [
            {
                "index": step.index,
                "prompt": step.prompt,
                "ok": step.ok,
                "assistant_text": step.assistant_text,
                "error": step.error,
                "checks": [
                    {
                        "label": check.label,
                        "ok": check.ok,
                        "detail": check.detail,
                    }
                    for check in step.checks
                ],
            }
            for step in result.step_results
        ],
    }
