# Legacy AI model catalog backup

This directory stores the deterministic offline backup of the pre-curation
built-in `loushang.ai` model catalog.

- Plan ID: `AIQ-004`
- Source commit: `80a547f13598282cbb9c352fdd93ab6fe5f21ed8`
- Original path: `src/loushang/ai/model/models.json`
- Archive file: `models-legacy-full.json.gz`
- SHA-256 file: `models-legacy-full.sha256`
- Original SHA-256:
  `6b41c14692b696647c0d32b6aab1b4fcf3c681515fcb0d7039b94c6b8e8632b5`

## Verify

```bash
expected="$(awk '{print $1}' backup/ai/models-legacy-full.sha256)"
actual="$(
  gzip -dc backup/ai/models-legacy-full.json.gz \
    | sha256sum \
    | awk '{print $1}'
)"
test "$actual" = "$expected"
```

The sidecar uses `models-legacy-full.json` as the stable restored filename. The
verification command compares hash fields so it does not depend on any restored
temporary file path.

## Restore For Inspection

```bash
gzip -dc backup/ai/models-legacy-full.json.gz \
  > /tmp/loushang-models-legacy-full.json
```

Do not restore this file into the Python package data. It is an offline backup
only and is not part of runtime model loading, package data, or catalog
validation.

## Why This Exists

The hardening plan intentionally shrank the built-in catalog before the core
freeze work. The previous catalog contained a large model index, legacy `compat`
metadata, non-core providers, duplicated endpoints, and facts that were
reclassified or omitted during catalog curation.

Keeping this compressed archive preserves the prior data for audit and manual
recovery without keeping the full legacy catalog on the runtime package path.

## Custom Catalog Recovery

Long-tail providers and models removed from the built-in catalog should be
restored through custom catalog loading rather than by expanding the curated
built-in catalog. Use the decompressed JSON as source material, copy only the
provider/model entries needed by the local deployment, and keep any unsupported
or unverified facts omitted or explicitly unknown in the new catalog format.
