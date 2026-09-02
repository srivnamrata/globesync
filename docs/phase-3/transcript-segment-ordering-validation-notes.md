# GlobeSync Phase 3 Transcript Segment Ordering Validation Notes

This note defines the validation work required before tightening transcript ordering from a non-unique composite index to a uniqueness constraint on `(transcript_id, sequence_order)`.

## Purpose

* verify whether any legacy transcript rows already violate the intended segment ordering rule
* document how to classify duplicates before adding a uniqueness constraint
* keep Phase 3 migration tightening safe on GCP production data

## Current baseline

The current Phase 3 schema groundwork now includes:

* a non-unique composite index on `transcript_segments(transcript_id, sequence_order)` in [20260901_08_add_transcript_segment_ordering_index.py](#file-4393033632292541)
* `Transcript.segments` already read in `sequence_order` order in [transcript.py](#file-3239543912548904)
* transcript rebuilds in [transcription_tasks.py](#file-3239543912548955) currently delete then recreate all segment rows for a transcript, assigning `sequence_order=idx`

That means the application intent is already one ordered position per segment within each transcript, but the database does not enforce it yet.

## Write-path coverage status

The current repo now shows ordered-write intent on the primary segment-producing paths:

* [transcription_tasks.py](#file-3239543912548955) recreates transcript segments with zero-based `sequence_order`
* the new correlation and provenance columns are present in [20260901_07_add_workflow_correlation_foundation.py](#file-493542987818579) and the matching SQLAlchemy models
* transcription dispatch and internal handlers now thread request, task, idempotency, and provenance context, and Cloud Tasks-backed translation and lip-sync handlers now preserve the Cloud Tasks task name as correlation context

This lowers the risk of adding tighter transcript ordering later because both the schema groundwork and the first round of task-level correlation wiring are now in place, even though full cross-path validation is still pending.

## Validation questions

Before adding uniqueness, confirm all of the following:

* whether any existing transcript has multiple rows with the same `sequence_order`
* whether duplicate rows represent true historical corruption, partial retry artifacts, or intentionally retained alternates
* whether any rows have null or negative ordering values
* whether downstream reads or exports ever depend on duplicate order values being tolerated

## Validation query set

Run these checks before authoring the tightening revision:

### 1. Duplicate order detection

```sql
SELECT
  transcript_id,
  sequence_order,
  COUNT(*) AS row_count
FROM transcript_segments
GROUP BY transcript_id, sequence_order
HAVING COUNT(*) > 1
ORDER BY row_count DESC, transcript_id, sequence_order;
```

### 2. Null order detection

```sql
SELECT COUNT(*) AS null_order_rows
FROM transcript_segments
WHERE sequence_order IS NULL;
```

### 3. Negative order detection

```sql
SELECT COUNT(*) AS negative_order_rows
FROM transcript_segments
WHERE sequence_order < 0;
```

### 4. Transcript-level density check

This identifies transcripts where the ordering sequence may have gaps or unexpected resets.

```sql
WITH ordered AS (
  SELECT
    transcript_id,
    sequence_order,
    ROW_NUMBER() OVER (
      PARTITION BY transcript_id
      ORDER BY sequence_order, created_at, id
    ) - 1 AS expected_zero_based_order
  FROM transcript_segments
)
SELECT *
FROM ordered
WHERE sequence_order <> expected_zero_based_order
ORDER BY transcript_id, sequence_order;
```

### 5. Duplicate key drill-down

Run this only if query 1 returns rows. It captures the specific segment rows that would need classification before cleanup.

```sql
WITH duplicate_keys AS (
  SELECT transcript_id, sequence_order
  FROM transcript_segments
  GROUP BY transcript_id, sequence_order
  HAVING COUNT(*) > 1
)
SELECT
  ts.id,
  ts.transcript_id,
  ts.sequence_order,
  ts.speaker_tag,
  ts.start_time_seconds,
  ts.end_time_seconds,
  ts.created_at,
  ts.origin_type,
  ts.source_action
FROM transcript_segments ts
INNER JOIN duplicate_keys dk
  ON ts.transcript_id = dk.transcript_id
 AND ts.sequence_order = dk.sequence_order
ORDER BY ts.transcript_id, ts.sequence_order, ts.created_at, ts.id;
```

### 6. Affected transcript summary

Use this summary to separate isolated retry artifacts from broader transcript-level corruption patterns.

```sql
WITH duplicate_keys AS (
  SELECT transcript_id, sequence_order
  FROM transcript_segments
  GROUP BY transcript_id, sequence_order
  HAVING COUNT(*) > 1
)
SELECT
  ts.transcript_id,
  COUNT(*) AS affected_segment_rows,
  COUNT(DISTINCT ts.sequence_order) AS affected_positions,
  MIN(ts.sequence_order) AS min_sequence_order,
  MAX(ts.sequence_order) AS max_sequence_order,
  MIN(ts.created_at) AS earliest_created_at,
  MAX(ts.created_at) AS latest_created_at
FROM transcript_segments ts
INNER JOIN duplicate_keys dk
  ON ts.transcript_id = dk.transcript_id
 AND ts.sequence_order = dk.sequence_order
GROUP BY ts.transcript_id
ORDER BY affected_segment_rows DESC, ts.transcript_id;
```

## Triage rules for duplicates

If duplicate `(transcript_id, sequence_order)` rows exist, classify them before cleanup:

* if one row is clearly newer but the transcript was meant to be fully rebuilt, prefer keeping the transcript set created by the latest successful transcription run
* if duplicates differ only because of a retry artifact, keep one canonical row and document the cleanup rule in the migration notes
* if duplicates expose a deeper bug in transcript creation, fix the write path before adding the uniqueness constraint
* never auto-delete ambiguous duplicates without recording the transcript IDs affected

## Expected cleanup approach

Preferred Phase 3 cleanup order:

1. capture the affected `transcript_id` values and duplicate counts
2. decide a deterministic retention rule for each duplicate class
3. clean duplicates in a data-fix step or pre-tightening migration
4. rerun the validation queries and record zero remaining duplicate keys
5. only then add a unique constraint or unique index on `(transcript_id, sequence_order)`

## Evidence to record

Before closing the ordering-validation task, record:

* the exact validation query outputs
* the number of affected transcripts, if any
* the chosen cleanup rule for each duplicate pattern
* confirmation that rerun validation returned zero duplicate keys
* the follow-up Alembic revision ID that tightens ordering uniqueness

## Evidence log template

Append validation evidence in this format once real data checks are run:

* environment: GCP production or named validation environment
* migration baseline: [20260901_07_add_workflow_correlation_foundation.py](#file-493542987818579) and [20260901_08_add_transcript_segment_ordering_index.py](#file-4393033632292541) applied
* query run date:
* operator:
* duplicate-key result summary:
* null-order result summary:
* negative-order result summary:
* density-check result summary:
* affected transcript IDs or count:
* chosen cleanup rule:
* follow-up migration or data-fix reference:
* rerun validation status:

## Recorded validation evidence

The following baseline validation results were captured from the first transcript ordering checks:

* environment: GCP production
* migration baseline: [20260901_07_add_workflow_correlation_foundation.py](#file-493542987818579) and [20260901_08_add_transcript_segment_ordering_index.py](#file-4393033632292541) applied for this validation run
* query run date: 2026-09-01
* operator: Namrata
* duplicate-key result summary: 0 duplicate `(transcript_id, sequence_order)` keys returned by query 1
* null-order result summary: 0 rows with `sequence_order IS NULL`
* negative-order result summary: 0 rows with `sequence_order < 0`
* density-check result summary: 0 transcripts flagged by the zero-based ordering density check
* affected transcript IDs or count: none
* chosen cleanup rule: no cleanup needed based on the current baseline validation results
* follow-up migration or data-fix reference: proceed to uniqueness-tightening preparation after environment metadata is recorded
* rerun validation status: baseline passed; rerun after task and route wiring lands

Because query 1 returned no rows, the duplicate drill-down and affected-transcript summary queries were not needed for this run.

## Results entry template

Copy this block into the evidence log and replace the placeholder values with actual outputs from the validation run.

* environment: <GCP production or validation environment>
* migration baseline: [20260901_07_add_workflow_correlation_foundation.py](#file-493542987818579) and [20260901_08_add_transcript_segment_ordering_index.py](#file-4393033632292541) applied
* query run date: <YYYY-MM-DD>
* operator: <name>
* duplicate-key result summary: <for example, 0 duplicate keys or 3 duplicate keys across 2 transcripts>
* null-order result summary: <for example, 0 rows with `sequence_order IS NULL`>
* negative-order result summary: <for example, 0 rows with `sequence_order < 0`>
* density-check result summary: <for example, 0 transcripts flagged or 2 transcripts flagged for review>
* affected transcript IDs or count: <none, count only, or specific transcript IDs>
* chosen cleanup rule: <retry artifact, full-transcript rebuild leftover, ambiguous duplicate manual review, or no cleanup needed>
* follow-up migration or data-fix reference: <revision ID, script name, or pending>
* rerun validation status: <pending, passed, or blocked>

### Example formatted result

Use this only as formatting guidance, not as actual evidence.

* environment: GCP production
* migration baseline: [20260901_07_add_workflow_correlation_foundation.py](#file-493542987818579) and [20260901_08_add_transcript_segment_ordering_index.py](#file-4393033632292541) applied
* query run date: 2026-09-01
* operator: Namrata
* duplicate-key result summary: 3 duplicate keys across 2 transcripts
* null-order result summary: 0 rows with `sequence_order IS NULL`
* negative-order result summary: 0 rows with `sequence_order < 0`
* density-check result summary: 2 transcripts flagged for order mismatch review
* affected transcript IDs or count: 2 transcripts affected; `11111111-1111-1111-1111-111111111111`, `22222222-2222-2222-2222-222222222222`
* chosen cleanup rule: treat rows as full-transcript rebuild leftovers and retain only the latest coherent transcript segment set by `created_at`, with manual review if the latest set is incomplete
* follow-up migration or data-fix reference: pending Phase 3 pre-tightening cleanup migration
* rerun validation status: pending until cleanup step is applied

## Draft cleanup rule wording

Use or adapt the following wording in the eventual cleanup migration notes or rollout evidence.

### Retry artifact cleanup rule

For duplicate `(transcript_id, sequence_order)` rows that are otherwise materially identical, retain one canonical row and remove the later retry artifact rows. Prefer the earliest committed row by `created_at`, using `id` only as a deterministic tie-breaker when timestamps are equal.

### Full-transcript rebuild leftover cleanup rule

When duplicate ordering keys indicate that a transcript was fully rebuilt more than once, retain the single most recent coherent transcript segment set for the affected `transcript_id` and remove older leftover rows from prior rebuild attempts. A coherent set means the retained rows form the expected zero-based sequence for that transcript without gaps at the time of cleanup.

### Ambiguous duplicate handling rule

If duplicate `(transcript_id, sequence_order)` rows differ materially in timing, text, speaker attribution, or surrounding transcript completeness such that the canonical row cannot be chosen safely by deterministic metadata alone, do not auto-delete them in the tightening migration. Record the affected `transcript_id` values, review them manually, and defer uniqueness tightening until the write-path or data issue is resolved.

## Draft pre-tightening migration notes

Use the following points when authoring the migration that cleans duplicate ordering data before any uniqueness enforcement.

### Scope

* operate only on `transcript_segments` rows that violate the intended `(transcript_id, sequence_order)` uniqueness rule
* do not change unaffected transcripts
* do not add the unique constraint in the same revision unless rerun validation is already proven clean in the target environment

### Required inputs before authoring

* recorded outputs from validation queries 1 through 6 in this document
* a documented retention rule for each duplicate class found in production or the target deploy environment
* confirmation that the current transcription write path still assigns deterministic zero-based ordering

### Migration behavior expectations

* log which duplicate class each cleanup rule addresses
* apply a deterministic retention rule so reruns are stable
* preserve the most recent coherent transcript segment set when duplicates come from full rebuild leftovers
* avoid deleting ambiguous rows automatically; instead fail closed by deferring tightening until manual cleanup is complete

### Post-cleanup validation notes

* rerun duplicate, null, negative, and density checks after cleanup
* record zero remaining duplicate `(transcript_id, sequence_order)` keys before the tightening revision is authored
* reference both the cleanup revision ID and the later uniqueness-tightening revision ID in the rollout checklist

## Notes started

Initial notes are now in place, and baseline validation evidence has started:

* the first four validation queries now show no duplicate ordering keys, no null ordering values, no negative ordering values, and no density mismatches
* duplicate drill-down and affected-transcript summary queries were not required for the baseline run because query 1 returned no rows
* rollout metadata is now filled in for the baseline run, so this can serve as formal early validation evidence
* if later runs remain clean after route and task updates, the next step can move from validation notes to uniqueness-tightening preparation

## Phase 3 handoff note

This note should stay paired with [additive-schema-plan.md](#file-4107232751829827) and [phase-3-rollout-checklist.md](#file-4107232751829830) until transcript ordering is fully tightened.
