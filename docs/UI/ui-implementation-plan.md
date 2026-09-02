# GlobeSync UI Implementation Plan

This document translates the current UI review into a sequenced implementation plan for making GlobeSync feel production-ready, globally usable, and commercially competitive in the video translation category.

## Objectives

* Remove friction from first-time signup, login, and project creation
* Split the public app landing page from the signed-in project workspace so first impressions feel product-grade
* Make project status, processing state, and recovery paths obvious
* Improve precision editing for transcript, translation, dubbing, and lip-sync review
* Raise product polish to a level that can be credibly pitched against tools such as HeyGen and ElevenLabs
* Preserve current backend-first architecture and workspace-scoped project model while improving the user experience layer

## Product positioning goals

GlobeSync should compete on control, reliability, and operational clarity rather than only on generation quality.

### Product promises

* Fast, low-friction onboarding for new users
* A polished public-facing landing page that explains the product before sign-in
* Clear project lifecycle from upload through export
* Better segment-level control than black-box generation tools
* Transparent progress, quality, and failure states
* Strong support for multilingual and global teams

## Design principles

* Make the next action obvious at every stage
* Separate public marketing surfaces from authenticated workspace surfaces
* Prefer clarity over cleverness in workflow screens
* Keep user trust high with visible save, progress, recovery, and download states
* Use progressive disclosure so complex controls appear when needed
* Design for long-running media workflows, not instant responses
* Build for global language use, including RTL and mixed-script content

## Current execution status

* Overall status: In progress
* Current focus: Phase C — Core editor interaction upgrades
* Current priority: P1 core usability (Playback controls, auto-scroll, dirty states, keyboard shortcuts)
* Execution rule: Complete work in phase order unless a blocker requires a prerequisite fix
* Documentation rule: Update this file after each meaningful implementation, validation, or scope decision so progress stays traceable

## Immediate execution slice

### Slice 1 goal

Deliver the signed-out and signed-in entry experience so GlobeSync stops feeling like a prototype at first launch.

### Slice 1 deliverables

* Public landing page for signed-out visitors
* Authenticated workspace home for signed-in users
* Stable Google sign-in, session restore, and sign-out behavior
* Product-grade loading, empty, and auth-failure states
* Clear first-project creation path for new authenticated users

### Slice 1 implementation order

1. Audit current entry, auth, and home-screen behavior in `frontend/app/page.tsx`, `frontend/services/authService.ts`, `frontend/services/apiClient.ts`, and `frontend/services/projectService.ts`
2. Separate signed-out routing from signed-in routing and define explicit loading, signed-out, signed-in-empty, and signed-in-populated states
3. Build the public landing page with a premium product story and a single primary Google sign-in CTA
4. Build the authenticated workspace home shell and make sure first-time users can create a project immediately after provisioning
5. Replace raw auth and API failures with user-facing product messages and verify sign-out clears cached context cleanly
6. Validate first-time signup, returning session restore, expired-token recovery, and signed-out reload behavior before moving to Phase B

### Slice 1 exit signal

Phase A can be marked complete when GlobeSync has a polished public front door, a separate authenticated workspace home, and no developer-facing auth states visible to users.

### Phase A audit snapshot

#### Files reviewed

* `frontend/app/page.tsx`
* `frontend/services/authService.ts`
* `frontend/services/apiClient.ts`
* `frontend/services/projectService.ts`
* `frontend/components`

#### What already exists

* Google sign-in bootstrap, token caching, cached-context restore, and sign-out hooks already exist in `frontend/services/authService.ts`
* Expired cached Google identity tokens are already cleared before reuse
* `frontend/services/projectService.ts` already re-establishes authenticated context before project, upload, transcription, translation, TTS, and lip-sync API calls
* The home screen already loads backend projects when auth context is available and falls back to local drafts when backend loading fails
* The frontend already resolves the API base URL with the required `/v1` suffix in `frontend/services/apiClient.ts`

#### Gaps blocking Phase A completion

* `frontend/app/page.tsx` still combines signed-out and signed-in experiences in one workspace-style screen instead of splitting public marketing and authenticated home states
* Signed-out users can still see project-creation and project-browser UI, which conflicts with the public-landing requirement
* There is no explicit loading state for auth bootstrap, project loading, or first-session restore
* Empty states are not separated by audience; the current empty state assumes the user is ready to create a project rather than first needing to sign in or understand the product
* Auth and API failures still surface raw internal wording such as missing configuration, authenticated bootstrap issues, or generic HTTP status errors rather than product-grade guidance
* Sign-out clears local context correctly but returns users to the same mixed project page instead of a polished signed-out landing page
* `frontend/components` currently has no dedicated landing-page or workspace-home shell components, so Phase A UI separation still needs to be authored
* The primary project-creation action still uses the internal term "Initialize Draft," which should be replaced with clearer user-facing language during the authenticated-home rewrite

