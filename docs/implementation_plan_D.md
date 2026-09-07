# Phase D — Translation Quality and Review Workflow

Give reviewers the ability to spot bad segments at a glance and fix individual ones without rerunning the whole pipeline.

## What the backend already supports

Both per-segment actions have live endpoints:
- **Retranslate segment** → `POST /translation/translate-segment` (requires `segment_id`, `source_text`, `original_duration_ms`, `source_language`, `target_language`)
- **Regenerate audio** → `POST /tts/synthesize-segment` (requires `translation_id`)

No backend changes are needed for Phase D.

---

## Proposed Changes

### Component: Editor — `frontend/app/editor/[projectId]/page.tsx`

#### Risk indicators on every segment row
Each row will get a coloured risk badge based on data already in the `TranslatedSegment` object:

| Condition | Badge | Colour |
|---|---|---|
| `durationRatio > 1.15` | Slow — translation is too long | Red |
| `durationRatio < 0.75` | Fast — translation is too short | Amber |
| `confidence < 0.5` | Low confidence | Amber |
| `trans` is `undefined` | Missing translation | Red |

#### Segment-level action menu (three-dot ⋯ button per row)
- **Retranslate** — calls `POST /translation/translate-segment`, replaces `translatedText` in the store, marks row dirty
- **Regenerate audio** — calls `POST /tts/synthesize-segment`, shows inline "Synthesizing…" spinner
- **Reset to original** — replaces `translatedText` with the last persisted backend value (no API call needed, uses `translations` snapshot from initial load)

#### Autosave status line in the header
A small `"Autosave · last saved HH:MM"` or `"Unsaved changes"` indicator placed next to the Save button, so users always know whether edits are safe — directly addressing the plan requirement.

#### New service methods in `frontend/services/projectService.ts`
- `retranslateSegment(segmentId, sourceText, durationMs, sourceLang, targetLang, prevCtx?, nextCtx?)` → calls `/translation/translate-segment`
- `synthesizeSegment(translationId)` → calls `/tts/synthesize-segment`

---

## Open Questions

> [!IMPORTANT]
> **Regenerate audio scope**: When a user clicks "Regenerate audio," it only re-synthesises TTS for that one segment — it does **not** rebuild the full dubbed video. The full dub still requires clicking "Dub only" or "Dub + Lip-Sync". Is that the right expectation to set in the UI?

> [!NOTE]
> **Reset translation**: "Reset to original" will revert to whatever was loaded from the backend when the editor opened. It does **not** call any API to fetch the backend's current version. Should it instead fetch the latest persisted translation from the backend before resetting?

---

## Verification Plan

### Manual QA
1. Open a project with translated segments. Verify risk badges appear correctly for long/short/missing translations.
2. Click **Retranslate** on a segment — verify the translation text updates and the row is marked dirty.
3. Click **Regenerate audio** — verify an inline spinner appears and disappears without breaking other rows.
4. Click **Reset to original** — verify the text reverts cleanly.
5. Make an edit and wait for autosave — verify the header shows "Saved · HH:MM".
