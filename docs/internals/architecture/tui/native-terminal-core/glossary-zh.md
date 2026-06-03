# Native Terminal Core 中英文术语对照表

本文档是 [Glossary](./glossary.md) 的中文对照表，用于团队讨论、迁移沟通和实现计划编写。英文术语仍以 `glossary.md` 为规范源。

## 核心心智模型

原生终端 TUI 不是在一块空白画布上画界面。它是在用户正在使用的终端里工作：上面可能已有 shell 输出，用户可以滚动历史，窗口可能随时改变大小，模型输出和键盘输入也可能同时发生。因此，运行时只把属于当前 TUI 的那一部分终端管理成一个可预测的逻辑屏幕。每次渲染时，运行时先生成完整的当前界面，再和上一次成功显示的界面比较，只写入下一帧需要的终端操作。这个模型是避免闪烁、重复行、光标漂移、输入错位和破坏 scrollback 的基础。

## 一、终端与屏幕模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Native Terminal | 原生终端 | 用户正常使用的终端屏幕和 scrollback。主编码流程在这里运行，不要求进入 fullscreen alternate screen。 |
| Alternate Screen | 备用屏幕 | 独立的全屏终端缓冲区，常见于编辑器和全屏 TUI。主编码流程不应依赖它。 |
| Physical Terminal | 物理终端 | 实际终端设备及其尺寸、视口、光标、模式、scrollback 和能力。 |
| Viewport | 可视窗口 | 当前可见的终端行列区域。输出、滚动或用户滚动都会改变它。 |
| Scrollback | 终端历史 | 终端拥有的历史区域。已提交的对话记录应能通过正常 scrollback 查看。 |
| Hardware Cursor | 硬件光标 | 由终端控制序列移动的真实终端光标。运行时拥有它的位置控制。 |
| Terminal Capability | 终端能力 | 当前终端支持的能力，如 truecolor、同步更新、超链接、括号粘贴、焦点事件、鼠标跟踪或图片协议。 |
| Terminal Writer | 终端写入器 | 唯一向 stdout 写入终端控制序列和文本的代码路径，由运行时拥有。 |

### 终端能力与环境感知

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Terminal Capability Detection | 终端能力探测 | 通过终端 query、环境变量和保守 fallback 规则识别可选能力，并向 renderer 和 UI part 提供稳定能力快照。 |
| Terminal Environment Detection | 终端环境识别 | 识别 tmux、screen、Kitty、Ghostty、WezTerm、iTerm2、VS Code terminal、Windows Terminal、Termux、SSH 等上下文，用于能力、输入协议、resize、剪贴板和 fallback 决策。 |
| Image Protocol | 图片协议 | 终端内联图片协议，如 Kitty graphics 或 iTerm2 inline image。必须受能力控制，不安全时降级为文本描述。 |
| Cell Dimensions | 单元格像素尺寸 | 一个终端 cell 的像素宽高，用于图片缩放；区别于文本占用列数的 Cell Width。 |
| Terminal Restoration | 终端状态恢复 | 退出时恢复 raw/cbreak 模式、显示光标、关闭临时键盘协议、关闭括号粘贴，并按需排空残留输入。 |

常见终端环境探测提示：

| 探测方式 | 说明 |
| --- | --- |
| `TMUX` / `TERM=tmux-*` / `TERM=screen-*` | 默认关闭 images + hyperlinks。 |
| `KITTY_WINDOW_ID` / `TERM_PROGRAM=kitty` | 使用 Kitty 图像协议。 |
| `GHOSTTY_RESOURCES_DIR` / `TERM_PROGRAM=ghostty` / `TERM` 包含 `ghostty` | 使用 Kitty 图像协议。 |
| `WEZTERM_PANE` / `TERM_PROGRAM=wezterm` | 使用 Kitty 图像协议。 |
| `ITERM_SESSION_ID` / `TERM_PROGRAM=iTerm.app` | 使用 iTerm2 图像协议。 |
| `TERM_PROGRAM=vscode` | trueColor + hyperlinks，无图像协议。 |
| `COLORTERM=truecolor` / `COLORTERM=24bit` | trueColor。 |
| `WT_SESSION` | Windows Terminal trueColor。 |

