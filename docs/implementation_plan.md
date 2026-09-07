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
