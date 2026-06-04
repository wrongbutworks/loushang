# `resource-descriptors`

## Scope

- skill、method、resource 与 extension 的描述对象

## Objects

### `SkillDescriptor`

归属组件：

- `skill`

角色：

- skill 描述对象

承担语义：

- skill identity
- metadata
- source location
- activation constraints

### `MethodDescriptor`

归属组件：

- `method`

角色：

- 方法资产描述对象

承担语义：

- method identity
- guidance
- role / stage / task 关联

### `ResourceBundle`

归属组件：

- `loader`

角色：

- loader 聚合出的运行资源集合对象

承担语义：

- prompts
- skills
- extensions
- `AGENTS.md`
- 其他 coding 侧资源

### `ExtensionDescriptor`

归属组件：

- `extensions`

角色：

- 扩展描述对象

承担语义：

- extension identity
- load target
- hook capabilities

## Reference Implementation Alignment

- `ResourceBundle`、`SkillDescriptor`、`MethodDescriptor`、`ExtensionDescriptor` 当前不直接复用 `reference CLI` 的统一导出对象名

## Notes

- 这组对象主要服务于 loader / skill / method / extensions 之间的资源交换
