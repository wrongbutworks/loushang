# Coding DomainApp P2 Minimal Method-Guided Turn Design

## Goal

P2 的目标是在 P1/P1.5 已经具备 method 资源、projection、visibility CLI 的基础上，实现第一版 `CodingDomainApp` 最小闭环。

这个闭环只解决一件事：当用户显式指定 method 时，coding turn 可以由该 method 生成的 guidance 指导执行，并把 `method_id` 继续记录到 work metadata。

成功标准：

- 无 `--method` 时，现有 prompt / print / json / TUI 行为不变。
- 有 `--method <id-or-name>` 时，CLI 可以解析并找到 method。
- `MethodLoader -> MethodCompiler -> MethodProjector` 生成的 guidance 会被注入到本次 coding prompt。
- `WorkRun.method_id` 和 work log payload 能记录显式 method id。
- 缺失 method 时返回清晰错误，不启动 prompt run。
- P2 public API 不暴露 TaskFlow、multi-agent、automatic method selection。

## Scope

### In Scope

- 新增轻量 `loushang.coding.domain` 包。
- 定义 `CodingDomainApp` 或等价 facade。
- 定义 `CodingDomainRequest` / `CodingDomainPreparedTurn` 小数据对象。
- 支持显式 method id/name 解析。
- 使用 P1 method APIs 编译并投影 method guidance。
- 将 guidance 作为 prompt prefix 注入一次 coding turn。
- CLI 增加 `--method <id-or-name>`。
- prompt / print / json 路径传递 `method_id` 到 `CodingWorkShell`。
- focused tests 和 CLI regression。

### Out Of Scope

- 自动 method selection。
- method 持久化为 session selected state。
- TUI method picker。
- TaskFlow / multi-step execution。
- multi-agent collaboration。
- METHOD.md / SOUR.md 标准实现。
- 大规模重构 `AgentSession`。
- 修改 P1 `loushang.method` schema。

## Why This Comes Next

P1/P1.5 已经完成：

- `loushang.method` core types。
- skill-backed method adapter。
- `methods/**/SKILL.md` loader。
- method registry / selector。
- single-turn compiler / projector。
- `method list/show` visibility CLI。
- `WorkRun.method_id` metadata plumbing。

现在缺的是 domain app 边界：谁负责把 method projection 应用到 coding turn。

如果直接把 `MethodLoader` 和 projection 拼接逻辑写进 CLI 或 `AgentSession`，会重新制造耦合。P2 应该先把这层放到 `loushang.coding.domain`，让 CLI 只是调用者，让 `AgentSession` 继续保持现状。

## Recommended Architecture

新增：

```text
src/loushang/coding/domain/
  __init__.py
  app.py
  types.py
```

### `types.py`

Owns:

- `CodingDomainRequest`
- `CodingDomainPreparedTurn`

Suggested shape:

```python
@dataclass(frozen=True)
class CodingDomainRequest:
    user_input: str
    method: str | None = None
    cwd: Path | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class CodingDomainPreparedTurn:
    user_input: str
    method_id: str | None = None
    method_guidance: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
```

`CodingDomainPreparedTurn.user_input` is the final prompt text to send to the current session. P2 keeps this explicit so old session APIs do not need to change.

### `app.py`

Owns:

- `CodingDomainApp`
- method lookup
- method compile/project
- prompt guidance assembly

Suggested shape:

```python
class CodingDomainApp:
    def __init__(
        self,
        method_loader: MethodLoader | None = None,
        method_compiler: MethodCompiler | None = None,
        method_projector: MethodProjector | None = None,
    ) -> None: ...

    def prepare_turn(self, request: CodingDomainRequest) -> CodingDomainPreparedTurn: ...
```

The app is intentionally synchronous in P2 because method loading and projection are local file/resource operations.

## Prompt Guidance Policy

P2 should use a deterministic prefix:

```text
<method guidance>

User request:

<original user input>
```

Where `<method guidance>` is `MethodProjection.system_guidance`.

This is not final prompt assembly architecture. It is a narrow compatibility path that lets current `AgentSession.prompt(...)` keep working while P2 validates the domain app boundary.

Rules:

- No method -> return original user input unchanged.
- Explicit method -> prepend projected guidance.
- Do not mutate session system prompt.
- Do not mutate resource bundle.
- Do not persist selected method.
- Do not apply method to follow-up messages in P2 unless the current print/prompt path already treats them as separate turns.