## 二、渲染模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Logical Screen | 逻辑屏幕 | 当前活跃 render tree 在 diff 前生成的完整逻辑行列表。它可以包含当前可见窗口上方、但仍属于活跃 UI 树的行，也包含底部临时 UI。它不是完整终端历史，也不是完整持久会话历史。 |
| Active Logical Screen | 活跃逻辑屏幕 | 当前由 TUI runtime 拥有并参与渲染规划的逻辑屏幕。它是当前活跃 render tree 的完整行数组，不是完整会话归档，也不只是终端可见窗口；可包含 header、chat/transcript、pending、status、widget、editor、footer、overlay 等当前 UI 区域。 |
| Logical Line | 逻辑行 | 带文本、样式和宽度信息的渲染行。测量使用终端单元格宽度，而不是字符串长度。 |
| Render Tick | 渲染周期 | 一次运行时渲染尝试：收集状态、渲染树、计算终端操作并通过终端写入器刷新。 |
| Render Pass | 渲染遍 | 渲染周期中求值 renderable tree 的步骤，只产出渲染结果，不写终端。 |
| Render Operation | 渲染操作 | 运行时规划的终端写操作，如移动光标、写行、清行、显示或隐藏光标、同步刷新。 |
| Differential Rendering | 差分渲染 | 行级比较当前逻辑行和上次已渲染逻辑行，在安全时只写必要变更；稳定路径不做字符级终端 diff。 |
| Reflow | 重排 | 在宽度变化或内容变化后重新计算换行、布局和光标映射。必须保持记录顺序且不重复已提交内容。 |
| Resize-Stable Reflow | 尺寸稳定重排 | 终端尺寸变化后，根据新宽高约束重新计算 renderable tree、软换行、区域高度和光标位置，并通过安全差分刷新或 resize repaint 更新受管视口。不得重复对话记录、丢失输入、错位编辑器或状态区，也不得产生明显全屏闪烁。 |
| Full Recompose | 全量重组 | 重新渲染完整 renderable tree 生成当前逻辑行。常用于 resize、主题变化、overlay 变化和内容更新；不等于清屏。 |
| Full Repaint | 全量重绘 | 根据当前逻辑行重写 runtime-managed 可见区域。可用于首次渲染、resize、受限高度恢复、overlay 几何变化或不安全视口转换；不同于清除 scrollback。 |
| Resize Repaint | 尺寸重绘 | 由终端宽高变化触发的全量重绘路径。优先保证 composer、status、overlay、光标映射和临时区域在 resize 后稳定。 |
| Clear Scrollback | 清除终端历史 | 清除终端历史的控制操作，如支持 CSI 3 J 的终端。它和全量重绘是不同概念，默认用于 resize repaint；稳定差分更新不得使用它。 |
| History Preservation Policy | 历史保留策略 | 控制 runtime 如何保留终端历史的产品策略。默认是 best effort：稳定流式输出保留 scrollback，resize 使用确定性重绘并默认清除 scrollback；需要保留 shell 历史的部署可以显式关闭 resize clear scrollback。 |
| Synchronized Update | 同步更新 | 终端支持时让多次写入作为一个视觉帧出现的更新模式。 |
| Managed Viewport | 受管视口 | 运行时认为自己拥有或可以安全原地更新的行集合。不能授权重写任意历史 scrollback。 |
| Unsafe Viewport Transition | 不安全视口转换 | 运行时无法证明旧行仍在预期物理位置的状态变化，如外部 stdout 写入、影响受管行的滚动或 resize/reflow 失效。 |
| Previous Rendered Lines | 上次已渲染行 | 上一次成功刷新后的逻辑行快照。它是 overlay 合成、光标标记提取、行规范化后的差分基线，不是持久对话记录；可包含可见窗口上方仍在活跃 UI 树中的行，也可在 compaction、导航、清空、force render、resize repaint 或 UI 重建后被替换或缩短。 |
| Current Logical Lines | 当前逻辑行 | 当前 render pass 产出的完整逻辑行。运行时先渲染 root 树，再合成 overlay、提取光标标记并应用行规范化，然后用于 diff 和写终端。它完整覆盖当前活跃逻辑屏幕，但不等于完整 terminal scrollback 或完整持久会话历史。 |
| Changed Line Range | 变更行范围 | 当前逻辑行和上次已渲染行之间最小的连续变更范围。 |
| Append Update | 追加更新 | 当前逻辑行只在末尾追加时使用的差分路径，有利于终端自然滚动并避免重写历史内容。 |
| Rendered Line Array | 已渲染行数组 | render loop 使用的具体有序终端就绪行数组。当前数组和上一次成功数组共同构成下一次终端更新的行级差分基线。该数组只覆盖活跃逻辑屏幕，不能无限保留所有历史行。 |
| Viewport Top | 视口顶部 | 渲染规划中对应第一行可见终端行的逻辑行索引。 |
| Previous Viewport Top | 上次视口顶部 | 上次成功刷新后记录的视口顶部，用于把逻辑行位置转换成相对终端光标移动。 |
| Logical Cursor Row | 逻辑光标行 | 运行时用于规划的逻辑光标行，通常是受管逻辑屏幕末尾。 |
| Hardware Cursor Row | 硬件光标行 | 运行时记录的真实终端光标行；为 IME 或焦点输入定位时可与逻辑光标行不同。 |
| Working Area High-Water Mark | 工作区高水位 | 当前终端会话中运行时渲染过的最大逻辑屏幕高度，用于判断收缩时是否需要清理旧行或恢复重绘。 |
| Recovery Repaint | 恢复重绘 | 在不安全转换、非 resize 恢复、宽度重排或陈旧行条件下重新建立受管视口的全量重绘。它可和尺寸重绘共用实现，但不意味着清除终端历史。 |
| Synchronized Flush | 同步刷新 | 作为一个终端更新发出的渲染刷新，是运行时的终端写入帧边界。 |
| Cursor Marker | 光标标记 | 聚焦 renderable 输出的零宽标记，用于声明逻辑光标位置；运行时会移除标记并映射到硬件光标。 |
| Hardware Cursor Masking | 硬件光标遮蔽 | 渲染写入期间隐藏终端硬件光标，帧写完后再定位并恢复显示，避免用户看到光标穿过输出区或状态行。 |
| Viewport-Relative Cursor Placement | 视口相对光标定位 | 用逻辑光标行减去视口顶部得到可见终端行，再用绝对屏幕坐标定位硬件光标，避免终端自动换行或 IME 行为让下一次输入错行。 |

