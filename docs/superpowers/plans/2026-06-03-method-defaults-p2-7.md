# Method Defaults P2.7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add settings-backed default method policy for non-interactive coding turns while preserving explicit CLI flag precedence.

**Architecture:** Store defaults in `loushang.coding.control.MethodSettings`, project them to `loushang.coding.domain.MethodPolicy` in the CLI, and leave `CodingDomainApp` as the only component that loads/projects method resources.

**Tech Stack:** Python dataclasses, existing `SettingsManager`, existing `CodingDomainApp`, pytest, ruff.

---

### Task 1: Method Settings Slice

**Files:**
- Modify: `src/loushang/coding/control/types.py`
- Modify: `src/loushang/coding/control/settings_manager.py`
- Modify: `src/loushang/coding/control/__init__.py`
- Test: `tests/coding/test_settings_manager.py`

- [ ] **Step 1: Write failing settings tests**

Add tests that assert:

```python
from loushang.coding.control import MethodSettings, SettingsManager

manager = SettingsManager(global_settings_path=global_path, project_settings_path=project_path)
assert manager.get_settings().method == MethodSettings()
```

Then add cases for:

- loading `{"method": {"mode": "explicit", "selected_method": "review"}}`
- project settings overriding only `selected_method`
- `update_settings(scope="global", method=MethodSettings(mode="explicit", selected_method="review"))`
- `set_method_settings(MethodSettings(mode="off"), scope="project")`
- `get_method_settings()` returning the effective value

- [ ] **Step 2: Verify tests fail**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_settings_manager.py -q
```

Expected: FAIL because `MethodSettings`, `method`, and settings accessors do not exist.

- [ ] **Step 3: Add `MethodSettings` and config field**

In `src/loushang/coding/control/types.py` add:

```python
@dataclass(frozen=True)
class MethodSettings:
    mode: str = "explicit"
    selected_method: str | None = None
```

Add `method: MethodSettings = field(default_factory=MethodSettings)` to `ControlConfig`.

- [ ] **Step 4: Add settings serialization and patch application**

In `settings_manager.py`:

- import `MethodSettings`
- include `method` in `_control_config_to_patch`
- apply a `method` patch in `_apply_patch`
- accept `method: MethodSettings | Mapping[str, object] | object = _UNSET` in `update_settings`
- serialize `method` through `_serialize_settings_slice`
- add `get_method_settings()`
- add `set_method_settings(...)`

Use the existing `_apply_dataclass_patch(...)` pattern so global/project/session nested patches compose.

- [ ] **Step 5: Export public type**

Export `MethodSettings` from `src/loushang/coding/control/__init__.py` and `__all__` in `types.py`.

- [ ] **Step 6: Verify settings tests pass**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_settings_manager.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/loushang/coding/control tests/coding/test_settings_manager.py
git commit -m "feat: add method settings"
```

### Task 2: CLI Policy From Settings

**Files:**
- Modify: `src/loushang/coding/cli/__main__.py`
- Test: `tests/coding/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests for:

- settings default method applies to `-p`
- settings default method applies to `--mode print`
- settings `mode="off"` suppresses method guidance
- `--method` overrides settings
- `--no-method` overrides settings
- missing configured method reports the existing method-list hint
- unsupported configured mode reports `unsupported method policy mode: auto`

Use the existing `_write_review_method(...)`, `_fake_services(...)`, `FakeRunner`, and fake runtime patterns.

- [ ] **Step 2: Verify tests fail**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_cli.py -k "method" -q
```

Expected: FAIL because CLI ignores method settings.

- [ ] **Step 3: Add settings-to-policy helper**

Change:

```python
def _method_policy_from_args(args: CliArgs) -> MethodPolicy:
```

to:

```python
def _method_policy_from_args(
    args: CliArgs,
    *,
    settings_manager: object | None = None,
) -> MethodPolicy:
```

Resolution:

```python
if args.no_method:
    return MethodPolicy.off()
if args.method is not None:
    return MethodPolicy.explicit(args.method)
settings = _method_settings_from_settings_manager(settings_manager)
if settings is None:
    return MethodPolicy.explicit(None)
if settings.mode == "off":
    return MethodPolicy.off()
return MethodPolicy(mode=settings.mode, selected_method=settings.selected_method)
```

Add `_method_settings_from_settings_manager(...)` following the existing `_tool_settings_from_settings_manager(...)` style:

- first try `settings_manager.get_method_settings()`
- then try `settings_manager.get_settings().method`
- otherwise return `None`

- [ ] **Step 4: Pass resolved settings manager**

In `run_cli(...)`, change the `CodingDomainRequest` call to:

```python
method_policy=_method_policy_from_args(args, settings_manager=settings_manager)
```

- [ ] **Step 5: Verify CLI tests pass**

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_cli.py -k "method" -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/loushang/coding/cli/__main__.py tests/coding/test_cli.py
git commit -m "feat: apply method defaults from settings"
```

### Task 3: Regression And PR Prep

**Files:**
- Modify previous files only.

- [ ] **Step 1: Run focused regression**

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/domain tests/coding/test_cli.py tests/method tests/work -q
```

Expected: PASS.

- [ ] **Step 2: Run settings regression**

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/test_settings_manager.py -q
```

Expected: PASS.

- [ ] **Step 3: Run lint**

```bash
uv --cache-dir .uv-cache run ruff check src/loushang/coding/control src/loushang/coding/cli tests/coding/test_settings_manager.py tests/coding/test_cli.py
```

Expected: PASS.

- [ ] **Step 4: Inspect branch**

```bash
git status --short
git log --oneline --decorate --max-count=5
```

Expected: clean worktree with commits for design, plan, settings, and CLI integration.

- [ ] **Step 5: Push and open PR**

```bash
git push -u origin feature/method-defaults-p2-7
gh pr create --base main --head feature/method-defaults-p2-7 --title "Add method defaults from settings" --body "Closes #45"
```

Expected: PR created for issue #45.
