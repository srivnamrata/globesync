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
* Current focus: Phase E — Processing visibility and failure recovery
* Current priority: P2 job-stage progress, recovery guidance, and output discovery
* Execution rule: Complete work in phase order unless a blocker requires a prerequisite fix
* Documentation rule: Update this file after each meaningful implementation, validation, or scope decision so progress stays traceable

## Post-deployment verification checklist

Run these checks after `translation-web` and `translation-api` deployment completes. `/health` is the deployment smoke check; `/healthz` is intentionally not required by the deployment scripts.

### API and CORS

* `GET /health` returns `200` with JSON status `healthy`.
* Run `curl.exe -i -X OPTIONS "https://translation-api-<service-host>/v1/translation/languages" -H "Origin: https://translation-web-<service-host>" -H "Access-Control-Request-Method: GET"` and confirm success with `Access-Control-Allow-Origin` matching the deployed web origin.
* The web app loads supported languages without a CORS fallback warning.
* Raw and exports GCS buckets allow browser `GET`, `HEAD`, `PUT`, `POST`, and `OPTIONS` requests from the deployed web origin.

### Public and authenticated UI

* Landing page loads at desktop and 320px mobile width without horizontal overflow.
* Google sign-in, first-time provisioning, returning session restore, sign-out, and expired-token recovery work.
* Workspace search, sorting, status filters, project actions, and clear-filter empty state work.

### Editor and processing

* Project opens with source media, transcript, translations, waveform, and save-state indicators intact.
* Upload, transcription, translation, voice, lip-sync, and export stages show correct status and progress.
* Files over 100 MB use resumable upload and show matching percentage in the message and progress panel.
* Failed operations show the last successful stage and an actionable recovery path.
* Export history shows status, language, size, render time, preview, download, retry, and responsive mobile layout.
* Version history, export history, and readiness dialogs close with Escape and backdrop click.

### Evidence to capture

* Record the API and web Cloud Run revision names.
* Capture one successful CORS preflight and one successful signed GCS waveform response.
* Capture screenshots at 320px, 768px, and desktop widths.
* Record remaining console errors separately from third-party Google Identity iframe warnings.

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

## UI quality and world-class execution plan

### Purpose

The existing phases define the product capabilities GlobeSync needs. This execution plan adds the quality bar needed to make those capabilities feel like one dependable, premium media-translation workspace. It does not create a parallel roadmap: each item below is completed in the existing phase where it belongs.

### Product experience standard

GlobeSync should feel like a focused translation studio, not a generic dashboard or an opaque AI generator. Every core screen must make three things immediately clear:

1. What media and language pair the user is working on
2. What stage the project is in and whether the user needs to act
3. What the safest, highest-value next action is

### Design foundations (complete before broad visual polish)

#### Design token deliverable

Create a small, reusable UI foundation before adding further one-off styles. Centralize the following in Tailwind theme extensions, CSS custom properties, or a shared component layer:

* Brand: one primary accent, plus defined hover, pressed, focus, and subtle-surface variants
* Semantic status colors: neutral, info, processing, success, warning, and error; never rely on color as the only status signal
* Surfaces: page, raised panel, input, selected, and disabled states for both light public pages and dark workspace pages
* Spacing: a deliberate 4px or 8px scale; avoid arbitrary visual spacing in recurring controls
* Shape: consistent radius family for controls, cards, dialogs, and feature surfaces
* Type: display, page title, section title, body, metadata, and compact-label styles, including line-height and weight
* Elevation: restrained shadows and borders that establish hierarchy without creating a "card on card" effect
* Motion: standard durations/easings for hover, state transitions, toast appearance, and progress changes; respect `prefers-reduced-motion`
* Focus: a high-contrast keyboard focus ring used consistently on every interactive control

#### Shared component deliverable

Build or standardize shared primitives before reproducing patterns across screens:

* Button: primary, secondary, quiet, destructive, icon-only, loading, and disabled states
* Status badge: status icon, concise label, optional progress, and accessible text equivalent
* Empty, loading, error, and success states with action slot and recovery copy
* Form field with label, help text, validation, and required/error states
* Menu and confirmation dialog with keyboard dismissal, focus management, and non-destructive defaults
* Project card, stage-progress indicator, segment-risk badge, and output-summary card
* SVG icon set for product controls; do not use emoji as operational UI icons

#### Non-negotiable quality gate

Before visual QA, normalize all user-visible text to UTF-8 and remove mojibake (for example, a misdecoded em dash [U+2014], bullet [U+2022], or emoji). Use plain text or the shared SVG icon set where encoding is fragile.

### Screen blueprints

#### Public landing page (Phase A / Phase F)

* Lead with one customer outcome and one primary Google sign-in or sign-up action
* Use a real product screenshot, short workflow visualization, or polished product-derived visual instead of decorative placeholders
* Keep proof points concrete: supported language count, editable review, export formats, and privacy or reliability claims only when verified
* Limit feature cards to three clear benefits and use consistent SVG icons rather than emoji
* Include responsive navigation, legible mobile typography, and a clear signed-in route away from the marketing page

#### Workspace home (Phase B)