## 三、对话记录模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Transcript | 对话记录 | 用户可见的对话历史。稳定内容以显示记录表示，并可进入正常终端 scrollback。 |
| Session Store | 会话存储 | 产品拥有的完整持久会话存储，如 JSONL、数据库或分段文件。它可以远大于活跃逻辑屏幕；render loop 不应把它当作每 tick 的已渲染行数组。 |
| Transcript Window | 对话记录窗口 | 产品适配器投影给 TUI 的会话历史子集，用于组成活跃逻辑屏幕。通常包含 compaction summary、保留的最近显示记录、活跃草稿和活跃工具记录。 |
| Evicted Transcript Prefix | 已移出对话前缀 | 不再投影进活跃逻辑屏幕的稳定对话前缀。它仍保存在会话存储中，也可能已经存在于终端 scrollback，但不属于当前逻辑行或上次已渲染行。 |
| Transcript Area | 对话记录区 | 临时 UI 上方的概念区域，由终端 scrollback 支撑，包含稳定对话内容。 |
| Display Record | 显示记录 | 渲染前的产品中立历史数据，如用户提示、助手回复、工具执行、错误、中断或分隔线。 |
| Content Block | 内容块 | 显示记录内部的嵌套内容项，如助手消息中的文本块、思考块和工具调用引用。 |
| Assistant Message Record | 助手消息记录 | 助手输出的显示记录，可包含多个内容块，流式输出时可保持为草稿记录。 |
| Thinking Block | 思考块 | Provider 或产品明确提供给 UI 展示的模型 thinking/reasoning 内容块。TUI 不推断、不编造、不暴露未提供的隐藏推理。 |
| Thinking Visibility | 思考可见性 | 思考块的展示策略，如可见、折叠、按策略隐藏或不可用。折叠时显示标签而不是完整内容。 |
| Tool Execution Record | 工具执行记录 | 一次工具调用生命周期的显示记录，包含工具名、输入摘要、运行状态、输出、截断、错误、折叠和耗时标记。 |
| Tool Timing Marker | 工具耗时标记 | 工具执行记录上的耗时标签。运行中可显示 elapsed，完成后可显示 took。不同于整个运行的 worked divider。 |
| Error Record | 错误记录 | 不属于具体工具执行记录的运行时、provider、产品或可恢复 TUI 错误记录。 |
| Tool Error | 工具错误 | 工具执行记录内部的错误状态，如命令失败、权限拒绝、超时、取消或失败输出被截断。 |
| Committed Transcript Block | 已提交对话块 | 可保留在 scrollback 中的稳定输出块，如用户提示、最终助手回复、工具摘要、错误或完成分隔线。 |
| Draft Record | 草稿记录 | 仍在变化的显示记录，如流式助手回复；完成后才变成已提交内容。 |
| Commit | 提交 | 从临时或草稿状态转为稳定对话内容的过程。提交后临时渲染不得再修改它。 |
| Working Line | 工作行 | 运行中显示的临时行，报告耗时和中断提示；运行中不是对话历史。 |
| Worked Divider | 完成分隔线 | 运行完成后提交的稳定分隔块，如 `Worked for 28.6s`，替代临时 working line。 |

