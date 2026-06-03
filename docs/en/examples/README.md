# Examples

English | [中文](../../zh-CN/examples/)

The repository contains two main example groups.

## Coding Examples

[examples/coding](../../../examples/coding/) contains runnable `loushang-coding` examples and a unified runner.

Start with:

```bash
cd examples/coding
python run.py list
python run.py run legacy-001
```

For first-time setup from the repository root:

```bash
python examples/coding/init_examples_env.py --copy-model-catalog
```

## Extension Examples

[examples/coding/extensions](../../../examples/coding/extensions/) demonstrates extension lifecycle hooks, dynamic resources, custom tools, tool guards, and online extension scenarios.

## AI SDK Examples

[examples/ai](../../../examples/ai/) demonstrates model lookup, complete, stream, tools, and typed contexts for `loushang.ai`.
