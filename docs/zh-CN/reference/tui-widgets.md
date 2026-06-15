# TUI 控件

[English](../../en/reference/tui-widgets.md) | 中文

`loushang.tui` 提供第一批可复用、键盘友好的控件。它们仍然是普通的
`Renderable` 与 `Focusable` UI part，可用于 `Tui`、`SurfaceHost`、扩展 widget
和 modal surface。

生命周期接线见 [TUI Runner](tui-runner.md)。编辑能力见
[TUI 编辑能力](tui-editing.md)。

## P0A 控件

| 控件 | 用途 |
| --- | --- |
| `Button` / `IconButton` | 单行动作。 |
| `Checkbox` | 布尔表单值。 |
| `Toggle` | 紧凑 on/off 设置。 |
| `RadioGroup` | 互斥选项。 |
| `TextField` | 基于 `TextInput` 的带标签单行输入。 |
| `SelectList` | 基于 `SelectionSurface` 的选择列表。 |
| `Form` / `FormRow` | 局部焦点遍历和同步校验。 |
| `Dialog` / `ConfirmDialog` | modal 组合与 confirm/cancel 流程。 |

## P0B 小控件

| 控件 | 用途 |
| --- | --- |
| `Badge` | 紧凑元信息标签，例如 `beta`、`cached` 或计数。 |
| `StatusPill` | 语义状态标签，例如 `ready`、`warning` 或 `failed`。 |
| `ProgressBar` | 带可选标签和百分比文本的静态单行进度。 |
| `KeyValueList` / `KeyValueItem` | 密集属性摘要和详情面板。 |
| `Toolbar` / `ToolbarAction` | 带局部焦点和激活行为的横向动作组。 |

除 `Toolbar` 会处理自己的局部焦点外，小控件都是普通 `Renderable`。它们适合
dashboard、dialog、状态面板和 extension surface 中的紧凑复用行。

```python
from loushang.tui import Badge, KeyValueList, ProgressBar, StatusPill, Toolbar, ToolbarAction

header = (Badge("beta", kind="info"), StatusPill("ready", status="success"))
progress = ProgressBar(value=42, total=100, label="Indexing", width=12)
details = KeyValueList([("Model", "Kimi"), ("Mode", "safe")])
toolbar = Toolbar([ToolbarAction("Refresh", value="refresh"), ToolbarAction("Cancel", value="cancel")])
toolbar.focus()
```

## P0C 轻量控件

| 控件 | 用途 |
| --- | --- |
| `Menu` / `MenuItem` | 带局部焦点和激活行为的短纵向动作列表。 |
| `Tabs` / `TabItem` | 用于视图切换的横向 selected-value 控件。 |
| `Spinner` | 由调用方驱动 frame 的静态活动指示器。 |

`Menu` 和 `Tabs` 只处理自己的局部状态。`Spinner` 只负责显示：调用方传入
`frame`，并决定何时请求下一次渲染。

```python
from loushang.tui import Menu, MenuItem, Spinner, TabItem, Tabs

tabs = Tabs([TabItem("overview", "Overview"), TabItem("logs", "Logs")])
menu = Menu([MenuItem("open", "Open"), MenuItem("refresh", "Refresh")])
spinner = Spinner(label="Syncing", frame=1)
```

## P1A 数据控件

| 控件 | 用途 |
| --- | --- |
| `Table` / `TableColumn` / `TableRow` | 带局部 active-row 导航的密集行列数据。 |

`Table` 支持固定和弹性列、左/右对齐、禁用行、局部键盘导航和行激活。

```python
from loushang.tui import Table, TableColumn, TableRow

table = Table(
    [TableColumn("job", "Job"), TableColumn("status", "Status")],
    [TableRow("build", {"job": "Build", "status": "ready"})],
)
table.focus()
```

## P1B 文本控件

| 控件 | 用途 |
| --- | --- |
| `TextArea` | 带确定性光标和 viewport 行为的多行表单文本。 |

`TextArea` 保留换行，普通 `enter` 插入新行，并且可以通过
`editor_input_target()` 嵌入 `Form` 和 `Dialog`。

```python
from loushang.tui import TextArea

notes = TextArea(label="Notes", placeholder="Write notes", height=5)
notes.focus()
```

## P1C 对话输入控件

| 控件 | 用途 |
| --- | --- |
| `QuestionDialog` | 返回结构化 intent 的多行问答输入。 |