## 四、布局模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Screen Region Stack | 屏幕区域栈 | 由 screen root 组装的垂直区域容器序列，用于在终端 diff 前定义屏幕组成。 |
| Region Container | 区域容器 | 拥有一个命名屏幕区域的 renderable。UI parts 和对话视图放入这些稳定槽位。 |
| Header Area | 头部区域 | 可选区域，用于启动提示、onboarding、更新日志摘要或产品介绍内容；默认不是固定 chrome。 |
| Transcript Render Area | 对话记录渲染区 | 渲染显示记录、草稿记录和对话 UI parts 的区域容器，可自然滚入终端 scrollback。 |
| Bottom Frame | 底部框架 | 视口底部由运行时拥有的可变区域，包含 surface、队列、工作行、编辑器、分隔和状态。 |
| Transient Area | 临时区域 | 可原地重绘的运行时 UI 区域，包括 surface、队列、工作行、编辑器、分隔和状态区域。 |
| Extension Widget Slot | 扩展部件槽 | 产品适配器或扩展可插入临时 UI 的可选区域，可位于编辑器上方或下方。 |
| Surface Area | 表面区域 | 编辑器上方托管临时交互 surface 的底部框架区域。非 overlay surface 默认放在这里。 |
| Pending Queue Area | 待处理队列区 | 展示已提交但尚待产品处理的 follow-up、steering 或其他动作的底部框架区域。 |
| Working Line Area | 工作行区域 | 展示运行进度和中断提示的区域，如 `Working 3.01s`；运行结束或中断后消失。 |
| Composer Area | 编辑器区域 | 包含可编辑输入的区域。输入软换行或显式换行时向上增长。 |
| Separator Area | 分隔区域 | 编辑器和状态区域之间的可选视觉间隔或分隔线。默认 coding 布局中是一行空行。 |
| Status Area | 状态区域 | 默认最底部的一行状态区。空间不足时省略或截断低优先级字段；默认渲染器避免写满最后一个终端单元，防止底行自动换行伪影。 |
| Footer Area | 页脚区域 | 可选底部区域，用于产品状态或自定义 footer。默认 coding 布局中 status area 就是 footer area。 |
| Screen Root | 屏幕根 | 顶层 renderable，负责把对话记录和底部框架 UI 组装成逻辑屏幕，不拥有终端写入权。 |
| Layout Policy | 布局策略 | 决定区域是否存在、优先级以及在宽高受限时如何收缩或隐藏的配置。 |

