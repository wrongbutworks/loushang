# Diagnostics Export Boundary

`loushang.harness.diagnostics.export` owns the reusable diagnostics archive
mechanism. It writes a deterministic set of archive members, protects archive
member names, and redacts both text artifacts and JSON values before writing.

The archive mechanism does not decide a product's storage root, file name,
package identity, README wording, JSON field convention, or which session and
trace files are useful. Those are supplied by a product adapter.

## Harness Contract

The Harness export API accepts:

- an explicit output path;
- a product-projected manifest and diagnostic JSON values;
- optional named text artifacts;
- optional clock and redaction functions for tests or stricter deployments.

It always rejects absolute paths and parent traversal in archive member names.
Default redaction applies recursively to structured values whose keys identify
credentials and to common bearer-token text forms. Products may add stricter
redaction, but cannot opt out of the default redactor accidentally.

The writer owns no diagnostics service lookup and no product serialization. A
failed product serializer must be handled by the product before invoking the
writer; it must not fall back to an unrestricted `repr()` in the archive.

## Coding Adapter

`loushang.coding.diag_export` remains a product adapter. It supplies the
`.loushang/diagnostics` output default, `loushang-diag-*` name, Coding README,
camelCase manifest, latest debug/trace/session artifacts, and Coding diagnostic
serialization. Its only responsibility is projection and product defaults; it
does not create a ZIP file or implement redaction.

This preserves the current Coding archive schema while making the export engine
available to Research, Design, PPT, OEM products, and extension-provided
diagnostic artifacts.