`QuestionDialog` 内嵌 `TextArea`：普通 `enter` 插入新行，默认
`ctrl+enter` 提交，`escape` / `ctrl+c` 取消。提交会返回
`question_submit` intent，由调用方决定如何使用答案。

```python
from loushang.tui import QuestionDialog

dialog = QuestionDialog(
    title="Add note",
    question="What should be remembered?",
    placeholder="Write a multi-line answer",
    required=True,
)
dialog.focus()
```

## P1D 树控件

| 控件 | 用途 |
| --- | --- |
| `TreeNode` / `TreeView` | 带局部 active-row 导航和展开状态的静态层级数据。 |

`TreeView` 以 preorder 展平可见节点。`right` 会展开折叠分支，或移动到第一个可用的直接子节点；
`left` 会折叠已展开分支，或移动到最近的可用可见父节点。激活可用节点时，除非节点定义了
`on_select`，否则返回 `InputIntent(kind="select", text=value)`。

```python
from loushang.tui import TreeNode, TreeView

tree = TreeView(
    (
        TreeNode("src", "src", expanded=True, children=(TreeNode("widgets", "widgets"),)),
        TreeNode("tests", "tests"),
    )
)
tree.focus()
```

## P1E Toast 控件

| 控件 | 用途 |
| --- | --- |
| `Toast` / `ToastStack` | 带队列、过期和关闭行为的内联临时消息。 |

`Toast` 是消息载荷。`ToastStack` 拥有队列，并在调用方放置的位置渲染当前可见
toast。Toast 控件不会自动打开 overlay；如果需要 overlay 展示，调用方应自行把
`ToastStack` 放入 overlay 或 surface。
`ToastStack` 是纯 renderable：它不会启动计时器、调度渲染、打开 overlay，也不会自动清理过期
toast。

队列操作都是显式的。`push()` 追加一个 `Toast` 或字符串消息，并返回稳定的 toast
value。`dismiss(value)` 移除可关闭 toast，`dismiss_oldest()` 移除最旧的可见可关闭
toast，`clear()` 清空所有排队 toast，`prune_expired()` 会修改队列并丢弃过期 toast。
`all_toasts()` 返回已存储队列；`visible_toasts()` 会过滤过期项、应用 `max_visible`，
并遵守 `newest_on_top`。

过期时间基于 `created_at_ms + duration_ms`。默认 duration 是 4000 ms；
`duration_ms=None` 会让 toast 一直可见，直到被关闭或清空。渲染和
`visible_toasts()` 会隐藏过期 toast，但不会修改队列；需要移除已存储的过期项时，
调用 `prune_expired()`。

```python
from loushang.tui import ToastStack

stack = ToastStack()
stack.push("Saved", kind="success", title="Config")
```

## P2A 命令面板

| 控件 | 用途 |
| --- | --- |
| `CommandPaletteView` | 基于 `CommandPalette` 数据的可搜索动作/模型选择器。 |

`CommandPalette` 仍然是 coding adapter 使用的数据模型。`CommandPaletteView`
是可聚焦 widget：它渲染这些条目，用简单的大小写不敏感子串匹配过滤，并返回结构化
intent。选择可用条目会返回 `command_select`；取消会返回 `command_cancel`。启用
close flag 时，widget 还会额外返回 `surface_close`。

禁用命令在 `CommandPaletteView` 中保持可见，但键盘导航会跳过它们，激活时不返回
内容。legacy coding palette adapter 在这个 slice 中不会消费 `disabled` 标记。

```python
from loushang.tui import CommandPalette, CommandPaletteItem, CommandPaletteView

palette = CommandPalette(
    (
        CommandPaletteItem("deploy", "Deploy service", "Run deployment pipeline"),
        CommandPaletteItem("archive", "Archive release", "unavailable", disabled=True),
    ),
    title="Commands",
)
view = CommandPaletteView(palette)
view.focus()
```

## P2B 标签页内容

| 控件 | 用途 |
| --- | --- |
| `TabGroup` / `TabPage` | 标签头加持久化页面内容。 |
| `SearchableList` / `SearchableListItem` | 可放入标签页的可搜索长列表。 |

`TabGroup` 组合现有 `Tabs` 与持久化页面内容。`ContentSwitcher` 保持内部实现；
没有提供回调时，选中页面变化会返回结构化 tab-change 对象。