## 五、渲染框架术语

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Renderable | 可渲染对象 | 框架级渲染协议。接收约束，返回渲染结果和可选输入/焦点声明，不直接写终端。 |
| Container | 容器 | 拥有子 renderable 布局的 renderable，决定顺序、约束、裁剪和焦点遍历。 |
| Focusable | 可聚焦对象 | 可接收键盘输入并声明逻辑光标位置的 renderable。返回意图或状态变化，不拥有输入循环。 |
| Focus | 焦点 | 运行时管理的键盘输入接收权。同一时间只有一个 renderable 或 surface 持有焦点。 |
| Surface | 临时表面 | 由 TUI 运行时托管的临时交互 renderable，如 autocomplete、命令面板、模型选择器、设置、帮助或确认框。 |
| Overlay | 覆层 | surface 的一种展示模式，可覆盖或浮在其他区域之上。几何位置和层级由运行时或 surface host 控制。 |
| Surface Host | 表面宿主 | 运行时拥有的 renderable，管理 surface 生命周期、焦点捕获、关闭原因、堆叠和焦点恢复。 |
| Selection Surface | 选择表面 | 从列表中选择一个或多个项目的 surface，拥有显示、导航、过滤、选择状态和关闭原因。 |
| Approval Surface | 授权表面 | 用于权限或授权决策的 surface，如允许命令、文件编辑或网络访问。返回明确授权意图。 |
| Dialog Surface | 对话表面 | 用于简单确认、取消或确认知悉的聚焦 surface，不应隐式提交编辑器文本。 |
| Approval Intent | 授权意图 | 授权表面返回的语义结果，是产品适配器输入；TUI 不直接执行受保护动作。 |
| Close Reason | 关闭原因 | surface 关闭的明确原因，如 confirm、cancel、escape、abort、blur、replaced 或 completed。 |
| Render Constraint | 渲染约束 | 渲染时传给 renderable 的宽高预算。Renderable 必须遵守约束或受控报告溢出。 |
| Render Result | 渲染结果 | renderable 渲染调用的结构化输出，包含逻辑行、可选光标声明和运行时元数据。 |

## 六、UI 部件术语

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| UI Part | UI 部件 | 由 renderables 构建的具体、可见、可复用 UI 单元，如编辑器、状态栏、队列视图、工具执行视图或授权提示。 |
| Basic Parts | 基础部件 | 文本、截断文本、空白、盒子、边框、加载器等基础 UI 部件族。 |
| Input Parts | 输入部件 | 编辑器、文本输入、自动补全视图等输入相关 UI 部件族。 |
| Status And Frame Parts | 状态与框架部件 | 状态栏、工作行、待处理队列视图等底部框架 UI 部件族。 |
| Transcript Parts | 对话记录部件 | 用户提示视图、助手消息视图、思考视图、工具执行视图、错误视图、Markdown、代码、图片和 diff 块等。 |
| Selection And Surface Parts | 选择与表面部件 | 选择列表、设置列表、命令面板、授权提示、对话视图、帮助查看器和更新日志查看器等。 |

