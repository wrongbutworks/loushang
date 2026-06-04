# `skill`

## Role

- coding skill 发现、解析与注入边界

## Owns

- `SkillLoader`
- skill 元数据解析
- skill prompt 片段收集
- skill 可见性与启用策略

## Depends On

- `loader`
- `utils`

## Commands

- `discover_skills(...)`
- `load_skill(...)`
- `reload_skills(...)`
- `enable_skill(...)`
- `disable_skill(...)`

## Queries

- `get_skill(...)`
- `list_skills()`
- `list_enabled_skills()`

## Events

- 当前无稳定事件面

## Key Data

- `SkillDescriptor`
- `ResourceBundle`
- `SKILL.md` frontmatter:
  - `name`
  - `description`
  - `disable-model-invocation`

## Out Of Scope

- method 选择策略
- extension hook 执行
- prompt 最终组装

## Reference Implementation Alignment

- 语义上吸收 `reference CLI` 的 customization / resource discovery 经验
- 在 Python 设计里显式保留 `SkillLoader`，让 skill 解析边界更清楚
- 但它更适合作为 resource loader 体系内的显式子边界，而不是另一套并列资源中心
- `description` 用于 `/skill:name` command 描述与 system prompt 中的 available skills 摘要。
- `disable-model-invocation: true` 让 skill 仍可显式 `/skill:name` 调用，但不会进入模型可自动发现的 skill 摘要。
- skill discovery 递归扫描 `skills/**/SKILL.md`；一旦某目录本身包含 `SKILL.md`，该目录即为 skill root，不再继续向下递归。
- discovery 跳过隐藏目录和 `node_modules`，并读取 `.gitignore` / `.ignore` / `.fdignore` 中的常用目录/路径/glob 忽略规则，避免把依赖、隐藏工作区或生成目录误注册为可用 skill。
