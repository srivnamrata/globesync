# GlobeSync UI Implementation Verification Guide

This document provides step-by-step instructions to verify that each phase and sub-part of `docs/UI/ui-implementation-plan.md` has actually been completed in the running application. Use it as a manual QA script after any deployment, or as a periodic regression check.

## How to use this guide

1. Deploy the latest build (`.\deploy\deploy-cloudrun.ps1` or `deploy/deploy-cloudrun.sh`) and confirm the API and web revisions are `Ready`.
2. Work through each phase in order. Each work item has: **Setup**, **Steps**, **Expected result**, and **Pass/Fail**.
3. Test at these breakpoints where noted: 320px (mobile), 768px (tablet), 1024px, 1440px (desktop), and 200% browser zoom.
4. Use two accounts where a check requires multiple workspace members (Phase H).
5. Record failures with a screenshot, the breakpoint, and the browser console output.

---

## 0. Pre-flight: Post-deployment verification checklist

| # | Check | Steps | Expected result |
|---|---|---|---|
| 0.1 | API health | `curl.exe -i https://<api-host>/health` | `200` with JSON body reporting `healthy` |
| 0.2 | CORS preflight | `curl.exe -i -X OPTIONS "https://<api-host>/v1/translation/languages" -H "Origin: https://<web-host>" -H "Access-Control-Request-Method: GET"` | `200`/`204` with `Access-Control-Allow-Origin` matching the web host |
| 0.3 | Language list loads | Open the web app, check Network tab for `/v1/translation/languages` | `200` response, no CORS fallback warning in console |
| 0.4 | GCS bucket CORS | Upload a file and load a waveform in the editor | No CORS error in console when GET/PUT-ing to the raw/exports bucket |

---

## Phase A — Access, trust, and entry experience

### A.1 Signed-out landing page

**Setup:** Open the web app in a private/incognito window (no cached session).
**Steps:** Load the root URL.
**Expected:** A polished public landing page renders (headline, feature cards, single Google sign-in CTA). No project browser, no project-creation form, no "Initialize Draft" wording is visible.
**Pass/Fail:** ___

### A.2 First-time Google sign-in and auto-provisioning

**Steps:** Click the Google sign-in button and complete auth with an account that has never used the app.
**Expected:** After redirect, the app leaves the landing page automatically (no manual refresh needed) and enters the authenticated workspace home with an empty-project state. No manual "sign in again" step is required.
**Pass/Fail:** ___

### A.3 Returning-session restore

**Steps:** With an active session, reload the page (`F5`).
**Expected:** The app restores the authenticated workspace home directly, without flashing the signed-out landing page first.
**Pass/Fail:** ___

### A.4 Sign-out behavior

**Steps:** Click Sign out from the workspace.
**Expected:** The app returns to the public landing page; local/cached auth context and workspace ID are cleared (verify via Application > Local/Session storage or by reloading and confirming signed-out state persists).
**Pass/Fail:** ___

### A.5 Expired/invalid token recovery

**Steps:** Manually clear/corrupt the cached token (or wait for expiry), then reload.
**Expected:** App shows the signed-out landing page with no raw error text (no "missing bearer token", no stack traces, no generic `500`/`401` text). A user-facing message may appear if sign-in failed previously.
**Pass/Fail:** ___

### A.6 No duplicate login controls

**Steps:** Inspect the landing page and any auth-related error states.
**Expected:** Exactly one primary sign-in entry point is visible at any time.
**Pass/Fail:** ___

---

## Phase B — Project browser and project lifecycle UX

### B.1 Workspace home shell

**Steps:** Sign in and view the workspace home.
**Expected:** Clear navigation/sidebar, welcome copy, and visual separation from the public landing page (different layout, dark workspace theme, workspace identity visible).
**Pass/Fail:** ___

### B.2 Onboarding tracker (0 projects)

**Setup:** Use an account with zero projects.
**Steps:** View the workspace home.
**Expected:** A "Getting Started" checklist/tracker is shown instead of a bare empty list.
**Pass/Fail:** ___

### B.3 Project card metadata

**Setup:** Create at least one project with uploaded media.
**Steps:** View the project card on the workspace home.
**Expected:** Card shows a 16:9 thumbnail/placeholder, project name, source/target language tags, duration tag, last-updated time, and a status badge overlaid on the thumbnail.
**Pass/Fail:** ___

### B.4 Project actions menu (rename/archive/duplicate)

**Steps:** Open a project card's action menu (`⋯`) and trigger each action.
**Expected:** Rename updates the name in place; archive removes it from the default active list; duplicate creates a new project shell. Menu closes with `Escape` and with an outside click.
**Pass/Fail:** ___