## 七、输入模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Input Event | 输入事件 | 由终端输入读取器生成的标准化键盘、粘贴、鼠标、焦点、尺寸变化或信号事件。 |
| Signal | 信号 | 会影响运行时的操作系统或终端信号，如 resize、interrupt、terminate、suspend 或 resume。 |
| Keybinding | 键绑定 | 从输入事件到动作或意图的映射。键绑定由运行时或产品适配器配置拥有。 |
| Intent | 意图 | 由 renderable、UI part、surface 或产品适配器返回的语义动作，如提交提示、打开命令表面、选择项目、授权决策或中止运行。 |
| Composer | 编辑器 | 用于提示文本、后续文本、steering 文本和斜杠命令输入的可编辑输入 UI 部件。 |
| Soft Wrap | 软换行 | 由终端宽度引起的视觉换行。不会在编辑器缓冲区中插入换行符。 |
| Explicit Newline | 显式换行 | 通过配置的键绑定插入编辑器缓冲区的换行符，是提交文本的一部分。 |
| Cursor Declaration | 光标声明 | 聚焦 renderable 报告的逻辑光标位置；运行时在换行、宽度计算和布局后映射到物理终端单元格。 |
| Bracketed Paste | 括号粘贴 | 一种终端模式，将粘贴文本标记为粘贴输入，避免把粘贴换行或转义序列误当普通按键。 |
| Paste Event | 粘贴事件 | 包含粘贴文本的标准化输入事件。作为一次编辑操作路由给聚焦输入对象；其中的换行插入编辑器缓冲区，不能提交提示。 |
| Paste Marker | 粘贴标记 | 大段粘贴内容的紧凑编辑器表示，如 `[paste #1 +123 lines]`。完整粘贴内容仍保留用于编辑、提交和撤销；光标移动和删除应把标记当作原子字素单元。 |
| Paste Safety | 粘贴安全 | 粘贴的终端控制序列不得被终端执行。运行时或编辑器必须按产品策略将其作为惰性文本插入、转义显示、过滤，或用简洁错误拒绝。 |
| Undo Stack | 撤销栈 | 编辑器的编辑操作历史，用于撤销和重做文本变化。一次粘贴通常应是一个撤销步骤。 |
| Kill Ring | 剪切环 | 编辑器保存被剪切文本的缓冲，用于删除到行尾、删除单词、粘回等操作；不是对话记录。 |
| Abort | 中止 | 请求取消或中断活跃运行的控制动作，不是提示文本。surface 激活时 surface 处理优先于运行中止。 |

### 终端输入协议模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Keyboard Protocol | 键盘协议 | 终端报告按键的协议，用于区分普通键、修饰键、释放事件、键盘布局和以 Escape 开头的歧义序列。 |
| Keyboard Protocol Negotiation | 键盘协议协商 | 启动时 query 协议支持、启用最佳协议、记录激活状态并在退出时关闭对应协议的状态机。 |
| Kitty Keyboard Protocol | Kitty 键盘协议 | 现代键盘协议，可报告 CSI-u、modifier、press/repeat/release 和 base layout key；终端响应 Kitty query 时优先使用。 |
| modifyOtherKeys | modifyOtherKeys 模式 | xterm fallback 键盘模式，在 Kitty 协议不可用时用 CSI 序列表达修饰键。 |
| Escape Sequence | 转义序列 | 以 `ESC` (`\x1b`) 开头的终端控制或输入序列，可表示按键、焦点、鼠标、终端响应、超链接、图片等。 |
| CSI Sequence | CSI 序列 | Control Sequence Introducer，通常以 `ESC [` 开头。方向键、修饰方向键、终端 query、SGR 样式和部分鼠标事件使用 CSI。 |
| OSC Sequence | OSC 序列 | Operating System Command，通常以 `ESC ]` 开头，以 BEL 或 ST 结束。常用于标题、OSC 8 超链接、部分剪贴板集成等。 |
| DCS Sequence | DCS 序列 | Device Control String，通常以 `ESC P` 开头，以 ST 结束。属于终端控制响应，必须等完整后再路由或丢弃。 |
| APC Sequence | APC 序列 | Application Program Command，通常以 `ESC _` 开头，以 ST 结束。Kitty graphics 的部分响应属于这类终端流量。 |
| Escape Disambiguation | Escape 消歧 | 判断收到的 `ESC` 是独立 Escape 键，还是更长转义序列前缀。应由输入组装器结合短 idle deadline 完成。 |
| Input Assembler | 输入序列组装器 | 接收 raw stdin chunk、缓存不完整终端序列，并只在序列完整后产出标准化输入事件的输入层组件。 |
| Pending Sequence | 待完成序列 | 已收到但尚未完整的输入序列前缀，如 lone `ESC`、半截 CSI/OSC 或半截 bracketed paste 标记。 |
| Idle Flush | 空闲刷新 | pending sequence 在短时间内没有后续输入后被冲刷为事件的过程，主要用于发出真正的独立 Escape 键。 |
| Input Drain | 输入排空 | 退出时关闭临时键盘协议后消费残留输入，避免延迟 key release 或终端响应泄漏到父 shell。 |

