# Ontology Wave 2A Facts And Provenance

## Status

Accepted implementation boundary for Wave 2A. This wave introduces the
append-only semantic Fact/Provenance authority, deterministic bitemporal
selection, and Fact-to-Object/Property/Link projection. It adopts SQLite
physical format version 2 directly.

Wave 2A does not retain a SQLite v1 reader or migration path. Version 1 was a
development-only Wave 1 format with no external compatibility commitment. A v1
database is rejected explicitly and must be recreated.

## Runtime Spine

```text
Source / future Adapter
          |
          | immutable FactBatch
          v
   +-------------------+
   | Semantic FactStore|  append-only authority + provenance
   +-------------------+
          |
          | select(valid_at, recorded_at)
          v
   +-------------------+
   | Fact Projector    |  schema validation + strict conflict detection
   +-------------------+
          |
          v
 Object / Property / Link projection
          |
          v
 QueryRequest -> QueryResult
```

`StoreMutation` remains the operational commit/recovery journal. It is not a
Fact and does not acquire source, evidence, confidence, or bitemporal meaning.
The existing direct object-mutation API remains a compatibility path; callers
must not represent those mutations as source-backed facts unless they actually
commit a `FactRecord`.

## Fact Envelope

Every immutable `FactRecord` contains:

- a stable `fact_id` and one typed assertion payload;
- `assertion_kind`: `asserted`, `derived`, or `inferred`;
- non-empty `source_ref` and `source_record_ref`;
- optional ordered `evidence_refs`, `methodology_ref`, `author_ref`, and
  `agent_ref`;
- optional finite confidence in the closed interval `[0, 1]`;
- business validity `[valid_from, valid_to)`;
- immutable system `recorded_at`;
- at most one lineage edge: `supersedes` or `corrects`.

The three infrastructure assertion payloads are deliberately small:

| Assertion | Meaning |
| --- | --- |
| `ObjectAssertion(object_type)` | the subject exists as one schema object type |
| `PropertyAssertion(property_name, value)` | one strict Foundation JSON value is asserted for a subject property |
| `LinkAssertion(link_type, target_id, properties)` | one typed edge exists from subject to target |

Measurement and Claim are domain object types built with these facts, not new
hard-coded infrastructure enums. Property `null` is a real JSON value and is
not confused with an absent assertion payload.

Facts are immutable after commit. A correction or newer observation appends a
new fact; it never updates or deletes the earlier record.
Retraction uses the same append-only mechanism: a correcting successor repeats
the assertion with a closed `valid_to`; after that boundary neither the retired
predecessor nor the expired successor appears in the current valid-time view.

## Bitemporal And Lineage Semantics

Selection always names both axes:

- `valid_at` answers what was true in the business world at that time;
- `recorded_at` answers what the system knew by that time.

A fact is selectable when it was recorded no later than `recorded_at` and its
half-open valid interval contains `valid_at`. A visible successor linked by
`supersedes` or `corrects` retires its referenced fact from the selected view.
Historical reads before the successor's `recorded_at` still expose the older
fact.

Lineage edges must point to a previously committed fact or an earlier fact in
the same batch. The predecessor must have the same subject, assertion category,
assertion kind, predicate, source, and source-record identity. The successor
cannot have an
earlier `recorded_at`. These rules make lineage acyclic and prevent one source
from silently overwriting another source's assertion.

Facts from different sources may coexist. Wave 2A has no merge-policy or source
priority framework. When coexisting current facts imply different object
types or property values, projection fails with explicit diagnostics instead
of choosing a winner. Equivalent assertions are safely coalesced.

## Batch And Idempotency Contract

`FactBatch` is the atomic ingestion unit and has a stable non-empty `batch_id`.
All fact IDs within a batch are unique.

- the first successful commit appends each fact with one contiguous fact
  sequence and advances the fact watermark;