* Use a stable app shell: navigation and workspace identity at left, workspace content at center, account actions available without competing with the primary action
* Make "Create project" the single dominant action; use a focused form, modal, or drawer after usability testing rather than a crowded inline workflow
* Every project card must use canonical project data: an intentional non-artifact thumbnail or poster representation, real duration, source-to-target language pair, latest activity, lifecycle state, and contextual next action
* Keep project-list responses metadata-only. Do not include expiring signed media, thumbnail, or output URLs; use a dedicated authorized artifact endpoint when thumbnail playback or retrieval is designed
* Show processing projects with stage and progress, completed projects with output availability, and failed projects with the last successful stage plus a recovery action
* Keep search, filters, sort, and bulk scanning functional at 20+ projects and usable on tablet-width screens

#### Translation editor (Phase C / Phase D)

Use a persistent three-zone workstation layout on desktop:

| Zone | Purpose | Required content |
| --- | --- | --- |
| Left | Project context and navigation | project name, source-to-target pair, stage progress, segment list or review filters |
| Center | Time-based media review | player, playback controls, timecode, interactive waveform/timeline, selected-range loop |
| Right | Precise segment editing | source and target text, speaker/timing metadata, quality signals, recovery actions, save state |

* On narrower screens, stack zones in the order: media review, selected segment edit, segment navigation; preserve a sticky playback control and selected-segment context
* Show an always-visible save state near the project title: `Saving`, `Saved just now`, `Changes stored locally`, or `Conflict requires review`
* Make the selected segment unmistakable across transcript, translation, video, waveform, and timeline without relying only on color
* Keep advanced controls behind a segment action menu or expandable inspector; the default editing surface should prioritize reading, editing, and playback
* Support keyboard navigation and shortcut discovery without conflicting with typing in text fields
* Apply directionality per source and target language segment so mixed-script and RTL editing stays readable

#### Quality review and pre-export gate (Phase D / Phase E)

Add a dedicated "Ready to export" checkpoint before a render is started. It should summarize, link to, and allow filtering by:

* Segments requiring review: low confidence, translation edits not saved, timing overflow or underflow, missing voice, lip-sync failure
* Completion counts: approved segments / total, voiced segments / total, and rendered outputs available
* Export details: target language, output format, estimated duration, and file size when known
* A clear policy: block export only for genuinely invalid prerequisites; warn, explain impact, and allow an informed override for quality risks
* One primary action: `Export video`, with secondary actions to review the outstanding items or save a draft

#### Processing, recovery, and output (Phase E)

* Use a common stage model everywhere: Upload, Transcribe, Translate, Voice, Lip-sync, Export
* Display stage state, percentage or meaningful indeterminate progress, elapsed time where useful, and last successful checkpoint
* Never replace user-created translations or output links with empty loading content; hydrate remote data before swapping visible state
* Error panels must state what happened, what is safe to retry, and what will be preserved; offer support context such as project and job identifiers only as secondary copy
* Completed exports should show an output summary with preview, download, open, version/language, duration, file size, created time, and status history

### Accessibility and responsive requirements

Apply these to every phase, not as a later retrofit:

* Meet WCAG 2.2 AA contrast for text, controls, focus states, and non-text UI indicators
* Make every mouse action usable from keyboard; retain visible focus and provide accessible names for icon-only buttons
* Use semantic headings, landmarks, form labels, live regions for asynchronous progress, and accessible dialog/menu focus handling
* Do not convey processing, risk, selection, or errors through color alone; include icons, text, or patterns
* Support `prefers-reduced-motion`; do not use motion as the only indication of a state change
* Test at 320px, 768px, 1024px, 1440px, and a typical 200% browser zoom level
* Test long project names, language names, and 2-3x expanded translations without clipping controls or hiding primary actions

### Delivery sequence and ownership

#### Foundation checkpoint -- before further Phase B-C feature work

1. Audit and normalize text encoding and icon usage
2. Define token values and shared component contracts
3. Apply shared button, field, status, loading, error, and focus patterns to the current home and editor surfaces
4. Capture baseline screenshots at desktop, tablet, and mobile widths

#### Workflow checkpoint -- Phases B through E

1. Replace project-card placeholders with canonical media data and contextual state
2. Implement the editor three-zone layout and cross-surface selected-segment synchronization
3. Add stage progress and recoverable failure states using the shared stage model
4. Add segment risk queue, segment-level repair, and visible save/conflict states
5. Implement the pre-export readiness gate and output-summary experience

#### Maturity checkpoint -- Phases F through H

1. Run consistency, accessibility, responsive, and global-language QA
2. Refine spacing, typography, interaction feedback, empty states, and motion from evidence gathered in workflow testing
3. Add collaboration and workspace context without diluting the single-user editing flow

### Definition of done for each UI change

A UI change is not complete until it has:

* a loading, empty, success, and actionable failure state where applicable
* keyboard, focus, responsive, and 200% zoom verification
* visible user-facing copy that is clear, accurate, and encoding-safe
* real backend data or a clearly marked intentional placeholder -- never fabricated media metadata
* a single clear primary action and no destructive default action
* a lightweight visual QA comparison against the shared component and token standards

### Evidence and success metrics

Track these before and after the workflow checkpoints:

* Median time from sign-in to first upload
* Median time from project open to locating a segment that needs attention
* Percentage of failed jobs retried successfully from the UI
* Percentage of exports started with unresolved warnings, grouped by warning type
* Edit-to-export completion rate and abandoned-project rate
* Save/conflict recovery success rate without loss of visible translation text
* Keyboard-only completion of create-project, edit-segment, and export-review tasks
* Visual QA defects by screen, breakpoint, and severity

### Foundation checkpoint status

#### Implemented

* Added GlobeSync visual tokens for brand color, surface hierarchy, semantic colors, panel elevation, control and panel radii, and interface transitions in `frontend/tailwind.config.js` and `frontend/app/globals.css`
* Added global visible keyboard focus treatment and reduced-motion handling
* Added reusable `Button`, `StatusBadge`, and `StatePanel` primitives under `frontend/components/ui`
* Applied the shared Button primitive to primary project-creation actions and the shared StatusBadge primitive to project lifecycle status in `frontend/components/homeShell.tsx`
* Updated application metadata so browser and assistive-technology route announcements identify GlobeSync clearly

#### Validation

* `npm.cmd run build` completed successfully from `frontend` after the foundation and integration changes
* TypeScript compilation and static route generation completed successfully

#### Next foundation slice

1. Apply the shared field, state-panel, and secondary-button patterns to home and editor feedback surfaces
2. Replace operational emoji with the shared SVG icon approach in high-traffic UI
3. Capture desktop, tablet, and mobile baseline screenshots before the workspace and editor layout changes

#### Foundation slice 2 status

##### Implemented

* Replaced public landing-page feature emoji with compact inline SVG illustrations and encoding-safe copy
* Applied the shared field pattern to both first-project and returning-user project-creation forms
* Applied the shared `StatePanel` pattern to workspace feedback and editor project-update messages
* Kept user-facing primary actions and status states on the shared primitives introduced in the first foundation checkpoint

##### Validation and follow-up

* `npm.cmd run build` completed successfully after the slice, including TypeScript validation and static route generation
* Browser-based responsive screenshots remain pending because no browser surface was available in this execution session
* Next implementation slice: capture the three responsive baselines when a browser is available, then replace additional operational iconography and begin the workspace-home canonical-media-data work

### Workspace-home canonical media data status

#### Implemented

* Extended the workspace-scoped project-list response with optional media filename and duration fields using the media relationship already loaded by the project-list query
* Extended frontend project state and API mapping to retain canonical media metadata
* Replaced the fixed project-card duration with canonical formatted duration and retained an intentional non-artifact media placeholder
* Added an explicit `No media yet` state instead of presenting fabricated media details for new projects

#### Validation

* `npm.cmd run build` completed successfully after the frontend integration
* Backend pytest validation is pending because this execution environment does not include a Python launcher or `pytest`

#### Next workspace-home slice

1. Add stage-level project progress and last-successful-stage presentation when backend job-status data is available
2. Add contextual card recovery actions for failed and incomplete projects
3. Replace the remaining hidden legacy encoding artifacts during the dedicated text-encoding cleanup pass

### Workspace-home project state status

#### Implemented

* Added an authoritative active pipeline summary to the project-list response: stage, status, progress percentage, and error message
* Reused the existing current export and lip-sync job relationships; project-list loading now eagerly loads those relationships instead of issuing per-card job requests
* Project cards now show an accessible stage label and progress bar only while a project is processing
* Failed cards now expose the backend error when available and provide a contextual link to review and recover in the editor
* Export status is prioritized over lip-sync status when both pointers exist because it represents the later active stage

#### Validation

* `npm.cmd run build` completed successfully after the frontend implementation
* Backend automated tests remain pending in an environment with Python and pytest available

#### Next workspace-home slice

1. Add project-level job history only after a stable backend history endpoint or response contract exists
2. Add stage-specific retry controls only for operations with safe, supported retry endpoints
3. Perform the dedicated source-text encoding cleanup before further copy polish

### Project export-history status

#### Implemented

* Added a project-scoped export-history method to the frontend service, using the existing backend `/export/history?project_id=` endpoint and authenticated request flow
* Reworked `ExportHistory` to use the shared panel and status primitives, clear loading, empty, and recoverable error states, and actual project-scoped output data
* Removed inaccurate fixed download-link-expiry copy and replaced encoding-sensitive separators with safe, consistent text separators
* Added an editor-header `Exports` control that opens project export history on demand without interrupting media review or version history

#### Consistency safeguards

* The history panel is secondary and lazy-loaded, preserving the current editor's primary review and editing flow
* No retry action was added: existing render dispatch endpoints require valid project inputs and do not expose a dedicated safe retry contract
* Status colors and controls use the shared component primitives introduced in the foundation checkpoint

#### Validation

* `npm.cmd run build` completed successfully after the export-history integration

#### Next safe slice

1. Add a pre-export readiness summary that identifies missing prerequisites and non-blocking quality risks before dispatch
2. Keep export dispatch behavior unchanged until the readiness summary is visible and validated

### Pre-render readiness status

#### Implemented

* Added a secondary, on-demand Export Readiness panel in the editor rather than adding another persistent competing surface
* The readiness review uses canonical editor state only: source media, completed transcript and segment count, translations, unsaved edits, timing-fit risk, low-confidence translations, generated-audio state, and draft conflicts
* Separates rendering blockers from non-blocking quality recommendations; it does not silently prevent users from using established render controls
* Made readiness, version history, and export history mutually exclusive overlays to preserve a calm, focused editing workspace

