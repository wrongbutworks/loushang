# Legacy AI model catalog archive

This directory stores the deterministic archive of the pre-curation built-in
`loushang.ai` model catalog for the AIQ quality hardening branch.

- Plan ID: `AIQ-004`
- Source commit: `80a547f13598282cbb9c352fdd93ab6fe5f21ed8`
- Original path: `src/loushang/ai/model/models.json`
- Archive file: `models-v1-full.json.gz`
- SHA-256 file: `models-v1-full.sha256`
- Original SHA-256:
  `6b41c14692b696647c0d32b6aab1b4fcf3c681515fcb0d7039b94c6b8e8632b5`

## Verify

```bash
expected="$(awk '{print $1}' docs/internals/archive/ai/model-catalog/models-v1-full.sha256)"
actual="$(
  gzip -dc docs/internals/archive/ai/model-catalog/models-v1-full.json.gz \
    | sha256sum \
    | awk '{print $1}'
)"
test "$actual" = "$expected"
```

The sidecar uses `models-v1-full.json` as the stable original filename. The
verification command compares hash fields so it does not depend on any restored
temporary file path.

## Restore For Inspection

```bash
gzip -dc docs/internals/archive/ai/model-catalog/models-v1-full.json.gz \
  > /tmp/loushang-models-v1-full.json
```

Do not restore this file into the Python package data as part of the curated
catalog migration. It is an internal audit archive only.

## Why This Exists

The hardening plan intentionally shrinks the built-in catalog to a small,
evidence-backed set of providers and models. The previous catalog contained a
large model index, legacy `compat` metadata, non-core providers, duplicated
endpoints, and facts that will be reclassified or omitted during the v2 catalog
migration.

Keeping this compressed archive preserves the prior data for audit and manual
recovery without keeping the full legacy catalog on the runtime package path.

## Custom Catalog Recovery

Long-tail providers and models removed from the built-in catalog should be
restored through custom catalog loading rather than by expanding the curated
built-in catalog. Use the decompressed JSON as source material, copy only the
provider/model entries needed by the local deployment, and keep any unsupported
or unverified facts omitted or explicitly unknown in the new catalog format.
