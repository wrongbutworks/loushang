# loushang.ai working agreement

- This package is a lower-level AI SDK, not an agent orchestrator.
- Do not import loushang.agent or loushang.coding from loushang.ai.
- Normalize input once before provider adapters.
- Provider adapters emit RawPart and must not expose vendor SDK objects.
- Core behavior must not branch on provider id or base URL.
- Built-in catalog facts live in `model/models.json`; user model files do not need evidence docs.
- Unknown capability is not supported capability.
- Every behavior change includes tests; user-visible changes include examples/docs.
- Run make check-ai before every commit.
- One plan item per commit; do not mix unrelated cleanup.