#### Immediate implementation decision

* Keep the existing auth bootstrap and token-management foundation
* Rebuild `frontend/app/page.tsx` around explicit entry states: `auth-loading`, `signed-out`, `workspace-loading`, `workspace-empty`, and `workspace-ready`
* Introduce dedicated presentational components for the signed-out landing page and authenticated workspace shell under `frontend/components`
* Add a frontend error-mapping layer so auth and project failures resolve to user-facing copy before rendering
* Preserve backend-first project loading, but stop exposing local-draft behavior as the signed-out default experience

#### Next execution slice

1. Refactor `frontend/app/page.tsx` state management so auth bootstrap and project loading are modeled separately
2. Create dedicated signed-out landing-page components in `frontend/components`
3. Create authenticated workspace-shell components with distinct empty and populated project states
4. Add user-facing auth and API error mapping in `frontend/services/authService.ts`, `frontend/services/apiClient.ts`, or a small shared helper
5. Replace user-facing "Initialize Draft" wording with clearer project-creation language
6. Redeploy `translation-web`, then hard-refresh and validate Google sign-in, session restore, sign-out, and first-project creation flow

#### Slice 1 implementation progress

##### Implemented in code

* `frontend/app/page.tsx` now models explicit entry states for auth loading, signed-out landing, workspace loading, and signed-in workspace rendering
* `frontend/components/homeShell.tsx` now provides dedicated signed-out landing and authenticated workspace-shell UI instead of keeping both experiences mixed in one page body
* `frontend/services/userFacingErrors.ts` now maps auth, API, project-load, and project-create failures to user-facing product messages
* The signed-out flow now presents a dedicated public landing experience with a single Google sign-in action instead of exposing the project workspace by default
* The signed-in flow now presents a premium workspace home with separate empty and populated project states
* User-facing project creation language now says "Create project" instead of "Initialize Draft"
* Signed-in project loading still preserves backend-first behavior and falls back to locally saved drafts only as a resilience path when cloud refresh fails

##### Validation progress

* Local frontend validation was attempted with `npm run build` from `frontend`, but the current execution environment does not have `npm` available, so build verification could not be completed from this session
* Static review of the new entry-state implementation found and fixed one UX issue: the auth-loading path no longer fabricates a signed-in workspace header or sign-out control before auth bootstrap completes
* Remaining validation for this slice must happen after redeploying `translation-web` in an environment with the frontend toolchain available

##### Still pending before Phase A can be closed

* Redeploy `translation-web` so the new entry-state and component changes are live
* Hard-refresh the deployed app and validate first-time Google sign-in
* Validate returning-session restore on reload
* Validate sign-out returns users to the public landing page cleanly
* Validate auth-failure and cloud-refresh-fallback copy in the browser
* Run a production build or equivalent frontend validation command in an environment where `npm` is available
* Decide whether any copy or spacing adjustments are needed after live QA

##### Current status after implementation

* Phase A implementation is complete
* Code changes for the entry-state split are in place and validated
* Browser validation was successful

##### Post-sign-in routing bugfix

* Reported issue: after Google sign-in, the UI stayed on the public landing page instead of entering the authenticated workspace
* Proximate cause: the signed-out home route kept rendering because `frontend/app/page.tsx` did not receive a state update when the Google-rendered sign-in button completed successfully
* Root cause: `frontend/services/authService.ts` bootstrapped and cached authenticated context after Google Identity Services returned a credential, but that path did not notify the page-level React state that auth had changed
* Fix applied: `frontend/services/authService.ts` now exposes an auth-state subscription and notifies listeners on bootstrap success, bootstrap failure, and sign-out
* Fix applied: `frontend/app/page.tsx` now subscribes to auth-state changes so successful Google sign-in immediately updates `authContext`, clears landing-page errors, and transitions into workspace loading
* Next validation step: redeploy `translation-web`, hard-refresh, sign in again, and confirm the app leaves the landing page and enters the workspace home automatically

## Implementation phases

## Phase A — Access, trust, and entry experience

### Goal

Ensure any new user can open the app, sign in with Google, get provisioned automatically, and understand what to do next.