### B.5 Search

**Steps:** Type a partial project name into the search box.
**Expected:** List filters live to matching projects only.
**Pass/Fail:** ___

### B.6 Sort

**Steps:** Change sort to "last updated" and "created time".
**Expected:** Project order changes accordingly.
**Pass/Fail:** ___

### B.7 Status filters

**Steps:** Click each status filter (Draft/Processing/Failed/Complete).
**Expected:** List filters to only that status; filter buttons expose `aria-pressed` state (inspect via accessibility tree).
**Pass/Fail:** ___

### B.8 Filtered empty state

**Steps:** Search for a project name that doesn't exist, or select a status filter with zero matches.
**Expected:** A clear empty-state message appears with a "Clear search and filters" action that restores the full list.
**Pass/Fail:** ___

### B.9 Safer language-pair controls

**Steps:** Open a project that already has a transcript/translation, then attempt to swap source/target languages.
**Expected:** A confirmation/warning appears explaining downstream impact before the swap proceeds (no silent invalidation of existing work).
**Pass/Fail:** ___

---

## Phase C — Core editor interaction upgrades

### C.1 Segment playback controls

**Steps:** Open a project with transcript segments. Click `PLAY` and `LOOP` on a segment.
**Expected:** Media plays from that segment's start time; loop repeats just that segment's range.
**Pass/Fail:** ___

### C.2 Clickable timestamps / timeline seek

**Steps:** Click a segment's timestamp and click a bar in the segment timeline.
**Expected:** The preview player seeks to that time in both cases.
**Pass/Fail:** ___

### C.3 Waveform review

**Steps:** Load a project with media. Observe the waveform under the timeline. Click and drag across it.
**Expected:** Waveform renders audio energy; clicking/dragging scrubs the player; the active segment range is visually highlighted during playback.
**Pass/Fail:** ___

### C.4 Auto-scroll to active segment

**Steps:** Play media with the transcript panel scrolled away from the current segment.
**Expected:** The transcript panel auto-scrolls to keep the active segment visible.
**Pass/Fail:** ___

### C.5 Editable field styling and dirty state

**Steps:** Edit a translation textarea.
**Expected:** The field is visually distinct (border color) while dirty/unsaved, distinguishable from saved fields.
**Pass/Fail:** ___

### C.6 Undo/redo

**Steps:** Edit a segment, then click Undo, then Redo.
**Expected:** Text reverts and then reapplies. Undo/redo are disabled (not just inert) before any edit exists, with a title/tooltip explaining why.
**Pass/Fail:** ___

### C.7 Explicit save control

**Steps:** Locate the Save/`Saved` control in the editor header.
**Expected:** A visible save action or save-state indicator exists even though autosave runs in the background.
**Pass/Fail:** ___

### C.8 Download/open-output actions

**Steps:** After a completed build, use "Open video" and "Download video".
**Expected:** Both work without relying on browser right-click "Save As".
**Pass/Fail:** ___

### C.9 Keyboard shortcuts

**Steps:** With focus outside a text field, press Space (play/pause), Arrow Up/Down (previous/next segment), Ctrl/Cmd+S (save).
**Expected:** Each shortcut performs its action; shortcuts do not fire while typing inside a textarea/input.
**Pass/Fail:** ___

---

## Phase D — Translation quality and review workflow

### D.1 Side-by-side source/translation

**Steps:** Open a segment row.
**Expected:** Source text and translated text are shown side by side with speaker tag, timestamp, and duration-fit indicator.
**Pass/Fail:** ___

### D.2 Risk indicators

**Steps:** Inspect segments with known issues (short/long duration ratio, low confidence, missing audio, failed lip-sync).
**Expected:** Corresponding badges appear: "Too short/long · Nx", "Low confidence", "No audio", "Lip-sync failed". Segments with none of these show "OK".
**Pass/Fail:** ___

### D.3 Segment-level actions (retranslate / regenerate audio / reset)

**Steps:** Open a segment's `⋯` menu.
1. Click **Retranslate**. Expected: a visible status message appears immediately (not just a silent button-label change); text updates on success; audio badge becomes "No audio" until regenerated.
2. Click **Regenerate audio**. Expected: status updates and the "No audio" badge clears to "OK" on success.
3. Click **Reset to original** on an edited segment. Expected: enabled only after a change exists; clicking restores the original text.
**Pass/Fail:** ___

### D.4 Menu dismissal

**Steps:** Open a segment `⋯` menu, then (a) press `Escape`, (b) click outside the menu.
**Expected:** Both close the menu. Clicking Retranslate/Regenerate/Reset inside the menu still triggers the action (not swallowed by the outside-click handler).
**Pass/Fail:** ___

