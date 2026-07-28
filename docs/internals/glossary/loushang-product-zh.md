# Loushang Product 与 OEM 中文术语对照表

本文档是 [Loushang Product And OEM Glossary](./loushang-product.md) 的中文
对照表，用于团队讨论、架构评审和实现计划编写。英文术语及完整边界定义以
`loushang-product.md` 为规范源。

## 核心心智模型

```text
平台 CLI 或 OEM CLI
  → 平台宿主
  → OEM 配置
  → Product 注册表
  → Product 路由器
  → Product 工厂
  → 每个 Product Session 只有一个活跃 Product Runtime
       → Product 内核
       → 已准入的 Capability Pack
       → 已激活的 Product Capability Bundle
       → Product 批准的 Plugin 贡献
```

Harness 提供产品中立机制；Product 提供领域语义、默认值与策略；OEM 选择并
覆盖多个 Product；Plugin 只能在 Product 和 OEM 准入后贡献可选资源或行为。

## 平台与启动模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Platform | 平台 | 可发现、注册并承载一个或多个 Product 的 Loushang 系统；平台本身不是领域 Product。 |
| Platform Host | 平台宿主 | 进程级组合根，负责 Product 发现、OEM 选择、Product 路由、共享服务和运行时释放。 |
| Platform CLI | 平台 CLI | 中立的 `loushang` 命令入口，根据显式参数或配置选择 OEM 与 Product。 |
| OEM CLI | OEM CLI／OEM 品牌命令 | 如 `acme` 的 OEM 品牌入口；调用共享平台启动机制，不复制 Product 启动逻辑。 |
| Default OEM | 缺省 OEM | 启动请求未指定 OEM 时使用的 OEM Profile。 |
| Default Product | 缺省 Product | OEM 或平台未收到显式 Product 选择时启动的 Product。 |

`loushang.<OEM>.cli` 可以是某个实现模块路径，但不是架构概念或强制打包规范。
平台应通过已注册且已信任的描述符加载 OEM，而不是从未校验字符串拼接导入路径。

## Product 模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Product | 产品 | 拥有领域目标、语言、Prompt、能力默认值、策略、上下文、Artifact、Session 兼容性和呈现语义的完整领域体验。 |
| Product Kernel | Product 内核／产品内核 | 不能因 Harness 可复用机制增加而迁出的领域语义与策略。 |
| Product Adapter | Product 适配器／产品适配器 | 把 Product 内核绑定到 Harness、Agent、Work、Channel、TUI 等共享机制的代码。 |
| Product Package | Product 包／产品包 | 提供 Product Descriptor、Factory、Adapter 和内置资源的可安装软件分发。 |
| Product Descriptor | Product 描述符 | 不创建运行时的数据注册记录，至少包含稳定 `product_id`、版本、API 兼容信息和工厂引用。 |
| Product Factory | Product 工厂 | 根据已准入的平台、OEM、工作区、Channel 和 Session 上下文创建 Product Runtime。 |
| Product Registry | Product 注册表 | 当前 Platform Host 已准入 Product Descriptor 的确定性目录。 |
| Product Router | Product 路由器 | 为启动、请求、工作区或持久化 Session 选择已注册 Product 的机制。 |
| Product Runtime Plan | Product 运行时计划 | Product 声明的能力槽、默认选择、可覆盖来源和配置；不包含 live object 或凭证。 |
| Resolved Runtime Profile | 已解析运行时配置 | 将 Product、OEM、Extension 和 Session 层确定性合成后的能力选择。 |
| Product Runtime | Product 运行时 | Product Factory 创建的一个活跃、已绑定执行实例。 |
| Active Product | 活跃 Product | 拥有当前 Product Session，并解释其输入、上下文、策略、Artifact 和呈现的 Product。 |
| Product Session | Product 会话 | 由一个 Product 及其 Session schema 和兼容策略拥有的持久或临时交互范围。 |
| Product Handoff | Product 移交 | 在不同 Product Session 之间显式转交 Work、Artifact 引用或用户意图。 |

一个 Product Session 恰好有一个 Active Product。平台可以同时承载多个 Product，
但不能在不迁移的情况下把一个 Session 的 `product_id` 原地改成另一个 Product。