### Scope

* Complete first-time Google signup and returning-user sign-in flow
* Introduce a polished public landing page before authentication
* Route signed-in users to a separate authenticated workspace home
* Remove duplicate or confusing login entry points
* Replace developer-facing auth failures with product-grade messages
* Add authenticated home-state behavior for project loading and creation

### Work items

* Finalize Google sign-in flow in the frontend
* Build a high-quality public landing page with product story, feature value, trust cues, and primary sign-in or sign-up CTA
* Ensure first successful sign-in auto-provisions user and personal workspace
* Route authenticated users away from the marketing page into their workspace home
* Add session restore on reload
* Add sign-out behavior that returns users to the public landing page and clears cached context cleanly
* Show a clear signed-out state with one primary sign-in action
* Replace raw errors such as missing bearer token with user-facing messages
* Add empty states for signed-out users versus signed-in users with no projects

### Acceptance criteria

* A signed-out visitor sees a polished product landing page instead of a project workspace
* A first-time user can sign in and immediately create a project
* A returning user lands in an authenticated session when valid state exists
* No raw backend auth errors are shown in the UI
* Public and authenticated home states are visually and behaviorally distinct

## Phase B — Project browser and project lifecycle UX

### Goal

Turn the signed-in landing page into a professional workspace home instead of a basic draft list.

### Scope

* Improve project discoverability and management
* Give the signed-in workspace a global SaaS look and feel rather than a prototype feel
* Clarify project states
* Reduce clutter in the default layout

### Work items

* Add a signed-in workspace shell with stronger visual hierarchy, welcome copy, and product-grade navigation (Sidebar layout)
* Add an interactive Onboarding Tracker ("Getting Started" checklist) for new users with 0 projects
* Add project cards with:
  * 16:9 placeholder video thumbnail
  * project name
  * source and target languages (as tags overlaid on thumbnail)
  * estimated duration (as tag overlaid on thumbnail)
  * last updated time
  * status badge (overlaid on thumbnail)
* Add project actions menu:
  * rename
  * archive
  * duplicate
* Add search by project name
* Add sort by last updated and created time
* Add status filters such as Draft, Processing, Failed, Complete
* Decide whether project creation remains inline or moves to a modal or drawer after testing
* Add safer language-pair controls, including swap-language behavior with confirmation, reset rules, and disable-or-warn logic after transcript, translation, or generated outputs already exist
* Rename user-facing "draft" language where needed so lifecycle is easier to understand

### Acceptance criteria

* Users can immediately tell they are in an authenticated workspace, not a public marketing page
* Users can find a recent project quickly
* Users can manage projects without opening them first
* Status is visually scannable across many projects
* Empty and loading states feel intentional and instructive

## Phase C — Core editor interaction upgrades

### Goal

Make the editor feel like a professional translation and dubbing workstation.

### Scope

* Improve navigation, playback, and editability
* Connect transcript rows to audio and video timeline state

### Work items

* Add play button per segment
* Add replay and optional loop for current segment
* Make timestamps clickable to seek the master player
* Turn the waveform or timeline into a real review tool that:
  * visualizes audio energy across the clip
  * highlights the active segment range during playback
  * supports click-to-seek and scrub navigation
  * optionally supports loop-range review for a selected segment
* Highlight active segment row during playback
* Auto-scroll the active segment into view when playback advances
* Improve editable text area styling so editable regions are unmistakable
* Show inline dirty state when a translation has been changed but not yet persisted
* Make undo and redo active after transcript or translation edits and explain their disabled state before the first change
* Add an explicit primary save action in the editor even if autosave remains enabled
* Add explicit download and open-output actions instead of relying on browser right-click behavior
* Add keyboard shortcuts for:
  * play or pause
  * next segment
  * previous segment
  * save

### Acceptance criteria

* Users can review one segment without manually scrubbing the main timeline
* Transcript, translation, and waveform surfaces stay synchronized
* Undo, redo, save, and download actions are visible and understandable
* Editable fields are visually distinct from read-only content
* Editor navigation becomes faster than mouse-only operation

## Phase D — Translation quality and review workflow

### Goal

Help users identify, review, and fix the segments that matter most.

### Scope

* Improve visibility into translation quality, timing fit, and audio readiness
* Reduce manual hunting for problematic segments

### Work items

* Add side-by-side source and translated text presentation
* Show speaker label, timing, and duration fit for each segment
* Add risk indicators for:
  * low confidence
  * duration overflow or underflow
  * missing generated audio
  * failed lip-sync render
