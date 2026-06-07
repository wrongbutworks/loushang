"""Kimi 模型发现与句柄获取示例。

这个示例只展示根包公开的查询入口：
- `get_providers()`
- `list_models(...)`
- `get_model(...)`
"""

from __future__ import annotations

from loushang.ai import get_model, get_providers, list_models

PROVIDER_ID = "moonshot"
ENDPOINT_ID = "openai-completions"
MODEL_ID = "kimi-k2.5"


def main() -> None:
    providers = get_providers()
    moonshot_models = list_models(provider=PROVIDER_ID, endpoint=ENDPOINT_ID)
    model = get_model(PROVIDER_ID, ENDPOINT_ID, MODEL_ID)

    print(f"PROVIDERS {providers!r}")
    print(f"MODELS {PROVIDER_ID}:{ENDPOINT_ID} count={len(moonshot_models)}")
    print(f"MODEL {model.provider_id}:{model.endpoint_id}:{model.id}")
    print(f"MODEL api={ENDPOINT_ID!r} reasoning={model.reasoning!r}")


if __name__ == "__main__":
    main()