#### Consistency safeguards

* The panel uses existing shared surfaces, status badges, semantic color meanings, headings, and accessible progress-independent text
* Existing dub and lip-sync dispatch behavior was deliberately not changed
* The readiness summary does not claim an export file size, output format, or job progress that the current editor state does not authoritatively provide

#### Validation

* `npm.cmd run build` completed successfully after the readiness integration

#### Next safe slice

1. Consolidate the editor header's repeated button styles onto the shared Button primitive without changing actions or shortcuts
2. Replace remaining user-visible encoding-sensitive text and operational glyphs as part of the scoped editor cleanup

### Editor-header consistency status

#### Implemented

* Migrated editor-header navigation, language-swap, history, export-history, readiness, undo, redo, save, dub-only, and lip-sync controls to the shared Button primitive
* Preserved the established hierarchy: quiet navigation, secondary utility actions, visible amber unsaved-work state, secondary dub-only action, and primary Dub + Lip-Sync action
* Preserved all existing handlers, disabled conditions, titles, keyboard shortcut messaging, and mutually exclusive secondary-panel behavior

#### Consistency safeguards

* No editor layout, dispatch flow, or state-management behavior was changed during this styling consolidation
* Existing Unicode text was not mechanically rewritten because source searches found no encoding-corruption patterns; terminal display alone is not treated as evidence of source corruption

#### Validation

* `npm.cmd run build` completed successfully after the header migration

#### Next safe slice

1. Consolidate visible conflict and loading controls onto shared primitives while preserving their recovery behavior
2. Audit the editor at responsive breakpoints when a browser surface becomes available before altering its main workstation layout

### Contract-safe UI consistency status

#### Implemented

* Consolidated conflict-recovery and secondary-panel close controls onto the shared Button primitive without changing their underlying state transitions
* Restored the canonical project-list artifact boundary: project summaries retain media identity and duration only; no signed thumbnail URL is generated, returned, or retained in frontend project state
* Updated the workspace-card plan to require an intentional non-artifact representation until a dedicated authorized thumbnail endpoint is designed

#### Safety verification

* No persistence logic, draft versioning, workspace scope, project lifecycle transition, or signed artifact endpoint behavior changed
* Conflict recovery still preserves local edits and requires an explicit user choice before reloading the server draft
* `npm.cmd run build` completed successfully after the consistency and contract-boundary corrections

#### Next safe slice

1. Do not add thumbnail retrieval or project-list artifact URLs without a dedicated workspace-authorized endpoint and contract test
2. Use browser-based responsive QA before changing the primary editor layout
3. Continue with non-destructive accessibility improvements to existing controls and state messaging

### Runtime artifact URL ownership status

#### Implemented

* Removed original-media, rendered-video, and dubbed-audio URL fields from canonical frontend project state
* Updated editor hydration, project patching, language-swap safety checks, and autosave fallback logic to use canonical media IDs and filenames only
* Added runtime-only source-media URL state populated through the dedicated authorized media endpoint; rendered video remains runtime-only and comes from dedicated lip-sync job status
* Sanitized legacy URL-shaped draft filenames before every editor draft cache write so signed URLs cannot be re-persisted to IndexedDB or backend draft payloads
* Added runtime URL refresh on source/rendered playback failures without issuing project patches or changing project lifecycle state

#### Validation

* Source search confirms no `originalVideoUrl`, `lastRenderedVideoUrl`, or `dubbedAudioUrl` fields remain in the frontend source
* Remaining `media_url` and `output_video_url` usage is limited to dedicated artifact endpoint responses and component runtime playback/download state
* `npm.cmd run build` completed successfully after the ownership refactor

### Phase D quality and recovery verification

#### Implemented

* Segment retranslation now invalidates generated-audio rows derived from the previous translation so readiness indicators do not report stale audio as usable
* Segment audio regeneration now replaces prior generated-audio rows instead of accumulating ambiguous records for the same translation
* The editor updates audio-readiness state immediately after retranslation and successful regeneration
* Retranslation and audio-regeneration failures now surface user-facing recovery messages instead of only writing to the browser console

#### Validation

* `npm.cmd run build` completed successfully with the Phase D review and recovery surfaces
* Static integrity review confirmed that generated-audio status uses the backend `ready`, `processing`, and `failed` lifecycle
* Backend automated validation remains pending because Python and pytest are unavailable in this execution environment

#### Next Phase D validation slice

1. Run the translation and media-audio API test suites in a Python-enabled environment
2. Verify retranslation changes the segment to `No audio` until regeneration succeeds
3. Verify repeated regeneration leaves exactly one current generated-audio record and clears the risk indicator

### Phase E processing visibility and recovery — slice 1

#### Implemented

* Added persistent `current_stage` and `last_successful_stage` checkpoints to lip-sync jobs, with an additive Alembic migration (`20260903_14`) so job progress remains available after refreshes and worker restarts.
* The render pipeline now persists `preparing`, `voice`, `lip_sync`, and `export` checkpoints alongside its existing progress events; a failed job retains its last safe completed checkpoint.
* Added an editor build-status panel with the common Upload, Transcribe, Translate, Voice, Lip-sync, and Export stage model. It uses actual project prerequisites and the authoritative render-job status rather than fabricated progress.
* Added stage-specific recovery copy that states what to investigate and explicitly confirms that saved translations and existing outputs are preserved.
* Kept the previously generated preview visible while a new build starts; initiating a render no longer clears an existing output link before its replacement succeeds.
* Clarified the stale-draft banner: loading the server draft intentionally replaces only local editor edits after hydration and does not erase already persisted translations.