`SearchableList` 拥有查询文本、过滤结果、active 行、viewport offset 和结构化选择结果。
它不编辑设置，也不写入配置。

## 设置页

新的设置页应组合 `PageScaffold`、`Tabs` 或 `TabGroup`、`SearchableList`，
以及 `Toggle`、`RadioGroup`、`SelectList` 等可聚焦控件。产品 adapter 应拥有
setting id、value cycle、持久化和副作用。

## 表单

```python
from loushang.tui import Checkbox, Choice, Form, FormRow, RadioGroup, TextField, Toggle

form = Form(
    [
        FormRow("name", TextField(label="Name", value="tower")),
        FormRow("cache", Checkbox("Enable cache", checked=True)),
        FormRow("mode", RadioGroup([Choice("fast", "Fast"), Choice("safe", "Safe")])),
        FormRow("auto", Toggle("Auto approve")),
    ]
)
form.focus()
```

`Form` 只拥有局部遍历。`tab` 与 `shift+tab` 在直接子控件之间移动。
`FormRow` 提供 `values()` 与 `validate()` 使用的稳定字段 id。

## 选择列表

`SelectList` 默认是嵌入式行为：

```python
SelectList(items, close_on_escape=False)
```

默认情况下，`escape` 返回 `None`，由父级表单或对话框决定是否关闭。
弹出式列表可设置 `close_on_escape=True`，让它返回 `surface_close`。

## 对话框

打开 modal 对话框时，让 dialog 自己成为 surface focus target：

```python
dialog = ConfirmDialog(title="Apply changes?", body=form)
tui.show_overlay(dialog, focus_target=dialog, presentation="modal", anchor="center")
```

Dialog 会先处理 `escape` 和 `ctrl+c`，再委派给内部字段。body 焦点处于激活状态时，
它也会把 `editor_input_target()` 委派给当前可编辑子控件。

## 主题 Token

支持样式的 P0A、P0B、P0C、P1A、P1B、P1C、P1D、P1E 与 P2A 控件可以接收
`ThemeResolver`。第一批稳定 token 如下：

