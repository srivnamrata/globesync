# Fix Editor Video Player and Preview Logic

This plan addresses the bugs reported during UI testing where the video player is missing, rendering the segment play/loop buttons and timeline seeking non-functional.

## The Problem
Currently, the `<video>` element in `page.tsx` is conditionally rendered **only** if `renderedVideoUrl` (the dubbed output) exists. 
Because the video element is unmounted before a dub is built:
1. `videoRef.current` is null, so clicking "Play" or "Loop" on a segment throws silently and does nothing.
2. Clicking the waveform seeks the timeline, but with no video mounted, you can't hear or see anything.
3. The preview area just shows "Preview Media Player Placeholder".
4. When a dub *is* built, you have no way to visually toggle back and watch the original video; the `comparisonMode` state is only wired up to an invisible `<audio>` element at the bottom of the page.

## Proposed Changes

### Modify `frontend/app/editor/[projectId]/page.tsx`

1. **Wire `comparisonMode` to the Video Player:**
   I will update the `<video>` element's `src` to dynamically switch based on the `comparisonMode` state (Original vs Dubbed).
   - If `comparisonMode === 'original'`, play `sourceMediaUrl`.
   - If `comparisonMode === 'dubbed'`, play `renderedVideoUrl`.

2. **Mount the Video Player with a Fallback:**
   I will ensure the `<video>` element is **always** mounted as long as `sourceMediaUrl` is available.
   - If the user selects "Dubbed" but `renderedVideoUrl` isn't built yet, the player will safely fallback to displaying the `sourceMediaUrl` (so you can still scrub and use the timeline).
   - I will add a small visual overlay in this fallback state that says *"Dubbed preview is not ready yet. Showing original video."* to avoid confusion.

3. **Remove the Invisible Audio Element:**
   The `comparisonAudioRef` and its invisible `<audio>` element (lines 2088-2104) are no longer needed, as we will use the main visible `<video>` player for all comparison playback. I will clean this up and update the "Play selected segment" button to rely on `videoRef` instead.

## Verification Plan
After making these changes, I will:
- Verify that the video player appears immediately after loading a project with source media.
- Verify that segment Play/Loop buttons work immediately without needing a dub.
- Verify that toggling between "Original" and "Dubbed" buttons seamlessly switches the video player's source.

---

# Fix Dub build Voice/Export stage stuck in a loop (never completes)

This plan addresses the UI bug where the Dub build status panel shows the Voice and Export stages cycling/looping for several minutes and never reaching Completed.

## The Problem
When **Dub only** (or **Dub + Lip-Sync**) is clicked, the build-status panel gets stuck:
- Voice shows `ACTIVE` and Export shows `WAITING`, then they appear to loop, and the overall progress sits at a low value (observed at `8%`) for several minutes.
- The job never reaches `completed`, so the Export never finishes and the preview never appears.

### Root cause analysis (traced from frontend poll to backend task)
The frontend `pollForLipSyncCompletion` in [page.tsx](../../frontend/app/editor/[projectId]/page.tsx) is a pure client poll (180 attempts x 5s). It is not the loop source; it only reflects what the backend job reports.

**Confirmed runtime failure (from Cloud Run logs):** the API container was deployed with `--memory=1Gi`, which is too small for the render pipeline. Requests also hit the exact 300-second Cloud Run timeout. The logs showed a repeating cycle:

```
Memory limit of 1024 MiB exceeded with ~1050 MiB used
→ Cloud Run terminates the container mid-request
→ Cloud Tasks receives 503/504 for /v1/internal/tasks/render-lipsync-project
→ Cloud Tasks retries the task from the top
→ task re-persists voice @ 8% and restarts TTS/media work
→ memory spikes again → terminated again → retry → loop
```

The job made real progress, got OOM-killed, restarted from its last checkpoint, and never reached Export — which the UI rendered as Voice/Export looping at 8%.

**Confirmed Dub-only contract bug:** the public route put `enable_lipsync: false` in the Cloud Tasks payload, but `RenderLipSyncProjectTaskPayload` did not declare that field and the internal handler did not forward it. Pydantic discarded the value, so `run_lipsync_project_pipeline` used its default `enable_lipsync=True`. Dub-only jobs therefore ran the more expensive neural lip-sync path, contrary to their persisted render mode.

### Note on an earlier hypothesis
An initial hypothesis was a hung Google TTS call. Logs disproved this as the trigger, so the speculative per-segment `asyncio.wait_for` change was removed. It would not stop an already-running thread-backed provider call and is outside this fix.

## Proposed Changes

### 1. Preserve Dub-only mode through Cloud Tasks (applied)
- [internal_tasks.py](../../backend/app/routers/internal_tasks.py): declare `enable_lipsync` on the task payload and forward it to the render pipeline.
- [test_lipsync_pipeline.py](../../backend/tests/test_lipsync_pipeline.py): verify that `enable_lipsync=False` reaches the pipeline.

### 2. Raise Cloud Run API memory (applied)
- All API deployment paths now use `--memory=2Gi`. The web service stays at 512Mi.
- Redeploy the API so the render pipeline has headroom for video/audio/FFmpeg workloads.

### 3. Align request deadlines (applied)
- All API deployment paths now default the Cloud Run request timeout to 1800 seconds.
- Render Cloud Tasks set a matching 1800-second dispatch deadline so the queue does not abandon a healthy long render earlier than Cloud Run.

## Verification Plan
- Redeploy with 2Gi, run a Dub-only build, and confirm it completes (reaches 100% / Export done) instead of OOM-looping.
- Confirm Dub-only logs do not enter the neural lip-sync path.
- Re-check Cloud Run logs for `render-lipsync-project`: no `Memory limit ... exceeded` / `503` / `504` entries during the build.
- Confirm the build-status panel progresses Voice → Export → Completed without bouncing.