## 八、Coding 集成术语

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Product Adapter | 产品适配器 | 把产品状态和事件转换为通用 TUI 记录、UI 部件、surface、状态快照和意图的层。 |
| Run | 运行 | 产品级工作单元，如一次 agent turn。TUI core 只知道产品适配器暴露的 running/idle 状态。 |
| Thinking Level | 思考等级 | 产品或模型的 reasoning effort 设置，如 off、minimal、low、medium、high、xhigh。可出现在状态快照中。 |
| Follow-Up | 后续输入 | 运行中提交的普通用户输入，会排队到下一轮，而不是发送给当前运行。 |
| Steer | 实时引导 | 运行中提交并在支持时发送给当前运行的输入，必须和 queued follow-up 可见地区分。 |
| Pending Queue | 待处理队列 | 展示尚未被产品处理的已提交输入，可包含 follow-up、steering 或其他待处理动作。 |
| Slash Command | 斜杠命令 | 请求命令选择或命令执行路径的编辑器输入。TUI 负责建议展示和导航，产品适配器负责语义。 |
| Status Snapshot | 状态快照 | 产品提供给状态区域的数据，如模型、cwd、分支、session id、上下文使用量、配额或运行状态。 |
| Concise Error | 简洁错误 | 面向用户的短错误块，默认不输出 Python traceback；只有显式 verbose diagnostics 才展示详细堆栈。 |

## 九、文本测量术语

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Cell Width | 单元格宽度 | 文本占用的终端列数，区别于字节长度或字符串长度。用于换行、截断、diff 和光标定位。 |
| Grapheme Cluster | 字素簇 | 用户感知上的一个字符，可能由多个 Unicode code points 组成，如 emoji 序列或组合符号。 |
| ANSI SGR | ANSI 样式序列 | 用于颜色、粗体、斜体、下划线或 reset 的 ANSI 样式控制序列，单元格宽度为零。 |
| OSC 8 Hyperlink | OSC 8 超链接 | 终端超链接控制序列，宽度为零，不能破坏换行或光标映射。 |

## 十、样式与主题术语

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Theme | 主题 | renderable、UI part 和 renderer 使用的结构化样式 token 集。描述期望样式，由运行时或样式解析器按终端能力降级。 |

## 十一、扩展边界术语

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Extension | 扩展 | 通过公共 API 添加命令、surface、renderer 或状态字段的外部或产品提供代码。不得直接写终端输出。 |
| Public TUI API | 公共 TUI API | `loushang.tui` 暴露给产品适配器和扩展的稳定 API。 |
| Capability Degradation | 能力降级 | 当终端或环境缺少可选能力时的 fallback，如超链接变纯文本、truecolor 降级为基础颜色、图片降级为文本或文件引用。 |

## 十二、避免术语

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Component | Component（避免使用） | loushang native terminal core 文档中的非规范术语。框架协议用 Renderable，可见部件用 UI Part。仅在引用或映射外部系统时使用。 |
