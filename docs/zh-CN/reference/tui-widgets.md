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

支持样式的 P0A 控件可以接收 `ThemeResolver`。第一批稳定 token 如下：

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

## 计划中的控件目录

`Toolbar`、`Menu`、`Popover`、`ProgressBar`、`Spinner`、`Badge`、`StatusPill`、
`KeyValueList`、`Tabs`、`Table`、`TreeView`、`Toast` 和 `TextArea` 是计划中的
目录项，不属于 P0A 实现范围。

## 示例

- [examples/tui/43_widgets_foundation.py](../../../examples/tui/43_widgets_foundation.py)：
  一个包含表单和确认对话框的键盘操作 widget 小应用。