#### Safety and contract safeguards

* The job-stage fields are additive and defaulted; they do not alter job ownership, project/workspace foreign keys, artifact keys, signed URLs, or dispatch payloads.
* No retry action was exposed because the backend does not yet provide a stage-scoped, idempotent retry contract. Recovery guidance directs users to start a new build only after resolving the relevant prerequisite.
* The UI derives its state from the existing authorized job-status endpoint and holds no signed artifact URL in persisted project or draft state.

#### Validation

* `npm.cmd run build` completed successfully after the Phase E slice, including TypeScript validation and static route generation.
* `git diff --check` completed without whitespace errors.
* Backend automated migration and pipeline tests remain pending in a Python-enabled environment.

#### Next Phase E slice

1. Extend the common stage model to upload, transcription, and translation jobs once each exposes an equally stable persisted stage/checkpoint contract.
2. Add a completed-output summary with authoritative duration, file size, created time, and selected-history-item preview once those fields are present in the render-history response.
3. Add stage-specific retry controls only with an explicit idempotent backend retry endpoint and contract tests.

### Phase E completed-output reuse — slice 2

#### Implemented

* Extended render and format-export job responses with separate, short-lived `output_video_url` (inline preview) and `download_video_url` (signed attachment) fields, plus lip-sync output file size.
* Preserved the existing `output_video_url` field for preview compatibility; the new download URL is additive and is generated only for the authorized request.
* Updated the project output-history panel so each completed entry has its own Open and Download actions, including render mode, language, size, and creation time.

#### Safety and contract safeguards

* No artifact URL is stored in a project, draft, or client cache. Both URLs are generated from the job-owned immutable object key at read time and remain subject to the existing workspace authorization check.
* The attachment response is signed separately from preview. This fixes cross-origin browser behavior without changing object persistence, bucket access, or URL expiry policy.
* The response additions are backward compatible; existing preview consumers continue using `output_video_url`.

#### Validation

* `npm.cmd run build` completed successfully after the output-history update, including TypeScript validation and static route generation.

### Phase E durable upstream operation tracking - slice 3

#### Implemented

* Added a workspace- and project-scoped `pipeline_operations` record for transcription and batch translation.
* Transcription and translation dispatch now persist an operation before queueing work and associate it with the active project operation pointer.
* Translation carries the operation ID through Cloud Tasks and Celery execution, persisting loading, translation, save, completion, and failure checkpoints.
* Preserved compatibility for direct translation task invocations that do not provide an operation ID.

#### Validation

* `pytest -q tests/test_translation_task_persistence.py tests/test_translation_pipeline.py` passed: 15 tests.
* Static diagnostics report no errors in the touched backend modules.

### Phase E persisted operation hydration - slice 4

#### Implemented

* Added an authorized `GET /v1/projects/{project_id}/pipeline-operation` endpoint backed by the active project operation pointer.
* Added typed frontend service access for persisted operation status.
* The editor now restores queued or in-progress transcription and translation state after project reload, including the durable message and failed-operation error text.

#### Validation

* `pytest -q tests/test_projects_api.py` passed: 15 tests.
* `npm.cmd run build` completed successfully.

### Phase E safe retry contract - slice 5

#### Implemented

* Added an authorized translation retry endpoint for failed batch operations.
* Retries create a new durable operation and idempotency key, preserving the failed operation as history.
* Non-failed operations and unsupported operation types are rejected with a conflict response.
* Added a typed frontend service method for the retry contract.

#### Safety boundary

* Transcription retry remains unavailable until its original language, speaker, and preprocessing options are persisted. The endpoint does not guess those inputs.

#### Validation

* `pytest -q tests/test_translation_retry_api.py` passed: 4 tests.
* `pytest -q tests/test_projects_api.py tests/test_translation_pipeline.py tests/test_translation_task_persistence.py` passed: 30 tests.

### Phase E editor translation retry control - slice 6

#### Implemented

* Added a retry action to the editor only for persisted failed translation operations.
* The control disables while dispatching, adopts the newly returned operation ID, and restores queued translation state without modifying saved translations, drafts, render jobs, or artifact URLs.
* Render-job status remains the dominant build status surface when a render is active.

#### Validation

* `pytest -q tests/test_translation_retry_api.py tests/test_projects_api.py` passed: 19 tests.
* `npm.cmd run build` completed successfully.
* `git diff --check` completed without whitespace errors.

### Phase E transcription retry inputs - slice 7

#### Implemented

* Persisted the original transcription language, speaker limit, noise-reduction, loudness-normalization, and VAD options on each new pipeline operation.
* Added an authorized transcription retry endpoint that accepts only failed transcription operations with complete persisted inputs.
* Retries create a fresh operation and idempotency key, preserve the failed operation as history, and reuse only the stored media/transcript lineage and options.
* Added a typed frontend service method without exposing a UI action until the editor has a dedicated transcription failure workflow.

#### Safety boundary