## OEM 模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| OEM | OEM／OEM 配置 | 选择 Product，并覆盖其允许配置、资源、能力、模型、权限、Channel 和品牌呈现的平台配置。 |
| OEM Package | OEM 包 | 提供 OEM Profile、可选 OEM CLI、资源覆盖、Extension、品牌与 Product 可用策略的可安装分发。 |
| OEM Profile | OEM 配置描述 | 声明启用的 Product、缺省 Product、Product 覆盖、共享 Extension、品牌、模型和权限策略的数据配置。 |
| OEM Layer | OEM 层 | 应用到 Product 已声明覆盖点的 OEM 选择或资源；不能修改 Product 封闭的 Capability Slot。 |
| Multi-Product OEM | 多 Product OEM | 在同一个 Platform Host 中准入并配置多个 Product 的 OEM Profile。 |
| OEM Product | OEM 自有 Product | 仅指 OEM 确实定义独立 Product 内核与 `product_id` 的情况。 |

OEM 通常不是 Product。一个 OEM Package 可以启用 `coding`、`ppt` 和
`environmental` 等多个 Product，也可以把 Coding 设为缺省 Product。

## 能力组合模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Capability | 能力 | 可命名的运行时或领域关注点，如 Store、Memory、Tool、Command、Deck Renderer 或 Artifact Handler。 |
| Capability Slot | 能力槽 | Product 声明的能力绑定位置，定义组合形态、生命周期范围、刷新边界和允许来源。 |
| Capability Pack | 能力包 | 运行时准入后，针对单一能力项类型的有序贡献组；对应代码中的 `CapabilityPack[T]`。 |
| Product Capability Bundle | Product 能力组合包 | 面向装配或分发、包含多种能力与资源类型的组合，如 `ppt-authoring`。 |
| Capability Mount | 能力挂载 | Product 在特定运行时范围内激活已准入 Capability Pack 或 Product Capability Bundle 的动作。 |

`CapabilityPack[T]` 不是安装包。它只组合一种 `T`，例如 Tool 或 Command。
`ppt-authoring` 如果同时包含 Skill、Prompt、Tool、Command、Deck Asset、
Renderer 和 Artifact Handler，应称为 Product Capability Bundle。

Coding 挂载 `ppt-authoring` 后仍是 Active Product；如果需要 PPT 专属 Canvas、
Session、Compaction、审批或 Deck 生命周期，应通过 Product Handoff 进入 PPT
Product。

## Package、Plugin、Extension 与资源模型

| 英文术语 | 中文术语 | 中文简介 |
| --- | --- | --- |
| Package | 包（需加限定词） | 架构文档中必须写成 Product Package、OEM Package 或 Resource Package。 |
| Resource Package | 资源包 | 可安装或物化的 Skill、Prompt、Theme、Extension 和 Product Asset 集合。 |
| Plugin | 插件 | 可选、可独立启停的资源根或 Extension 贡献来源；受 Product/OEM 信任与激活策略控制。 |
| Extension | 扩展 | 通过约定扩展面贡献的可执行或声明式行为，如 Tool、Command、Hook、Policy、Renderer 或 Channel Adapter。 |
| Skill | 技能／Skill | 教给模型专业工作流、领域约定或 Tool 使用方式的指令资源，不代表执行权限。 |
| Product Asset | Product 素材／产品素材 | 由 Product 解释的领域文件，如模板、布局、品牌包、图片或设计素材。 |
| Deck Asset | Deck 素材／演示文稿素材 | PPT 领域的 Product Asset，如演示模板、Slide Layout、Master、Theme、Brand Kit 或媒体。 |

Deck Asset 可以来自 PPT Product、OEM 覆盖或 Product Capability Bundle，但不应
为了复用相对文件路径而被建模成 Skill。

## 启动关系示例

缺省平台启动：

```text
loushang
  → 解析 Default OEM
  → 解析该 OEM 的 Default Product
  → 创建对应 Product Runtime
```

OEM 品牌启动 Coding 并挂载 PPT 创作能力：

```text
acme
  → 使用 "acme" OEM Profile 启动共享 Platform Host
  → 选择 "coding" Product
  → 挂载已准入的 OEM 能力与 ppt-authoring 能力组合包
```

完整 PPT Product：

```text
loushang ppt
  → 选择 "ppt" Product
  → 创建 PPT Product Session
```

## 避免混用的术语

| 避免术语 | 应改用 |
| --- | --- |
| Product Plugin | Product Package；如果同时实现 Plugin 合约，明确写出两个角色。 |
| PPT Skill Pack | 仅包含 Skill 时使用；跨 Skill、Tool、素材等类型时用 Product Capability Bundle。 |
| OEM Product | OEM CLI、OEM Profile、OEM Package、带 OEM Layer 的 Product，或真正拥有独立 `product_id` 的 OEM Product。 |
| Multi-Product Session | 部署可用性用 Multi-Product OEM；跨 Product 转交用 Product Handoff；真正统一语义时定义新的 Product。 |
| `loushang.<OEM>.cli` | 这是实现路径；架构术语用 OEM CLI、注册入口和 Platform Host。 |
