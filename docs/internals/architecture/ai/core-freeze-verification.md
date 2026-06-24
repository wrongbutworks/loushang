# Core Freeze Verification

Date: 2026-06-24

Branch: `ai/core-freeze-v1`

Base: `7f5810a263cdb58960dfed3998d9a0aefaeb4574`

Verification scope: `ai/core-freeze-v1` after AIF-017 review-fix changes.

## Result

The `loushang.ai` core-freeze validation passed locally.

No live-provider calls were run. No GitHub Actions result is claimed here.

## Validation Commands

| Command | Result |
| --- | --- |
| `git diff --check` | Passed |
| `make check-ai` | Passed |
| `uv run pytest tests -q` | Passed: 4190 passed, 6 skipped |
| `uv build` | Passed: built `dist/loushang-0.1.0.tar.gz` and `dist/loushang-0.1.0-py3-none-any.whl` |

`make check-ai` details:

- Ruff passed for AI source and tests.
- Mypy passed for 76 source files.
- Catalog check passed: 11 providers, 11 endpoints, 17 models.
- Import-boundary check passed.
- Offline examples passed: 13 examples.
- Offline AI/provider tests passed: 585 passed, 9 deselected.
- Total AI coverage: 83.68%.
- Coverage targets passed:
  - `ai-runtime-core`: 90.59% (minimum 90.00%)
  - `provider-adapters`: 88.36% (minimum 85.00%)
  - `production-adapter-modules`: 88.64% (minimum 85.00%)

## Removed-Surface Scan

Command:

```bash
rg -n "Compat|SupportStatus|EndpointProtocol|EndpointWireDialect|ResolvedRequest|ResolvedEndpoint|SimpleCallOptions|complete_simple|stream_simple|schemaVersion" src/loushang/ai tests/ai tests/providers
```

Result: no production-code hits under `src/loushang/ai`.

Remaining hits are test assertions that the removed names are not public API or
that old model-file fields are rejected:

- `tests/ai/contracts/test_core_provider_contracts.py`
- `tests/ai/test_core_freeze_contracts.py`
- `tests/ai/test_curated_catalog.py`
- `tests/ai/test_model_loader_schema.py`
- `tests/ai/test_options.py`
- `tests/ai/test_provider_contract_matrix.py`

The model loader still rejects the removed root schema field, but the production
source no longer contains the complete removed-field spelling as a scan hit.

## Review Index

Local review reports are stored under the ignored path
`.artifacts/ai-reviews/`. AIF-017 final full-branch review findings were
resolved, and the final report records the clean P0/P1 result plus the
subagent-auth limitation on the last retry.

| Scope | Local review report |
| --- | --- |
| AIF-001 | `.artifacts/ai-reviews/c077fbe7368db43d98b0e186e06333bc126d4073.md` |
| AIF-002 | `.artifacts/ai-reviews/7d51d88255ef91e23c3077088fcbb7cf6d897a4c.md` |
| AIF-002 follow-up | `.artifacts/ai-reviews/936374ab6cfb1f5f438439b0206ba5e370d60da6.md` |
| AIF-002 follow-up | `.artifacts/ai-reviews/78b374b44fda9b87d2c790a0baba6a6d72d9105d.md` |
| AIF-002 follow-up | `.artifacts/ai-reviews/b530ce1ab9c5fe3f0fff8ea949fea29e4922d6e6.md` |
| AIF-002 follow-up | `.artifacts/ai-reviews/6ee61b7fbcf93b42b446ed62232bbd83d9b2705f.md` |
| AIF-003 | `.artifacts/ai-reviews/8895f86baf8ea1a68ee516e6f94ee7f9f657ddd0.md` |
| AIF-003 follow-up | `.artifacts/ai-reviews/d6464e428fe0f25350b5ef284752af6c75a93707.md` |
| AIF-004 | `.artifacts/ai-reviews/7bf6d0bd0c6a0268b2e82f589760eb3c52519bef.md` |
| AIF-009 | `.artifacts/ai-reviews/cb26e850a5f357f07d5a072af7f66b8ae330aa37.md` |
| AIF-009 follow-up | `.artifacts/ai-reviews/62b4b5fab042c89e85dbc09a16cb4963ea0af053.md` |
| AIF-009 follow-up | `.artifacts/ai-reviews/1c675664c283e332e20036a26c8ecd1a8db2adb0.md` |
| AIF-009 follow-up | `.artifacts/ai-reviews/c98056343825e8c5fc77c8f02117c15a7161f9e7.md` |
| AIF-009 follow-up | `.artifacts/ai-reviews/bfabcaf66a19fa8318257128dfc4759bc1be031b.md` |
| AIF-009 follow-up | `.artifacts/ai-reviews/f34505237e8476ac799ed2feb18758fc07b4c601.md` |
| AIF-010 | `.artifacts/ai-reviews/81551521484c48cf4248f2ea98cd7c3fc79df0b3.md` |
| AIF-011 | `.artifacts/ai-reviews/9d8c331ae72ca3fd2cea14a159307da27c5e2df1.md` |
| AIF-012 | `.artifacts/ai-reviews/c4d2eb0e487b40a3b897b7205a7a78b363af09af.md` |
| AIF-013 | `.artifacts/ai-reviews/4597055fa3196ec3fbddc90763e90c7ba8d51aa1.md` |
| AIF-014 | `.artifacts/ai-reviews/5bbad29a40264886a5d51b225aa416a16d796f2c.md` |
| AIF-015 | `.artifacts/ai-reviews/1cb06ed7fea47dd55857edf5195181bb89ff0bdf.md` |
| AIF-016 | `.artifacts/ai-reviews/6b5f399a44f6390797fab176865d0f3adf17ff93.md` |
| AIF-017 | `.artifacts/ai-reviews/final-full-branch-2026-06-24.md` |

## Acceptance Notes

- Built-in runtime model file is `src/loushang/ai/model/models.json`.
- Historical model backup remains outside package data under `backup/ai`.
- Default registry loads built-in models plus user model files lazily.
- Explicit file and directory loaders are covered by tests.
- Built-in and user model files share the same parser and validation path.
- JSON-only add-model drill passed with request binding assertions.
- Main scenario examples run offline.
- Public docs and examples do not claim live-provider validation.
- GitHub Actions status is not claimed by this document.