### D.5 Compare original vs. dubbed audio

**Steps:** After a build completes, use "Compare audio" > Original / Dubbed / "Play selected segment".
**Expected:** Buttons are reachable and not clipped by container overflow (check on a project with many segments so the right panel scrolls); playback switches between source and dubbed audio for the selected segment.
**Pass/Fail:** ___

### D.6 Save-state and conflict cues

**Steps:** Edit a segment, wait for autosave, then simulate a draft conflict (edit in two tabs).
**Expected:** Save-state text shows `Saving`/`Saved just now`; conflict banner appears with "Keep my edits" / "Load server draft" options; reloading the server draft never blanks other segments' translations.
**Pass/Fail:** ___

---

## Phase E — Processing visibility and failure recovery

### E.1 Stage-based progress (upload/transcribe/translate/voice/lip-sync/export)

**Steps:** Start a new project, upload media, and run the full pipeline through to a completed dub or dub+lip-sync build.
**Expected:** A stage panel shows Upload → Transcribe → Translate → Voice → (Lip-sync, only when applicable) → Export with per-stage Waiting/Active/Done labels and a progress bar.
**Pass/Fail:** ___

### E.2 Dub-only mode excludes Lip-sync

**Steps:** Run **Dub only** (not Dub + Lip-Sync) to completion.
**Expected:** The build-status panel does **not** show a "Lip-sync" stage at all (not shown as Done, not shown as skipped) — only Upload/Transcribe/Translate/Voice/Export appear.
**Pass/Fail:** ___

### E.3 Failure recovery guidance

**Steps:** Force a failure at a stage (e.g., invalid media) or use a known-failing project.
**Expected:** Panel shows "Stopped during {stage}", the last successful checkpoint, and stage-specific recovery copy confirming saved translations/outputs are preserved.
**Pass/Fail:** ___

### E.4 Retry actions

**Steps:** With a failed transcription or translation operation, use the retry control in the editor.
**Expected:** Retry dispatches a new operation, disables while in flight, and adopts the new operation's queued state.
**Pass/Fail:** ___

### E.5 Large file resumable upload

**Steps:** Upload a media file larger than 100 MB.
**Expected:** Upload proceeds via resumable/chunked path; a real percentage (not static 0%) is shown in both the message and the progress bar.
**Pass/Fail:** ___

### E.6 Export history

**Steps:** Open "Exports" after at least one completed build.
**Expected:** Each entry shows status, language, size, render time (or "Render time unavailable" for older records), Open, Download, and retry-on-failure where applicable. Layout stacks correctly at 320px.
**Pass/Fail:** ___

### E.7 Dialog dismissal (version/export/readiness)

**Steps:** Open History, Exports, and Readiness dialogs one at a time. Test `Escape` and clicking the backdrop for each.
**Expected:** Both close the dialog; clicks inside the dialog do not close it.
**Pass/Fail:** ___

### E.8 Audio-status refresh after build

**Steps:** Before a build, note a segment shows "No audio". Run a Dub build to completion.
**Expected:** After the build completes, the segment's audio badge updates to reflect the real generated-audio status without requiring a manual page refresh.
**Pass/Fail:** ___

### E.9 Pipeline-operation hydration on reload

**Steps:** Start a translation/transcription operation, then reload the page mid-operation.
**Expected:** The stage panel restores the in-progress or failed state from the server rather than disappearing.
**Pass/Fail:** ___

---

## Phase F — Visual polish and brand maturity

### F.1 Consistent status colors

**Steps:** Compare status colors across workspace cards, pipeline stages, and badges.
**Expected:** Same semantic meaning always uses the same color family (success=green, warning=amber, error=red/rose, processing=indigo/blue), consistently.
**Pass/Fail:** ___

### F.2 Single dominant action per screen

**Steps:** View the workspace home and the editor header.
**Expected:** One clearly primary button per screen (e.g., "Create project", "Dub + Lip-Sync"); secondary actions are visually quieter.
**Pass/Fail:** ___

### F.3 Motion and reduced-motion

**Steps:** Enable OS "reduce motion" setting, then hover a project card and trigger a save/progress transition.
**Expected:** With reduced motion on, transform/scale animations are suppressed but color/opacity feedback still communicates state.
**Pass/Fail:** ___

### F.4 Empty-state quality

**Steps:** View empty states (no projects, filtered-empty, no export history).
**Expected:** Each has explanatory copy and a next action, not a bare blank area.
**Pass/Fail:** ___

---

## Phase G — Global product readiness

### G.1 RTL language fields