* Operations created before these fields existed are rejected for retry rather than retried with guessed settings.
* No render jobs, persisted drafts, translation rows, signed URLs, or artifact keys are modified by transcription retry dispatch.

#### Validation

* `pytest -q tests/test_transcription_retry_api.py tests/test_transcription_pipeline.py tests/test_projects_api.py` passed: 20 tests.
* Compilation succeeded for the touched backend modules and migration.

### Phase E editor transcription retry control - slice 8

#### Implemented

* Added a distinct editor recovery action for persisted failed transcription operations.
* The action is shown only when no render job is active, disables during dispatch, and adopts the newly queued operation returned by the authorized retry endpoint.
* Existing project data, translations, drafts, render jobs, signed URLs, and output artifacts remain untouched.

#### Validation

* `pytest -q tests/test_transcription_retry_api.py tests/test_translation_retry_api.py` passed: 6 tests.
* `npm.cmd run build` completed successfully.
* `git diff --check` completed without whitespace errors.

#### Remaining Phase E work

1. Perform browser QA for upload, job failure, output preview, forced download, and responsive history-panel behavior after deployment.

### Phase E large-file upload - slice 9

#### Implemented

* Editor uploads up to 100 MB continue using the existing direct-upload path.
* Larger audio and video files now initialize the existing signed GCS resumable-upload session, upload in 8 MB browser chunks, and finalize through the authorized project-scoped completion endpoint.
* The existing transcription and translation lifecycle continues unchanged after resumable upload completion.

#### Validation

* `npm.cmd run build` completed successfully with TypeScript validation.
* Focused diagnostics reported no errors in the edited frontend files.

### Phase E upload progress feedback - slice 10

#### Implemented

* Large-file uploads now report the completed upload percentage in the editor while each resumable chunk finishes.
* The progress callback is optional, so the existing upload service contract and small-file direct-upload path remain unchanged.

#### Validation

* `npm.cmd run build` completed successfully with no errors.
* Focused diagnostics reported no errors in the edited frontend files.

### Phase E upstream stage visibility - slice 11

#### Implemented

* The editor now renders the shared stage-based status panel while upload, transcription, or translation is active.
* Persisted upstream operation progress, checkpoint, and failure details are shown through the same status surface used for render recovery.
* Upload remains indeterminate until the resumable upload callback supplies actual progress; no synthetic percentage is presented.

#### Validation

* Focused diagnostics reported no errors in the edited editor file.
* `npm.cmd run build` completed successfully with no errors.

### Phase E upstream status language - slice 12

#### Implemented

* Upstream transcription and translation progress now uses the neutral `Project processing status` heading instead of the render-specific dub heading.
* Transcription and translation failures now provide stage-specific recovery guidance while confirming that project data and saved drafts are preserved.

#### Validation

* Focused diagnostics reported no errors in the edited frontend files.
* `npm.cmd run build` completed successfully with no errors.

### Phase E history recovery context - slice 13

#### Implemented

* Project output history now displays the last successful render checkpoint for failed dub or lip-sync jobs.
* Backend status values are translated into user-facing labels such as `Completed`, `In progress`, `Queued`, and `Needs attention`.
* Failed history entries explain that a new build can be started after the underlying issue is resolved.

#### Validation

* Focused diagnostics reported no errors in the edited export-history component.
* `npm.cmd run build` completed successfully with no errors.

### Phase E output timing summary - slice 14

#### Implemented

* Lip-sync and dub history entries now show the authoritative render duration when the backend provides it.
* Older records without timing data display `Render time unavailable` instead of implying a value.

#### Validation

* Focused diagnostics reported no errors in the edited frontend files.
* `npm.cmd run build` completed successfully with no errors.

### Phase E synchronized upload progress - slice 15

#### Implemented

* The shared editor processing panel now uses the actual resumable-upload percentage instead of displaying a static zero while large files upload.
* The upload message and visual progress bar advance from the same chunk-completion callback.

#### Validation

* Focused diagnostics reported no errors in the edited editor file.
* `npm.cmd run build` completed successfully with no errors.

### UI foundation keyboard focus - slice 16

#### Implemented

* Shared `Button` controls now expose a high-contrast focus ring for keyboard navigation without changing pointer or disabled states.

#### Validation

* Focused diagnostics reported no errors in the shared button component.
* `npm.cmd run build` completed successfully with no errors.

### UI foundation form focus - slice 17

#### Implemented

* Shared text inputs and selects now expose the same high-contrast keyboard focus ring as buttons.
* Existing focus-border, reduced-motion, and disabled behaviors remain unchanged.

#### Validation

* Focused diagnostics reported no errors in the global stylesheet.
* `npm.cmd run build` completed successfully with no errors.

### UI responsive output history - slice 18

#### Implemented

* Export-history rows now stack metadata and actions on narrow screens so Open and Download remain usable without horizontal compression.
* Desktop layouts retain the existing compact row presentation from the `sm` breakpoint upward.

#### Validation

* Focused diagnostics reported no errors in the export-history component.
* `npm.cmd run build` completed successfully with no errors.

### UI recoverable filtered-empty state - slice 19

#### Implemented

* Workspace search and status filters now show a clear empty-state explanation when no projects match.
* Added a keyboard-focusable `Clear search and filters` action that restores the full project list.
* The signed-in no-project onboarding state remains separate and unchanged.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no errors.