| Token | 作用范围 |
| --- | --- |
| `widget.focus` | 获得焦点且未禁用的控件或行。 |
| `widget.disabled` | 禁用控件或禁用的 radio 选项。 |
| `widget.error` | `TextField` 与 `FormRow` 的错误行。 |
| `widget.field.label` | `TextField` 标签。 |
| `widget.field.help` | `TextField` 帮助信息行。 |
| `widget.button.default` | default button。 |
| `widget.button.primary` | primary button。 |
| `widget.button.danger` | danger button。 |
| `widget.button.ghost` | ghost button。 |
| `widget.dialog.title` | dialog 标题。 |
| `widget.dialog.action` | dialog action 行。 |
| `widget.question.title` | `QuestionDialog` 标题行。 |
| `widget.question.text` | `QuestionDialog` 问题行。 |
| `widget.question.action` | `QuestionDialog` 非激活 action 行。 |
| `widget.question.focus` | `QuestionDialog` 激活 action 行。 |
| `widget.badge.default` | default badge。 |
| `widget.badge.info` | informational badge。 |
| `widget.badge.success` | successful badge。 |
| `widget.badge.warning` | warning badge。 |
| `widget.badge.danger` | dangerous 或 failed badge。 |
| `widget.status.neutral` | neutral status pill。 |
| `widget.status.info` | informational status pill。 |
| `widget.status.success` | successful status pill。 |
| `widget.status.warning` | warning status pill。 |
| `widget.status.danger` | dangerous 或 failed status pill。 |
| `widget.progress.track` | progress bar 未填充轨道。 |
| `widget.progress.fill` | progress bar 已填充区域。 |
| `widget.progress.label` | progress 标签和数字文本。 |
| `widget.keyValue.key` | `KeyValueList` key 列。 |
| `widget.keyValue.value` | `KeyValueList` value 列。 |
| `widget.toolbar.action` | 可用 toolbar action。 |
| `widget.toolbar.focus` | 获得焦点的 toolbar action。 |
| `widget.toolbar.disabled` | 禁用 toolbar action。 |
| `widget.menu.item` | 可用的非激活 menu item。 |
| `widget.menu.focus` | 获得焦点的激活 menu item。 |
| `widget.menu.disabled` | 禁用 menu item。 |
| `widget.menu.description` | menu item 描述。 |
| `widget.tabs.tab` | 可用的未选中 tab。 |
| `widget.tabs.selected` | tab strip 未聚焦时的选中 tab。 |
| `widget.tabs.focus` | tab strip 聚焦时的选中 tab。 |
| `widget.tabs.disabled` | 禁用 tab。 |
| `widget.spinner.frame` | spinner frame 字符。 |
| `widget.spinner.label` | spinner 标签文本。 |
| `widget.table.header` | table header 行。 |
| `widget.table.row` | 可用的非激活 table 行。 |
| `widget.table.focus` | 获得焦点的激活 table 行。 |
| `widget.table.disabled` | 禁用 table 行。 |
| `widget.table.empty` | table 空状态文本。 |
| `widget.tree.row` | 可用的非激活 tree 行。 |
| `widget.tree.focus` | 获得焦点的激活 tree 行。 |
| `widget.tree.disabled` | 禁用 tree 行。 |
| `widget.tree.empty` | tree 空状态文本。 |
| `widget.toast.info` | informational toast 前缀。 |
| `widget.toast.success` | successful toast 前缀。 |
| `widget.toast.warning` | warning toast 前缀。 |
| `widget.toast.danger` | dangerous 或 failed toast 前缀。 |
| `widget.toast.title` | Toast 标题片段。 |
| `widget.toast.message` | Toast 消息片段。 |
| `widget.commandPalette.title` | `CommandPaletteView` 标题行。 |
| `widget.commandPalette.queryLabel` | `CommandPaletteView` 搜索标签。 |
| `widget.commandPalette.queryText` | `CommandPaletteView` 查询文本。 |
| `widget.commandPalette.placeholder` | `CommandPaletteView` placeholder 文本。 |
| `widget.commandPalette.section` | `CommandPaletteView` 分区标签。 |
| `widget.commandPalette.item` | 可用的非激活命令行。 |
| `widget.commandPalette.focus` | 获得焦点的激活命令行。 |
| `widget.commandPalette.disabled` | 禁用命令行。 |
| `widget.commandPalette.description` | 命令描述。 |
| `widget.commandPalette.empty` | 命令面板空状态文本。 |
| `widget.commandPalette.footer` | 命令面板 footer 行。 |
| `widget.textArea.label` | `TextArea` 标签行。 |
| `widget.textArea.placeholder` | `TextArea` placeholder 文本。 |
| `widget.textArea.text` | `TextArea` 正文文本。 |
| `widget.textArea.error` | `TextArea` 错误行。 |
| `widget.textArea.help` | `TextArea` 帮助信息行。 |

## 计划中的控件目录

`Popover` 是计划中的目录项，不属于当前 widget 实现范围。

## 示例

- [examples/tui/43_widgets_foundation.py](../../../examples/tui/43_widgets_foundation.py)：
  一个包含表单和确认对话框的键盘操作 widget 小应用。
- [examples/tui/44_widgets_small_controls.py](../../../examples/tui/44_widgets_small_controls.py)：
  一个组合状态、详情、进度和 toolbar 的紧凑小控件示例。
- [examples/tui/45_widgets_light_controls.py](../../../examples/tui/45_widgets_light_controls.py)：
  一个组合 menu、tabs 和 spinner 的轻量控件示例。
- [examples/tui/46_widgets_table.py](../../../examples/tui/46_widgets_table.py)：
  一个带键盘行选择的密集 table 组合示例。
- [examples/tui/47_widgets_textarea.py](../../../examples/tui/47_widgets_textarea.py)：
  一个在小型表单中进行多行文本输入的示例。
- [examples/tui/48_widgets_question_dialog.py](../../../examples/tui/48_widgets_question_dialog.py)：
  一个返回结构化提交与取消 intent 的多行问答对话框示例。
- [examples/tui/49_widgets_tree.py](../../../examples/tui/49_widgets_tree.py)：
  一个带键盘展开和选择行为的静态层级树示例。
- [examples/tui/50_widgets_toast.py](../../../examples/tui/50_widgets_toast.py)：
  一个带队列、关闭和清空动作的内联 toast stack 示例。
- [examples/tui/51_widgets_command_palette.py](../../../examples/tui/51_widgets_command_palette.py)：
  一个带过滤、导航、选择和取消行为的可搜索命令面板示例。