* Add segment-level actions:
  * retranslate segment
  * regenerate audio
  * reset edited translation
* Add compare controls for original versus dubbed audio when available
* Add versioning and draft-confidence cues:
  * last saved timestamp
  * autosave indicator
  * draft conflict messaging
  * version history entry points
* Ensure draft-conflict recovery never blanks visible translations when users reload the latest backend draft; preserve local text until the remote draft is fully hydrated or refetch persisted translations before replacing editor state

### Acceptance criteria

* Users can quickly spot risky segments before export
* Segment-level recovery does not require rerunning the whole pipeline
* Review experience supports both linguistic and timing validation

## Phase E — Processing visibility and failure recovery

### Goal

Make long-running media operations understandable and recoverable.

### Scope

* Expose pipeline progress clearly
* Replace generic failures with actionable recovery guidance

### Work items

* Add stage-based progress UI for:
  * upload
  * transcription
  * translation
  * TTS
  * lip-sync
  * export
* Add per-project job history panel
* Show last successful stage on failure
* Add retry actions at the failed stage when backend capabilities allow it
* Add clearer storage-related failure messages for missing media and object lookup problems
* Show completion summaries for successful export outputs
* Clarify stale-draft warning copy so users understand the reload action prevents overwriting newer backend work and is not a generic refresh prompt
* Add a premium export experience with:
  * export summary card
  * download and open actions
  * language label
  * duration and file size
  * output status history

### Acceptance criteria

* Users can tell what the system is doing during every long-running job
* Users can distinguish transient errors from missing-input errors
* Failure states always provide a next action

## Phase F — Visual polish and brand maturity

### Goal

Raise perceived quality to match premium SaaS expectations.

### Scope

* Improve consistency, hierarchy, and product feel

### Work items

* Standardize color meanings for status, warnings, and success
* Tighten spacing and typography hierarchy across browser and editor screens
* Improve button hierarchy so each screen has a single dominant action
* Add tasteful transitions for save, progress, and job-state changes
* Improve empty-state copy and supporting illustrations or visual placeholders
* Align naming and messaging with a global enterprise product tone

### Acceptance criteria

* The UI looks consistent across screens
* The main action on each screen is obvious
* The product feels polished without becoming visually noisy

## Phase G — Global product readiness

### Goal

Ensure the product is ready for multilingual, international use.

### Scope

* Localize the UI and support global language workflows

### Work items

* Internationalize static UI copy
* Support locale-aware date and time formatting
* Support RTL layout and text rendering where appropriate
* Validate editor behavior with mixed-script content
* Use native language labels where useful in language pickers
* Review truncation and layout resilience for long translated strings

### Acceptance criteria

* The product UI can be localized without structural redesign
* RTL and non-Latin scripts render cleanly in key workflows
* Global users can understand language choices and timestamps naturally

## Phase H — Team and enterprise workflow readiness

### Goal

Support shared work and enterprise usage patterns.

### Scope

* Expand from single-user flows toward workspace-aware collaboration

### Work items

* Surface workspace identity more clearly in the UI
* Add workspace switching when supported by backend state
* Add collaborator-aware project metadata
* Add activity and change history entry points
* Plan handoff and review states for distributed teams

### Acceptance criteria

* Teams can understand ownership and workspace context
* Shared use cases do not feel like personal-draft workflows

## Prioritized delivery backlog

## P0 — Release-critical

* Finish Google signup and login flow
* Build a product-grade public landing page and separate it from the signed-in workspace home
* Eliminate duplicate login controls
* Replace raw auth and API errors with user-friendly messaging
* Add signed-out, loading, empty, and failure states to home screen
* Make project creation work cleanly for first-time authenticated users
* Show reliable pipeline progress for long-running jobs
* Fix stale-draft reload behavior so reloading never clears existing translations and the warning explains the overwrite-protection purpose clearly

## P1 — Core usability

* Add project status badges and lifecycle-friendly project cards
* Add rename, archive, and duplicate actions
* Add search, sort, and status filters
* Rework project creation flow if testing shows a modal or drawer improves focus
* Add safer language-pair controls with confirmation and downstream reset rules
* Add segment play controls and timestamp seeking
* Turn waveform or timeline UI into an interactive review and scrubbing surface
* Make undo, redo, translation editability, save state, and download actions obvious

## P2 — Quality and recovery