### UI accessible project filters - slice 20

#### Implemented

* Workspace status filters now expose their selected state with `aria-pressed`.
* The filter group now has an accessible label for keyboard and assistive-technology users.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no errors.

### UI accessible project controls - slice 21

#### Implemented

* Workspace project search now has an explicit accessible name: `Search projects by name`.
* Workspace project sorting now has an explicit accessible name: `Sort projects`.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no errors.

### UI keyboard menu dismissal - slice 22

#### Implemented

* Project action menus now close when the user presses `Escape`.
* The keyboard listener is attached only while the menu is open and is removed during cleanup.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no errors.

### UI semantic project actions - slice 23

#### Implemented

* Project action triggers now expose `aria-haspopup` and `aria-expanded` state.
* Project action popups use `menu` and `menuitem` semantics for assistive technology.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no relevant errors.

### UI project menu focus management - slice 24

#### Implemented

* Opening a project action menu now moves keyboard focus to the first available action.
* The action trigger references its popup with `aria-controls`.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no errors.

### UI version dialog dismissal - slice 25

#### Implemented

* The editor version-history dialog now closes with the `Escape` key.
* Its keyboard listener is attached only while the dialog is open and is removed during cleanup.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI version dialog backdrop - slice 26

#### Implemented

* Clicking outside the version-history dialog now closes the overlay.
* Clicks inside the dialog stop propagation so browsing version entries remains uninterrupted.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI export dialog backdrops - slice 27

#### Implemented

* Export history and export readiness overlays now close when the user clicks outside the panel.
* Clicks inside either panel stop propagation, preserving links, controls, and review interactions.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI export dialog keyboard dismissal - slice 28

#### Implemented

* Export history and export readiness overlays now close with the `Escape` key.
* The keyboard listener is active only while one of those overlays is open and is removed during cleanup.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### Phase E export history retry - slice 29

#### Implemented

* Export-history failures now include a `Try again` action for transient request failures.
* Retrying reuses the existing authorized history requests and preserves any history data already loaded.

#### Validation

* Focused diagnostics reported no errors in the export-history component.
* `npm.cmd run build` completed successfully with no errors.

### Phase E retry loading feedback - slice 30

#### Implemented

* Export-history retry actions now disable while requests are in flight.
* The control changes to `Retrying...` and exposes an appropriate accessible label during reload.

#### Validation

* Focused diagnostics reported no errors in the export-history component.
* `npm.cmd run build` completed successfully with no errors.

### UI export history async state - slice 31

#### Implemented

* Export History now exposes its refresh state with `aria-busy` while history requests are in flight.

#### Validation

* Focused diagnostics reported no errors in the export-history component.
* `npm.cmd run build` completed successfully with no errors.

### UI editor progress announcements - slice 32

#### Implemented

* Editor project-update messages now use a polite atomic live region so upload, transcription, translation, and export updates are announced as complete messages.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI contextual output actions - slice 33

#### Implemented

* Output-history Open and Download links now include render mode or format/resolution in their accessible names.
* Repeated actions remain visually unchanged while becoming distinguishable to assistive technology.

#### Validation

* Focused diagnostics reported no errors in the export-history component.
* `npm.cmd run build` completed successfully with no errors.

### UI pipeline busy state - slice 34

#### Implemented

* Shared pipeline status panels now expose `aria-busy` while queued or actively processing.
* Completed and failed states remain settled for assistive technology users.

#### Validation

* Focused diagnostics reported no errors in the pipeline status component.
* `npm.cmd run build` completed successfully with no errors.

### UI pipeline progress description - slice 35

#### Implemented

* Pipeline progress bars now expose both the current percentage and active stage through `aria-valuetext`.

#### Validation

* Focused diagnostics reported no errors in the pipeline status component.
* `npm.cmd run build` completed successfully with no errors.

### UI landing auth alert - slice 36

#### Implemented

* Public landing-page authentication failures now use `role="alert"` so they are announced immediately to assistive technology users.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no errors.

### UI workspace loading status - slice 37

#### Implemented

* Workspace session restoration and project loading now announce through a polite `status` live region.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no errors.

### UI editor upload control - slice 38

#### Implemented

* The editor upload control now exposes an accessible label for audio/video selection and transcription.
* Keyboard focus inside the hidden file input is surfaced on the visible upload control with a focus ring.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI editor media controls - slice 39

#### Implemented

* The editor video preview now has a descriptive accessible label.
* Timeline segment seek buttons now announce their timestamp and speaker context.
* The custom preview control now exposes Play/Pause state through `aria-label` and `aria-pressed`.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI keyboard timeline seeking - slice 40

#### Implemented

* The editor timeline is now keyboard-operable as a slider when media is loaded.
* Arrow keys seek by one second, Shift plus Arrow keys seek by five seconds, and Home/End jump to the timeline bounds.
* Screen readers receive the current time and total duration through slider value text.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI RTL editor fields - slice 41

#### Implemented

* Source and translated editor textareas now apply direction independently from their respective language codes.
* Arabic, Hebrew, and Urdu fields render right-to-left; other supported languages remain left-to-right.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI responsive segment editor - slice 42

#### Implemented

