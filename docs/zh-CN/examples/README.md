# 示例

[English](../../en/examples/) | 中文

仓库中主要有两组示例。

## Coding 示例

[examples/coding](../../../examples/coding/) 包含可运行的 `loushang-coding` 示例和统一运行器。

从这里开始：

```bash
cd examples/coding
python run.py list
python run.py run legacy-001
```

首次从仓库根目录初始化示例环境：

```bash
python examples/coding/init_examples_env.py --copy-model-catalog
```

## 扩展示例

[examples/coding/extensions](../../../examples/coding/extensions/) 展示 extension lifecycle hooks、动态资源、自定义工具、tool guard 和在线扩展场景。

## AI SDK 示例

[examples/ai](../../../examples/ai/) 展示 `loushang.ai` 的模型查询、完整返回、流式输出、工具调用和显式类型上下文。