**Steps:** Create/open a project with target language Arabic, Hebrew, or Urdu.
**Expected:** The translated-text field renders right-to-left; source field direction is independent and based on its own language.
**Pass/Fail:** ___

### G.2 Native language labels

**Steps:** Open a source/target language picker.
**Expected:** Native names are shown where the backend provides them (e.g., "Hindi (हिन्दी)"); falls back to English name otherwise.
**Pass/Fail:** ___

### G.3 Locale-aware date/time

**Steps:** View Export History / Version History timestamps.
**Expected:** Dates/times render in the browser's locale format; an invalid timestamp shows "Date unavailable" instead of "Invalid Date".
**Pass/Fail:** ___

### G.4 Mixed-script and long-text resilience

**Steps:** Enter a long mixed-script translation (e.g., Latin + Devanagari) into a segment.
**Expected:** Text wraps within the field without horizontal overflow or clipped controls.
**Pass/Fail:** ___

### G.5 Document language/direction metadata

**Steps:** Inspect `<html>` element attributes via browser dev tools.
**Expected:** `lang` and `dir` are set at the document level (English/LTR by default), while individual RTL fields override locally.
**Pass/Fail:** ___

---

## Phase H — Team and enterprise workflow readiness

### H.1 Workspace identity visibility

**Steps:** Sign in and view desktop and mobile (320px) headers.
**Expected:** Workspace name is visible in both; long names truncate safely without breaking layout.
**Pass/Fail:** ___

### H.2 Membership role display

**Steps:** View the workspace header.
**Expected:** The authenticated user's role (e.g., "Owner") is shown alongside workspace identity.
**Pass/Fail:** ___

### H.3 Workspace switching

**Setup:** Use an account that belongs to 2+ workspaces (or add a second membership via the backend for test purposes).
**Steps:** Open the workspace switcher and select a different workspace.
**Expected:** A switcher UI appears only when 2+ workspaces exist; switching updates the active workspace context (`X-Workspace-Id`), reloads workspace-scoped projects, and does not copy/mutate any project, draft, version, or artifact data.
**Pass/Fail:** ___

### H.4 Collaborator member-count summary

**Steps:** View the workspace home for a workspace with 2+ members.
**Expected:** A read-only member-count summary is shown. No invite, remove, or role-edit controls exist (these are intentionally deferred).
**Pass/Fail:** ___

### H.5 Deferred capabilities are absent, not broken

**Steps:** Look for collaborator invite/role-edit UI, activity/audit history, and handoff/review states anywhere in the app.
**Expected:** None of these exist yet — this is expected per the plan's "Intentionally deferred" section, not a defect. Do not file these as bugs; confirm they remain explicitly out of scope until backend contracts exist.
**Pass/Fail (confirm absence, not presence):** ___

### H.6 Backend contract tests

**Steps:** Run `pytest backend/tests/test_auth_api.py -q`.
**Expected:** All tests pass, including workspace-list (user-scoped) and workspace-members (active-workspace-scoped) tests.
**Pass/Fail:** ___

---

## Cross-cutting: Accessibility and responsive requirements

Apply these checks across all phases above, not as a separate one-time pass.

| # | Check | Steps | Expected result |
|---|---|---|---|
| X.1 | Keyboard-only flow | Unplug/ignore the mouse; complete create-project, edit-segment, and export-review tasks using Tab/Enter/Space/Arrow keys only | All tasks are completable; focus is always visible |
| X.2 | Focus containment in dialogs | Open History/Exports/Readiness dialog, press Tab repeatedly | Focus stays inside the dialog; closing restores focus to the triggering control |
| X.3 | Screen reader labels | Inspect accessible names (browser dev tools Accessibility tab) for icon-only buttons, menus, and progress bars | Every icon-only control has a meaningful accessible name; menus expose `menu`/`menuitem` roles; progress bars expose `aria-valuenow`/`aria-valuetext` |
| X.4 | Color-independent status | View status badges with a grayscale filter or color-blindness simulator | Status is still distinguishable via text/icon, not color alone |
| X.5 | Responsive breakpoints | Resize/test at 320px, 768px, 1024px, 1440px, and 200% zoom | No horizontal overflow, no clipped primary actions, controls remain usable |
| X.6 | Long text resilience | Use a very long project name and a 2-3x expanded translation | Layout truncates/wraps gracefully without hiding primary actions |

---

## Reporting results

For each failed check, capture:
1. Phase and item number (e.g., "D.3")
2. Breakpoint/browser used
3. Screenshot or screen recording
4. Console errors, if any
5. Whether the issue is a regression (previously passing) or a new gap

File fixes against the specific phase in `docs/UI/ui-implementation-plan.md` and record the resolution in `docs/UI/ui-implementation-changes.md`.