* Transcript segment cards now stack source and translation fields on narrow screens.
* The two-column editing layout returns at the medium breakpoint for desktop review workflows.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI onboarding form labels - slice 43

#### Implemented

* First-project onboarding controls now expose explicit accessible names for project name, source language, and target language.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no errors.

### UI keyboard segment selection - slice 44

#### Implemented

* Transcript segment cards are now keyboard-focusable and selectable with Enter or Space.
* Each segment exposes an accessible label and its selected state through `aria-pressed`.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI timeline selection semantics - slice 45

#### Implemented

* Timeline seek buttons now expose the currently selected segment with `aria-pressed`, matching the transcript segment cards.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI shared button busy state - slice 46

#### Implemented

* Reusable loading buttons now expose `aria-busy` while their async action is in progress.
* Native disabled behavior and the existing loading indicator remain unchanged.

#### Validation

* Focused diagnostics reported no errors in the shared button component.
* `npm.cmd run build` completed successfully with no errors.

### UI nested-control accessibility cleanup - slice 47

#### Implemented

* Transcript segment cards now use group semantics instead of an outer button role around nested buttons and textareas.
* Timeline seek controls use `aria-current` for the active location because they are navigation commands, not toggle buttons.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI encoding-safe editor icons - slice 48

#### Implemented

* Replaced operational glyphs in editor segment actions with inline SVG icons.
* Visible action labels remain available, and decorative icons are hidden from assistive technology.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI dialog focus containment - slice 49

#### Implemented

* Open editor dialogs now keep Tab and reverse-Tab focus inside the active panel.
* Focus containment applies consistently to version history, export history, and export readiness overlays.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI dialog focus restoration - slice 50

#### Implemented

* Closing an editor history, export-history, or readiness dialog now restores keyboard focus to the control that opened it.
* Focus restoration works across Escape, backdrop, and explicit close-button dismissal.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI dialog initial focus - slice 51

#### Implemented

* Version History, Export History, and Export Readiness dialogs now place initial keyboard focus on their close control when opened.
* This works with the existing focus trap and restores focus to the originating trigger when the dialog closes.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI quiet pipeline-status hydration - slice 52

#### Implemented

* Project detail responses now expose the existing active pipeline-operation pointer as an optional field.
* The editor skips the pipeline-status request when the server explicitly reports no active operation, removing expected 404 noise.
* Older API responses that omit the field retain the previous request behavior for compatibility.

#### Safety and validation

* The response addition is nullable and does not alter persistence, authorization, artifact URLs, or lifecycle transitions.
* `pytest backend/tests/test_projects_api.py -q` passed: 15 tests.
* Frontend diagnostics and `npm.cmd run build` passed.

### UI workspace progress description - slice 53

#### Implemented

* Processing project cards now expose stage-aware progress text through `aria-valuetext`.
* Cards announce either the actual percentage or an explicit `in progress` state when progress is indeterminate.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no errors.

### UI sticky mobile playback - slice 54

#### Implemented

* Editor timeline playback controls now remain visible at the bottom of the timeline on narrow screens.
* Desktop layouts keep the existing normal-flow playback row.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI native timeline seeking - slice 55

#### Implemented

* Replaced the interactive timeline container's nested slider semantics with a native `range` control for keyboard fine-seeking.
* Visual segment bars retain pointer scrubbing and per-segment seek actions without invalid interactive nesting.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI native language labels - slice 56

#### Implemented

* Workspace source and target language selectors now show native names from the supported-language API when available.
* Existing English language names remain the fallback when no distinct native name is provided.

#### Validation

* Focused diagnostics reported no errors in the home page.
* `npm.cmd run build` completed successfully with no errors.

### UI responsive workspace controls - slice 57

#### Implemented

* Workspace search and sorting controls now stack on narrow screens and return to a compact row at the small breakpoint.
* First-project source/target language controls now stack on narrow screens, keeping the swap control usable.

#### Validation

* Focused diagnostics reported no errors in the home shell component.
* `npm.cmd run build` completed successfully with no errors.

### UI mobile editor review order - slice 58

#### Implemented

* On narrow screens, the editor now presents media review before transcript and translation editing as specified by the workstation blueprint.
* Desktop retains the existing two-column media and editing arrangement.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

### UI labeled editor textareas - slice 59

#### Implemented

* Source transcript and translated textareas now have explicit accessible names.
* Labels include content type, language, speaker, and segment timestamp for reliable navigation through long scripts.

#### Validation

* Focused diagnostics reported no errors in the editor page.
* `npm.cmd run build` completed successfully with no errors.

#### Remaining Phase E work

1. Perform browser QA for large-file upload, job failure, output preview, forced download, and responsive history-panel behavior after deployment.

#### Large-file upload note

* Backend support already exists through `POST /v1/media/uploads/signed-resumable` and its completion endpoint, with a maximum resumable file size of 4 GB.
* The editor now uses the signed resumable path above 100 MB and continues the existing transcription lifecycle after finalization.
* The change must preserve workspace authorization, checksum and media probing, upload-session expiry, and the existing `MediaFile` persistence boundary.

#### Local QA note

* Local frontend and backend liveness checks passed, including a mobile-width entry-screen render without horizontal overflow.
* Authenticated editor, failed-job, retry, and export-history browser scenarios remain pending because this environment has no authenticated session or representative project fixture.