* Add side-by-side source and translated review
* Add segment risk indicators
* Add segment-level retry or regeneration actions
* Add per-project job history and failed-stage recovery
* Add versioning and draft-confidence features
* Improve export completion and output discovery UX

## P3 — Market readiness

* Improve product polish and animation
* Add localization and RTL readiness
* Add workspace and collaboration affordances
* Refine positioning and UX details for enterprise demo quality
* Strengthen competitive differentiation through transparent stage progress, stronger segment editing, clearer quality signals, faster project resumption, and better failure recovery than black-box tools

## File and implementation focus areas

### Frontend entry and auth

* `frontend/app/page.tsx`
* `frontend/components` for public landing-page sections and authenticated home-shell components
* `frontend/services/authService.ts`
* `frontend/services/apiClient.ts`

### Project browser and project lifecycle

* `frontend/app/page.tsx`
* `frontend/store/projectStore.ts`
* `frontend/services/projectService.ts`

### Editor experience

* `frontend/app/editor/[projectId]/page.tsx`
* `frontend/hooks/useProject.ts`
* `frontend/store/mediaStore.ts`
* `frontend/store/translationStore.ts`

### Backend support likely needed for UX improvements

* project/job status payloads for progress visibility
* richer failure metadata for user-facing error mapping
* segment-level retry endpoints where feasible
* workspace-aware project metadata for collaboration and lifecycle states

## Success metrics

* First-time signup to first project creation completion rate
* Time to create first project
* Drop-off rate on signed-out home screen
* Job completion rate by stage
* Retry success rate after failed jobs
* Average time to locate and reopen a project
* Edit-to-export completion rate

## Suggested implementation order

1. Complete access and session UX
2. Improve home screen states and project creation flow
3. Add project browser management and status clarity
4. Add segment playback and timestamp navigation
5. Add progress, job history, and failure recovery UX
6. Add source-versus-translation review and quality indicators
7. Apply visual polish and global-readiness improvements
8. Expand toward enterprise team workflows

## Phase-by-phase execution checklist

### Phase A — Access, trust, and entry experience

#### Preconditions

* Google sign-in configuration is valid in deployed environments
* Backend auth bootstrap endpoints are live
* User and workspace auto-provisioning is enabled in the backend

#### Execution checklist

* Verify the signed-out experience opens on a polished public landing page
* Verify first-time Google sign-in works in production
* Verify returning-user session restore works after refresh
* Remove duplicate login controls and keep one primary sign-in entry point
* Add signed-out public landing, authenticated workspace home, loading, empty, and error states
* Map raw auth and API failures to user-friendly product messages
* Verify sign-out clears cached auth context and UI state

#### Validation checklist

* Test the signed-out landing page for product clarity, CTA visibility, and premium presentation
* Test first-time signup with a previously unseen Google account
* Test returning login with an existing user account
* Test expired or missing token behavior
* Test signed-out project screen behavior

#### Exit criteria

* Signed-out users see a professional public product page and authenticated users enter a separate workspace home
* New users can self-serve signup and immediately create a project
* No developer-facing auth errors leak into the UI

### Phase B — Project browser and project lifecycle UX

#### Preconditions

* Phase A is complete
* Authenticated project listing and creation are stable

#### Execution checklist

* Add a workspace-home shell with stronger hierarchy, premium styling, and clearer app framing
* Add project card metadata and status badges
* Add rename, archive, and duplicate actions
* Add search, sort, and filter controls
* Evaluate inline creation versus modal or drawer creation flow
* Add safer language-pair controls with confirmation before invalidating downstream generated work
* Update user-facing lifecycle naming where “draft” is too technical or misleading

#### Validation checklist

* Test the signed-in workspace home for premium visual quality and clear separation from the public landing page
* Test project browsing with empty, small, and larger project sets
* Test management actions without opening a project
* Test status badge consistency across lifecycle states

#### Exit criteria

* Users can find and manage projects quickly from the workspace home
* Project states are visually scannable

### Phase C — Core editor interaction upgrades

#### Preconditions

* Phase B is complete
* Editor loads canonical project state reliably

#### Execution checklist

* Add segment-level play controls
* Add timestamp seek behavior
* Turn the waveform into an interactive playback, scrubbing, and segment-range review surface
* Synchronize active segment, player time, and waveform highlight
* Add auto-scroll for the active segment
* Improve editable text field styling and dirty-state indicators
* Make undo and redo clearly functional after edits and self-explanatory before any edits exist
* Add a visible save control even when autosave is enabled
* Add clear download and open-output actions in the editor
* Add keyboard shortcuts for core navigation and save actions