- replaying the same batch ID with byte-equivalent canonical content returns
  the original commit range with `replayed=True` and appends nothing;
- reusing a batch ID with different content raises
  `FactBatchConflictError`;
- duplicate fact IDs, invalid lineage, invalid envelopes, or persistence
  failures append nothing and do not advance the watermark.

Batch idempotency is infrastructure replay protection. `source_record_ref`
remains the semantic source identity used by future adapters and fusion.

## Projection Contract

Projection consumes one compiled schema and a fact selection at explicit
`valid_at` and `recorded_at` values. It performs these deterministic steps:

1. resolve current facts through recorded-time lineage;
2. require exactly one compatible object type per subject;
3. coalesce equal property/link assertions and reject conflicting properties;
4. materialize objects with their complete current property sets;
5. materialize links after all endpoints exist;
6. run the normal schema, unique, type, cardinality, required-field, endpoint,
   and reference-integrity checks.

The result carries the selected fact IDs, source fact watermark, schema
version, and the two projection times. Repeating projection with the same
schema, fact sequence, and times produces an equivalent object/link graph.

Projection does not mutate the FactStore and does not append semantic or
operational records. It is safe to rebuild after restart or from an online
backup.

## SQLite Physical Format V2

The current physical identity is `loushang.ontology.sqlite`, version `2`.
Version 2 adds append-only semantic fact records, committed batch identities,
and a fact watermark to the existing schema, object authority, operational
journal, and serving projection tables.

`SQLiteObjectStore` also implements the FactStore port. A fact batch commit is
validated before one SQLite transaction persists the fact rows, batch replay
identity, and fact watermark. In-memory state changes only after that
transaction succeeds. Reopen and online backup restore the same fact sequence,
batch replay behavior, and projection inputs.

The loader accepts exactly v2. It rejects v1, future versions, incomplete v2
tables, malformed facts, and inconsistent fact watermarks. There is no silent
DDL repair, implicit migration, or compatibility facade for v1.

## Public Surface

Wave 2A publishes the following concepts from `loushang.ontology.facts`:

- `AssertionKind`, `ObjectAssertion`, `PropertyAssertion`, `LinkAssertion`;
- `FactRecord`, `FactBatch`, `StoredFact`, `FactCommit`;
- `FactReadStore`, `FactStore`, and `MemoryFactStore`;
- `FactProjection` and `project_facts`;
- stable fact validation, batch-conflict, and projection failures.

`AssertionKind`, the assertion payloads, `FactRecord`, `FactBatch`,
`StoredFact`, `FactCommit`, `FactProjection`, and `project_facts` are also
available from `loushang.ontology`. Concrete Memory and SQLite store selection
stays in the facts/storage packages.

The SQLite implementation remains under `loushang.ontology.storage` because
backend selection is an application composition concern.

## Acceptance Gates

- one FactStore conformance suite passes for Memory and SQLite;
- asserted, derived, and inferred records remain distinguishable after commit,
  restart, and backup;
- duplicate batch replay is idempotent and conflicting replay is rejected;
- correction/supersession preserves historical recorded-time reads;
- valid-time boundaries use `[from, to)` consistently;
- invalid lineage and failed SQLite transactions leave facts and watermark
  unchanged;
- fact projection is deterministic, schema-valid, and rebuildable for objects,
  properties, links, uniqueness, and cardinality;
- SQLite v2 rejects a database marked v1 without altering it;
- the operational journal and semantic Fact APIs remain visibly separate;
- Foundation-only and optional HarnessWork integration import boundaries remain
  intact.

## Non-Goals

- v1 migration, repair, or dual-format readers;
- source/API/database adapters, cursors, mappings, or entity resolution;
- JSON-LD, RDF, OWL, SHACL, or safe-expression standards work;
- source-priority and merge-policy resolution;
- Actions, Decisions, authorization, approval, or external write-back;
- SQL query pushdown, generated SDKs, domain packages, or distributed serving.
