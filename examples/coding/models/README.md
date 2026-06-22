# Example Model Catalogs

放这里的文件会被 `examples/coding/run.py` 当作 `models` 目录 catalog 自动加载（按 `*.json` 合并）。

建议命名：
- `models.local.json`
- `models.work.json`
- `models.xx.json`

内容保持与 `src/loushang/ai/model/models.curated.v2.json` 兼容（`providers -> endpoints -> models`）。

示例（最小骨架）：

```json
{
  "providers": {}
}
```

你可以把实际模型内容拷贝或拼接到这里，运行时会：
1) 优先查找 `examples/coding/.loushang/models`（当 `LOUSHANG_EXAMPLES_MODEL_CATALOG` 未设置时）；
2) 否则查找 `<artifacts-root>/models.json`；
3) 最后回退到内置 `src/loushang/ai/model/models.curated.v2.json`。

仓库内提供了一个开箱即用的 Kimi Code 模板：

- `models.kimi-code.json`

它包含：
- `moonshot` + `anthropic-messages`（`anthropic-messages` endpoint 映射）
- `moonshot` + `kimi-code-openai`（`api.kimi.com/coding/v1` endpoint 映射）
- `kimi-for-coding`（按 Kimi Code 官方模型名，默认用于 `api.kimi.com/coding/` 与 `api.kimi.com/coding/v1`）
- `kimi-code` 语义兼容别名（仍走同一端点）

这样你可以在显式覆盖 catalog 时，用更“语义化”的模型名调用：

```bash
python examples/coding/run.py --model-catalog examples/coding/models run legacy-001
```

若你希望一键初始化后就带上这个 catalog，请用：

```bash
python examples/coding/init_examples_env.py --copy-model-catalog
```

推荐用法（含模板）：

```bash
cd /home/dev/workspace/loushang
python examples/coding/init_examples_env.py --copy-model-catalog
python examples/coding/run.py --model-catalog examples/coding/.loushang/models run legacy-001
```

你也可以放置多个 `models.*.json`，`run.py` 会按文件名排序后按顺序读取并 `update`，后处理文件可覆盖同名 provider/endpoint 的配置。