## CLI Integration

Add:

```text
--method <id-or-name>
```

Behavior:

- Only valid for prompt / text / print / json coding turns.
- Not valid for TUI mode in P2.
- Not valid for RPC mode in P2.
- Not valid for `method list/show` visibility commands.
- Missing method returns `Error: method not found: <id-or-name>` and exit code `1`.

CLI flow:

```text
parse args
resolve print input
if --method:
  CodingDomainApp.prepare_turn(user_input, method)
  pass prepared.user_input to prompt/print/mode runner
  pass prepared.method_id to work-shell capable paths
else:
  existing behavior
```

## Work Integration

P1 already added `CodingWorkShell.submit_coding_turn(..., method_id=...)`.

P2 should thread `method_id` through:

- `run_prompt_command(...)`
- `run_print_mode(...)`
- `PrintMode`
- CLI calls into prompt / print / json runners

This remains metadata-only for Work. Work does not compile or apply methods.

## Relationship To Existing Components

### `loushang.method`

P2 consumes `MethodLoader`, `MethodSelector`, `MethodCompiler`, and `MethodProjector`. It should not modify method schemas.

### `AgentSession`

P2 does not change `AgentSession`. It sends a prepared prompt string through existing `session.prompt(...)`.

### CLI

CLI parses `--method`, asks `CodingDomainApp` to prepare the turn, and routes the resulting text to existing runners.

### Work

Work receives `method_id` only when explicitly present. Work remains an observable execution layer, not a method runtime.

## Error Handling

- Missing method -> `ValueError("method not found: <id-or-name>")` or a small domain-specific exception.
- Loader errors -> formatted CLI error.
- Empty projected guidance -> still allowed if method content is empty, but tests should cover stable formatting.
- `--method` with no prompt -> same prompt-required behavior unless the command is otherwise unsupported.

Avoid a large custom exception hierarchy in P2.

## Testing Strategy

### Unit Tests

Add:

```text
tests/coding/domain/test_coding_domain_app.py
```

Coverage:

- no method returns original prompt unchanged。
- explicit skill-backed method prepends guidance and returns `method_id`。
- explicit `methods/**/SKILL.md` resource works。
- missing method returns clear error。
- `METHOD.md` / `SOUR.md` are still ignored by loader。

### CLI Tests

Extend `tests/coding/test_cli.py`:

- `--method review -p "..."` passes prepared prompt to prompt runner。
- `--method review --mode print "..."` passes prepared prompt to print runner。
- `--method missing -p "..."` returns error before prompt runner。
- no `--method` behavior remains unchanged。
- `--method` in TUI/RPC mode returns unsupported error in P2。

### Work Tests

Extend focused work/prompt tests:

- work log contains `method_id` when explicit method is used。
- work log behavior unchanged without method。

### Regression

Run:

```bash
uv --cache-dir .uv-cache run --extra dev pytest tests/coding/domain tests/coding/test_cli.py tests/method tests/work -q
uv --cache-dir .uv-cache run ruff check src/loushang/coding/domain src/loushang/coding/cli src/loushang/coding/mode src/loushang/coding/prompt_command.py tests/coding/domain tests/coding/test_cli.py
```

## Rollout Plan

### Task 1: Coding Domain Types

Create `loushang.coding.domain.types` and public exports.

### Task 2: CodingDomainApp

Implement method lookup, compile/project, and deterministic prompt guidance assembly.

### Task 3: CLI `--method`

Add parser field and validation. Keep `method list/show` unchanged.

### Task 4: Prompt / Print Integration

Thread prepared prompt and `method_id` through prompt and print/json paths.

### Task 5: Work Metadata

Pass explicit `method_id` into `CodingWorkShell` where work logging is active.

### Task 6: Regression

Run focused CLI, method, work, and domain tests.

## Open Questions

Deferred beyond P2:

- Should TUI support explicit method in startup state?
- Should selected method persist in session metadata?
- Should method guidance be a dedicated prompt part instead of text prefix?
- Should `MethodProjection.temperature` influence provider config?
- Should future DomainApp choose methods automatically based on task?
- Should method guidance apply to follow-up messages?

## Tracking

GitHub issue:

- `#40 P2: CodingDomainApp minimal method-guided turn` - https://github.com/zhnt/loushang/issues/40