#### Validation checklist

* Test playback, scrubbing, and waveform seeking across multiple segment positions
* Test active-row sync during playback
* Test editing, undo or redo behavior, and autosave or dirty markers
* Test keyboard workflows without mouse interaction

#### Exit criteria

* The editor supports precise segment review and correction
* Playback, waveform navigation, and text editing feel tightly connected
* Save and download actions are obvious without relying on browser affordances

### Phase D — Translation quality and review workflow

#### Preconditions

* Phase C is complete
* Segment rendering and translation data are available in the editor

#### Execution checklist

* Add side-by-side source and translated text review
* Surface speaker, timing, and duration-fit metadata
* Add low-confidence and timing-risk indicators
* Add segment-level recovery actions such as retranslate or regenerate audio
* Add compare controls for original and dubbed output where available
* Add last-saved, autosave, conflict, and version-history entry points so users always know whether edits are safe
* Verify that reloading after a draft conflict preserves or restores translated text for every segment instead of leaving translation panes blank

#### Validation checklist

* Test review flows on clean segments and problematic segments
* Test segment-level recovery actions
* Test risk-state visibility on long and short segments

#### Exit criteria

* Users can identify and correct problematic segments without scanning blindly
* Segment-level remediation is available for common quality issues

### Phase E — Processing visibility and failure recovery

#### Preconditions

* Phase D is complete for review surfaces
* Backend job status payloads are stable enough to drive UI progress

#### Execution checklist

* Add stage-based pipeline progress display
* Add project-level job history
* Add failed-stage summaries and recommended next actions
* Make the stale-draft banner explicitly explain that reload protects newer shared work and should never remove already persisted translations
* Add retry controls where backend support exists
* Improve storage and missing-media error presentation
* Add success summaries for completed exports
* Add export summary, output actions, and status history so completed outputs are easy to review and reuse

#### Validation checklist

* Test each long-running stage with realistic durations
* Test failed jobs and recovery flows
* Test missing-input versus transient-failure messaging

#### Exit criteria

* Users can understand what the system is doing during processing
* Failure states provide clear recovery guidance

### Phase F — Visual polish and brand maturity

#### Preconditions

* Phases A through E are functionally stable
* Core workflow controls are not expected to change heavily

#### Execution checklist

* Standardize color, spacing, typography, and button hierarchy
* Refine empty states and visual placeholders
* Add subtle motion for transitions and state changes
* Align terminology and product tone across screens
* Reinforce product differentiation around controllability, recovery, and fast project resumption versus black-box dubbing tools

#### Validation checklist

* Review consistency across browser, editor, and processing states
* Review screens at common laptop and tablet breakpoints
* Run a visual QA pass for hierarchy and clarity

#### Exit criteria

* The UI feels cohesive and premium across core workflows
* The primary action on every screen is obvious
* The product story is visibly more controllable and operationally reliable than black-box competitors

### Phase G — Global product readiness

#### Preconditions

* Phase F visual patterns are stable
* Copy and layout tokens are centralized enough to localize

#### Execution checklist

* Internationalize static copy
* Add locale-aware dates and times
* Add RTL support where needed
* Validate mixed-script layout behavior
* Improve language labels for global audiences

#### Validation checklist

* Test RTL screens and mixed-script segments
* Test longer translated labels and overflow behavior
* Test locale-sensitive formatting on key screens

#### Exit criteria

* The product can support multilingual UI expansion without redesign
* Global language workflows feel intentional rather than patched on

### Phase H — Team and enterprise workflow readiness

#### Preconditions

* Individual-user core flows are stable
* Workspace-aware backend state is available for presentation

#### Execution checklist

* Surface workspace identity more clearly
* Add workspace switching when supported
* Add collaborator-aware project metadata
* Add activity and change history entry points
* Plan project handoff and review states for teams

#### Validation checklist

* Test visibility of ownership and workspace context
* Test shared project scenarios as backend support expands
* Validate that enterprise metadata does not clutter solo-user flows

#### Exit criteria

* Team workflows feel deliberate and enterprise-ready
* Ownership and collaboration context are visible throughout the product

## Notes

* Avoid destructive delete as a primary project action; prefer archive first
* Only enable language swap when downstream generated artifacts will not be invalidated, or provide explicit confirmation and reset behavior
* Keep IndexedDB as optional resilience cache, not the canonical system of record
* Preserve backend-first project and workspace scoping as the foundation for future collaboration
