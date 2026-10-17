# AI Influencer WebUI — Final UI Polish and Reliability Plan

**Prepared:** 17 October 2026  
**Implementation baseline:** `/data/data_ssd/pigni/ai-influencer/backend-v6`  
**Purpose:** implementation plan for a coding agent  
**Scope:** final UI cleanup, drawer/menu redesign, Images Review, LoRA workspace persistence, dataset-classification reliability, global job monitoring, and density reduction

## 1. Desired Outcome

Refine the current v6 interface into a compact, professional operator workspace without removing any existing feature.

The application should expose the next useful action immediately, while detailed configuration should open through a small number of clearly named controls such as **Settings**, **Generator**, **Details**, or **More**. Switching routes must not destroy the operator's working context. Long-running work must be visible globally, with progress and ETA.

This is an incremental refinement of the current implementation. Do not rebuild the application from scratch and do not change the visual identity unnecessarily.

## 2. Audit Summary

The current version is substantially better than the earlier three-column interface, but several implementation and interaction problems remain.

### Confirmed high-severity issues

1. **Drawers are visually transparent.**
   - The shared drawer uses `background: var(--surface-1)` and borders such as `var(--border-1)`.
   - The referenced CSS custom properties are currently undefined.
   - Browser-computed values for `--surface-1`, `--surface-2`, `--border-1`, and status tokens are empty.
   - Result: page cards, images, controls, and text remain visible through the drawer, making Video Generator, Dataset Image Details, Images Generator, and LoRA Guide difficult to read.

2. **LoRA workspace context is lost when switching routes.**
   - `LoraPlayground.tsx` initializes `characterId` as an empty string and unconditionally selects `chars[0]` after loading.
   - `stage` also initializes to `0` on every mount.
   - Reproduction: select Akula and the LoRA Dataset stage, navigate to another route, return to LoRA; the page returns to Nikita and the Character stage.

3. **`nenne_02` classification is stale and internally inconsistent.**
   - Observed database state: `status=classifying`, `total=83`, `imported=83`, `classified=26`, with no stored error.
   - Actual media rows: 70 images — 26 ready and 44 pending.
   - The source's last update predates the current API container, so the in-process task died while the source remained `classifying`.
   - The Jobs page reports zero active jobs because dataset classification currently runs through FastAPI `BackgroundTasks` and is not represented as a durable execution job.
   - `classify_source()` writes `source.classified = index` for only the current pending batch, which can reset rather than preserve cumulative progress after a retry.

4. **Images Review requires page scrolling to reach essential controls.**
   - The image consumes most of the viewport.
   - Approve, Reject, rating, content classification, and the counter are below the image.
   - The filmstrip is large, always open, and followed by an unrelated “Load more” control.
   - A reviewer cannot consistently see the image and decision controls at the same time in the 812 × 726 in-app viewport.

5. **Several controls wrap text or become overly tall.**
   - Long action names and tab labels wrap inside buttons.
   - Chat Settings uses long tab names and then repeats the same title inside an accordion.
   - LoRA character cards contain long policy messages.
   - The absence of a shared non-wrapping action style makes the interface look inconsistent.

### General density problems

- The Home page opens the entire System and Infrastructure section by default, pushing product workflow information below the fold.
- LoRA Character displays profile generation, model selection, upload, edit, identity-set generation, and Danger Zone together.
- LoRA also retains a long training-job history that belongs primarily on Jobs.
- Dataset uses a full-width New Source button followed by a mostly empty Sources header area.
- Jobs displays too many secondary metrics before the job list.
- Too many unrelated disclosure controls appear at the same visual level.
- Some pages use both tabs and accordions for the same navigation concept.

## 3. Product Rules for This Pass

1. Preserve every current capability.
2. Move complexity; do not delete it.
3. Use no more than one primary action per visual section.
4. Prefer a **Settings** button that opens a well-organized panel over several independent accordions scattered through the page.
5. A disclosure should reveal content, not duplicate a navigation system already represented by tabs.
6. A drawer must be opaque, readable, independently scrollable, keyboard accessible, and have one close mechanism.
7. A standard action button must remain on one line.
8. Multiline text is allowed only in content tiles intentionally designed for it, never in routine toolbar actions.
9. Route changes must preserve in-progress workspace context.
10. Long-running work must survive API restarts and must appear in the global job monitor.

## 4. Delivery Phases

Implement in the following order. Each phase should be independently testable and committed separately.

### Phase 0 — Baseline and regression inventory

1. Capture current screenshots for Home, Chat, Images Grid, Images Review, Video, Dataset, LoRA, and Jobs at:
   - 812 × 726
   - 1024 × 768
   - 1280 × 800
   - 1440 × 900
2. Capture every drawer in its open state:
   - header menu;
   - Chat Settings;
   - Images Generator;
   - Video Generator;
   - Dataset Image Details;
   - LoRA Guide;
   - New Source modal.
3. Record an action inventory so no function is lost during compaction.
4. Add a regression test reproducing LoRA route-state loss before changing its implementation.
5. Add a backend test fixture reproducing a dataset source marked `classifying` with no active process/job.

**Exit condition:** screenshots and failing regression tests exist.

### Phase 1 — Repair design tokens, buttons, and overlay foundations

Fix the shared primitives before touching page-specific layouts.

#### 1.1 Define every shared token

Add stable values at `:root` or `.playground` in `webui/src/main.css`. At minimum define:

```css
--surface-0: #0b101b;
--surface-1: #101a2a;
--surface-2: #142238;
--surface-3: #1b293e;
--border-1: #243149;
--border-2: #30405a;
--text-1: #e3e9f4;
--text-2: #b7c6dc;
--text-3: #8fa4bf;
--st-ok-bg: #173f36;
--st-ok-fg: #9be5cf;
--st-busy-bg: #3d3518;
--st-busy-fg: #f0d57a;
--st-bad-bg: #4a202b;
--st-bad-fg: #f5a8b6;
--st-neutral-bg: #29364b;
--st-neutral-fg: #c7d5ea;
```

The coding agent may tune values to the existing palette, but no referenced token may remain undefined. Add a small test that reads the expected custom properties or render-test classes that use them.

#### 1.2 Standardize action buttons

Create explicit styles instead of relying on unrestricted global button wrapping:

```css
.button,
button:not(.multiline-card) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  white-space: nowrap;
  line-height: 1.1;
  min-height: 34px;
}
```

Implementation details:

- Do not apply `white-space: nowrap` to character cards, option cards, or other intentional multiline content tiles; give those an explicit `.multiline-card` or semantic class.
- Prevent toolbar buttons from shrinking their labels: `flex: 0 0 auto`.
- Let the toolbar container wrap whole controls instead of wrapping words within a control.
- If a toolbar still does not fit, move tertiary actions into `OverflowMenu`.
- Use icon-only buttons only for universally understood actions such as Close or More, and give each an accessible name and tooltip.
- Keep a compact control height of 32–36 px.
- Truncate long character policy/status text with ellipsis; show the complete message in a tooltip or details panel.

#### 1.3 Repair `InspectorDrawer`

Update `webui/src/components/ui/InspectorDrawer.tsx` and its CSS:

- Use a fully opaque surface.
- Use a backdrop with approximately 60–70% darkness and optional light blur.
- Drawer width on desktop: 400–440 px, with an optional `size="wide"` variant of 520–600 px for media/configuration-heavy panels.
- Below 640 px, use a full-width bottom sheet or full-width side sheet.
- Use a sticky header with one title and one Close button.
- Use one scrollable body.
- Add an optional sticky footer slot for the primary action.
- Lock background page scrolling while open.
- Preserve focus trap, Escape close, backdrop close, and focus restoration.
- Add `aria-labelledby` rather than relying only on `aria-label` where possible.
- Ensure the drawer is above the application header and every sticky toolbar.
- Never render a second “Hide guide” or duplicate heading inside drawer content.

Suggested API:

```tsx
<InspectorDrawer
  open={open}
  title="Character settings"
  summary="Nikita · Real"
  size="default"
  footer={<button className="primary">Save</button>}
  onClose={close}
>
  ...
</InspectorDrawer>
```

#### 1.4 Consolidate disclosure behavior

- Only one full drawer should be open at a time.
- Opening a new drawer closes the previous drawer.
- Use tabs inside a settings drawer only for genuinely separate categories.
- Do not repeat the selected tab title as an accordion immediately below it.
- Use accordions only for advanced or diagnostic content inside the selected category.

**Exit condition:** every drawer has an opaque surface and readable content; no routine action button wraps at 812 px.

### Phase 2 — Redesign drawer and menu content

#### 2.1 Chat Settings

Current problem: long tabs such as “Character settings (version, style, PPV, timing)” wrap, and the same label is repeated in an expanded details section.

Replace them with short tabs:

- Character
- Media
- Memory
- Timing

Suggested grouping:

- **Character:** personality/version controls and link to full character editor.
- **Media:** photo style, checkpoint, PPV defaults.
- **Memory:** fan-specific memory.
- **Timing:** reply delay, activity hours, realism simulation.

Remove the duplicate accordion title. The selected tab panel should begin directly with its fields. Keep advanced realism parameters in one Advanced section inside Timing.

#### 2.2 Images Generator

Use a wide drawer because this is a production form.

Default visible controls:

- prompt;
- creative direction;
- selected preset;
- selected LoRA chips;
- pose summary;
- image count;
- concise recipe summary.

Move the following under **Settings** or **Advanced** inside the drawer:

- checkpoint/model family;
- LoRA catalog and detailed weights;
- CLIP weights;
- seed;
- classifier toggle;
- character-consistency controls;
- Pose Library.

Do not use multiple adjacent accordions named Details, Manage LoRAs, Character consistency, and Pose Library at the same hierarchy level. Use two clear sections:

1. Generation settings
2. Advanced settings

Keep selected LoRAs visible as removable chips. Open the searchable catalog through “Manage LoRAs.”

#### 2.3 Video Generator

- Keep Mode, Start image, Motion/scene, and motion presets visible.
- Rename the current `Details` disclosure to **Video settings**.
- Put resolution, frames, model, steps, seed, and expert parameters there.
- Keep the output summary visible in one compact line.
- Put Generate video in the sticky drawer footer.
- Ensure the selected start image is clearly a drawer asset, not underlying page content.

#### 2.4 Dataset Image Details

- Keep the media preview or thumbnail at the top.
- Show caption and key state immediately.
- Place structured fields in a compact two-column definition layout when width allows.
- Use a collapsed Technical metadata section for dimensions, hashes, source path, and internal IDs.
- Put Extract pose in the footer as a secondary action.
- Put Delete in an overflow Danger section, not beside the routine action.

#### 2.5 LoRA Guide

- Remove the inner “Hide guide” button; the shared drawer already has Close.
- Do not repeat “LoRA tab guide” as both drawer header and body heading.
- Use step-linked help: when the operator is on Character, open the Character help section first.
- Reduce body type to the standard 13–14 px and keep line length under approximately 70 characters.
- Use compact bullet lists and headings, not one uninterrupted wall of text.

#### 2.6 Header account menu

The current header menu is acceptable but should receive small refinements:

- close on route selection, Escape, and outside click;
- keep the current route visibly selected;
- separate navigation from account actions;
- avoid showing the full route list in the menu on widths where the main navigation is already visible, unless the user intentionally opened it for account actions.

**Exit condition:** drawers use a consistent structure and no drawer duplicates its own title or navigation.

### Phase 3 — Rebuild Images → Review as a viewport workspace

This is the most important UI-specific phase.

#### 3.1 Layout objective

At 812 × 726, the following must be visible simultaneously:

- selected image;
- previous/next controls;
- rating;
- Approve and Reject;
- content label;
- current position.

The browser page must not need vertical scrolling for the core review decision.

#### 3.2 Proposed structure

```text
┌ Header ───────────────────────────────────────────────┐
│ Nikita · Review       [Grid] [Review] [Trash] [Info] │
├───────────────────────────────────────────────────────┤
│                                                       │
│                selected image / overlay               │
│                                                       │
├ sticky decision bar ──────────────────────────────────┤
│ ★★★★★   [Approve A] [Reject R] [Suggestive ▾]  1/60 │
├ optional compact filmstrip ───────────────────────────┤
│ thumbnails…                                    [hide] │
└───────────────────────────────────────────────────────┘
```

#### 3.3 Implementation requirements

- Make Review its own flex/grid workspace with `height: calc(100dvh - var(--header-height))`.
- The image region uses `min-height: 0` and scales the image with `object-fit: contain`.
- Reserve height for the decision bar before calculating image maximum height.
- Keep the decision bar sticky or fixed within the review workspace.
- Put metadata and captions behind an **Info** drawer.
- Put keyboard help behind a help icon/tooltip; do not consume permanent layout space.
- Keep shortcuts A, R, arrow keys, and rating shortcuts working even when focus is not inside a form control.
- Use equal visual weight and width for Approve and Reject.
- Show current state in the action button without changing its label width.
- Make filmstrip one compact row with 64–72 px-wide thumbnails.
- Default filmstrip to collapsed on viewports below 900 px; remember the user's preference in session storage.
- Preload adjacent images and virtualize or window the filmstrip.
- Remove the explicit “Load more” button from the main review decision area. Load the next cursor page automatically as the reviewer approaches the end, while retaining an error/retry state.
- Preserve the reviewed image by ID when switching between Grid and Review.
- Preserve review index/image when switching routes and returning to Images during the same session.
- Hide character/filter selection panels in Review. Use one compact context control in the header if character switching is still necessary.

#### 3.4 Review failure states

- If the full image cannot load, show a bounded error card with Retry and Skip.
- Never collapse the decision bar because the image failed.
- Disable actions only while the current mutation is pending, not while unrelated thumbnails load.
- Optimistically advance after Approve/Reject, but roll back state and remain on the same image if the request fails.

#### 3.5 Tests

- All core controls visible at 812 × 726 without document scroll.
- Keyboard navigation and A/R shortcuts.
- Filmstrip preference persistence.
- Selected image persistence after route switch.
- Cursor prefetch near the end.
- Failed mutation rollback.

Primary files:

- `webui/src/components/ImagePlayground.tsx`
- `webui/src/components/ui/ReviewStage.tsx`
- `webui/src/main.css`
- `webui/src/test/reachability.test.tsx`
- `webui/src/test/ui.test.tsx`

**Exit condition:** an operator can review a sequence without scrolling the document or reopening controls.

### Phase 4 — Persist and compact the LoRA workspace

#### 4.1 Persist operator context

Create a versioned hook or context, for example:

`webui/src/hooks/useLoraWorkspaceState.ts`

Persist at least:

```ts
interface LoraWorkspaceStateV1 {
  characterId: string;
  stage: "character" | "dataset" | "training";
  datasetId?: string;
  expandedIdentityRunId?: string;
  expandedLoraId?: string;
  scrollTop: number;
  guideOpen: boolean;
  updatedAt: number;
}
```

Use a React context above the route so state survives normal route switching. Mirror the safe parts to `sessionStorage` so state also survives a reload in the same browser session.

Selection priority on mount:

1. valid URL/query selection, if supplied;
2. valid saved session selection;
3. first available character.

Do not unconditionally call `setCharacterId(chars[0].id)` after character loading. Validate the saved character against the returned list first.

Additional requirements:

- Restore stage only after character data is loaded.
- Restore the relevant dataset only if it still exists for that character.
- Restore scroll position after the selected stage has rendered.
- Persist opened subview IDs, but do not reopen transient confirmation dialogs.
- Preserve unsaved text/number form drafts in route-level React state. Session persistence is optional for drafts, but normal tab switching must not clear them.
- Clear or migrate versioned storage safely if the state schema changes.
- If a selected character is deleted, fall back gracefully and clear the invalid saved ID.

#### 4.2 Compact the Character stage

The Character stage should become a summary-first workspace.

Default compact card:

- 64–80 px profile image;
- character name and style;
- profile anchor status;
- identity-set status, for example `0 accepted`, `Ready`, or `Needs review`;
- current model summary;
- primary next action;
- buttons: **Settings**, **Change image**, and **More**.

Move the following into **Character settings** drawer:

- profile-picture model;
- generation prompt;
- upload photo;
- duplicate/variation;
- Qwen-Edit instruction and action;
- advanced profile-generation controls.

Keep **Generate identity set** visible as the primary next action when no run exists. Once candidates exist, change the primary action to **Review identity set**.

Move Delete character into `More → Danger zone`. Keep the full warning and confirmation.

Do not place the full Identity Set interface directly below every profile control. Use a compact status card that opens a dedicated full-width review subview.

#### 4.3 Compact Dataset and Training stages

- Dataset stage should show selected dataset, coverage summary, selected/target count, progress, and the next action.
- Detailed dataset generation/curation opens a dedicated subview or Settings drawer.
- Training stage should show configuration summary, active LoRA, current active job, and up to three recent jobs.
- Replace the long embedded training history with **View all jobs** linking to Jobs filtered by character and type.
- Keep raw paths, logs, and technical traces inside Technical details only.

#### 4.4 Stepper behavior

- Keep the three current top-level stages unless a separate Identity stage is introduced deliberately.
- Each step button must be one line.
- Use short labels and a compact count/status badge.
- Only the selected stage body should be mounted or visible.
- Changing stage updates persisted state immediately.

#### 4.5 Tests

1. Select Akula, Dataset stage, and a dataset.
2. Navigate to Images.
3. Return to LoRA.
4. Verify Akula, Dataset stage, selected dataset, and approximate scroll/subview position are restored.
5. Reload and verify the session-safe state is restored.
6. Delete or remove the selected fixture and verify fallback without a crash.

Primary files:

- `webui/src/components/LoraPlayground.tsx`
- `webui/src/App.tsx`
- new `webui/src/hooks/useLoraWorkspaceState.ts`
- `webui/src/main.css`
- `webui/src/test/lora-jobs.test.tsx`
- `webui/src/test/shell.test.tsx`

**Exit condition:** switching routes never sends the operator back to the first character or first stage.

### Phase 5 — Make dataset classification durable and repair `nenne_02`

This phase is a backend reliability change required by the UI. Do not merely change the displayed label.

#### 5.1 Move classification into the durable job system

Replace FastAPI in-process `BackgroundTasks` classification with the existing execution-job/worker infrastructure.

The classify endpoint should:

1. validate the source;
2. check for an existing queued/running `dataset_classify` job for that source;
3. create one idempotent job if none exists;
4. enqueue it for the worker;
5. return the job ID and current job state.

Suggested response:

```json
{
  "job_id": "...",
  "started": true,
  "state": "queued"
}
```

The worker must update:

- heartbeat;
- `progress.current`;
- `progress.total`;
- `progress.unit = "images"`;
- current filename or safe short identifier where useful;
- final ready, failed, and blocked counts.

Classification must appear in Jobs and the new global job tray.

#### 5.2 Repair source counters

Use actual persisted `DatasetImage` rows as the source of truth.

- Classification denominator: count of image-kind rows eligible for classification, not stale `source.imported`.
- `source.imported` should be reconciled to persisted rows or clearly renamed if it means attempted imports.
- Keep separate counters for attempted, imported, duplicate/skipped, ready, pending, failed, and blocked.
- Do not present `70 images` beside `26/83` without explaining the extra 13 attempts.
- If import attempts are retained, display `70 imported · 13 skipped` rather than using 83 as the classification denominator.

#### 5.3 Fix cumulative progress

The current loop uses `source.classified = index`, where `index` starts from one for only the current pending batch. Replace this with one of the following:

- compute `ready + blocked + terminal_failed` from the database after each item; or
- initialize from the already terminal count and increment transactionally.

Prefer database-derived counts for correctness.

Do not count retriable failures as successfully classified. Report them separately.

#### 5.4 Stale-job reconciliation

On application/worker startup and periodically:

- find sources marked `classifying` with no queued/running classification job;
- if pending images remain, mark the source `stalled` or `pending` and expose **Resume classification**;
- optionally auto-enqueue one idempotent resume job;
- never leave a source permanently classifying because the API restarted.

If a job heartbeat expires, use the same standard failure handling as other execution jobs.

#### 5.5 Safe repair for `nenne_02`

After code and migrations are deployed:

1. reconcile its counters from `DatasetImage` rows;
2. preserve the 26 ready descriptions;
3. queue classification only for the 44 pending rows;
4. verify the job appears globally with `0/44` or cumulative `26/70` progress;
5. verify it reaches 70 terminal records or reports explicit failed items;
6. do not delete or re-import the source as part of the repair.

#### 5.6 UI behavior

- Replace the current source-only spinner with a Job-linked progress row.
- Show `26 ready · 44 pending · 0 failed`.
- Display ETA when available; otherwise show “Estimating…” rather than a fake value.
- Primary action when stalled: **Resume classification**.
- Primary action when running: **View job**.
- Disable duplicate start only while a real active job exists.
- If classification fails, show the readable error and a Retry action.

#### 5.7 Tests

- Classification survives API restart.
- Worker restart causes reconciliation or retry, not a permanent `classifying` source.
- Existing ready images are not reclassified during resume.
- Counter mismatch is reconciled.
- Duplicate requests return the same active job instead of starting parallel work.
- Source reaches `ready`, `partial`, or `failed` based on explicit outcomes.
- Jobs API exposes progress and classification type.

Primary files likely include:

- `app/dataset.py`
- `app/dataset_api.py`
- `app/jobs.py`
- the worker dispatch/handler module
- `app/db.py` or migration files if source counters/state require schema changes
- `webui/src/api.ts`
- `webui/src/components/DatasetPlayground.tsx`
- backend dataset/job tests

**Exit condition:** classification is durable, correctly counted, visible as a job, and `nenne_02` can resume from its 44 pending images.

### Phase 6 — Add the global active-jobs tray

The current header badge links directly to Jobs and only shows counts. Replace it with an interactive popover while retaining a **View all jobs** destination.

#### 6.1 Desktop behavior

Clicking the header job indicator opens a 340–400 px popover containing:

- header: `Jobs`, active count, attention count;
- up to five active/queued jobs;
- for each job:
  - type;
  - character/source name;
  - state;
  - progress bar;
  - current/total;
  - ETA or “Estimating…”;
  - short worker/GPU metadata only if useful;
- up to three recent failures when no active job exists or after the active section;
- footer: **View all jobs**.

The summary API already returns active and failed jobs. Reuse it where sufficient. Extend the API only if the summary omits progress fields needed by the tray.

#### 6.2 Mobile/compact behavior

- Use a bottom sheet or full-width drawer below 640 px.
- Keep rows dense and one-line where possible.
- The tray must not cover its own trigger without providing a visible close action.

#### 6.3 ETA

- Reuse the current job progress structure.
- Prefer server-provided progress and stable elapsed time.
- Calculate a client estimate only after enough progress exists.
- Smooth ETA changes to prevent large jumps, or update no more than once every few seconds.
- Never show an ETA when progress has no meaningful total.
- Queue state should show queue position rather than an ETA.

#### 6.4 Polling and actions

- Poll the badge approximately every five seconds while the application is visible.
- Poll the open tray more frequently only if necessary.
- Pause or reduce polling when `document.visibilityState !== "visible"`.
- Announce only new failures and completed jobs, not every progress update.
- Clicking a row opens Jobs with the relevant job expanded or filtered.
- If Cancel is included, require a confirmation only for cancellation and keep it visually secondary.

#### 6.5 Count semantics

- Active and failed/attention counts must be visually different.
- The accessible label must state both, for example: “2 active jobs, 3 jobs need attention.”
- Jobs page and header must use the same data source and state definitions.

Primary files:

- `webui/src/components/ui/JobTray.tsx`
- new `webui/src/components/ui/JobTrayPopover.tsx` if useful
- `webui/src/components/ui/JobProgress.tsx`
- `webui/src/api.ts`
- `webui/src/main.css`
- `webui/src/test/lora-jobs.test.tsx`
- `webui/src/test/ui.test.tsx`

**Exit condition:** the operator can inspect every active job, progress, and ETA without leaving the current page.

### Phase 7 — Compact Home and the remaining pages

#### 7.1 Home

The first viewport should prioritize work, not infrastructure.

New order:

1. Needs attention
2. Active jobs or recent work
3. Characters / workflow shortcuts
4. Compact system summary
5. Detailed infrastructure on demand

Changes:

- Keep attention cards compact and clickable.
- Add a small active-jobs summary that opens the global tray or Jobs.
- Change the default for `home_infra` from open to closed. In the current code, `localStorage.getItem("home_infra") !== "0"` opens it for new users; use an explicit saved opt-in such as `=== "1"`.
- When collapsed, show one line: service health, GPU count, and model health.
- Move Default models behind **Model settings**.
- Move GPU role allocation and Free VRAM behind **GPU settings**.
- Show GPUs as dense rows, not large cards, until expanded.
- Keep Recent jobs to three items maximum; link to Jobs.
- Keep Characters high enough to appear without scrolling through system details.
- Avoid multiple open accordions at the bottom. Use one **Models and runtimes** settings panel with sections inside it.

#### 7.2 Dataset

- Replace the full-width New Source button and empty Sources block with one compact source toolbar:
  - source selector;
  - status/count;
  - New source;
  - More.
- Keep progress immediately below the toolbar only while active or failed.
- Remove the two-step Image Details interaction. Clicking a card or one Details button should directly open the drawer.
- Keep Search, Status, and More in one compact row.
- Do not use a persistent bottom “Image details” bar after card selection unless it contains clear selection context and a primary action.

#### 7.3 Chat

- Use a compact context row for character and fan.
- Truncate long character personalities in selection cards.
- Keep conversations and settings accessible through clear buttons on compact screens.
- Preserve selected character, fan, conversation, model, and active Chat/Compare tab across route switching, following the same route-workspace pattern used for LoRA.
- Prevent the initial loading render from showing “0 characters” or “Choose a character” before the character request completes.

#### 7.4 Video

- The two-column video grid is appropriately compact at the audited width; retain it.
- Apply drawer opacity and settings grouping fixes.
- Keep card prompt to one line with ellipsis.
- Keep metadata to one compact row.
- Preserve Approve/Reject and content label, moving tertiary actions to More.

#### 7.5 Jobs

- Keep state chips and filters.
- Reduce the KPI region to four primary metrics: active, succeeded, failed, and storage/health.
- Put average duration by job type, approval rate, backups, and system coverage under **System metrics**.
- Put failure-code summaries immediately above the filtered job list only when relevant.
- Default the job list closer to the top of the viewport.
- Support URL filters so the LoRA page and global tray can link to a character, type, or specific job.

**Exit condition:** Home and LoRA surface the operator's next action before configuration detail; other pages no longer use space for redundant controls.

### Phase 8 — Accessibility, responsiveness, and final QA

#### 8.1 Required viewport checks

Verify every route and drawer at:

- 812 × 726
- 1024 × 768
- 1280 × 800
- 1440 × 900
- 1920 × 1080

#### 8.2 Automated checks

- No document-level horizontal overflow.
- No routine button has a rendered height greater than the shared single-line button height.
- No undefined required CSS custom properties.
- Every drawer contains exactly one visible close action.
- Every drawer returns focus to its trigger.
- Escape and backdrop close work.
- Underlying page cannot scroll while drawer is open.
- All drawers have an opaque computed background.
- Core Review controls are visible at 812 × 726.
- LoRA state persists across route switches.
- Dataset classification is represented by an execution job.
- Job tray and Jobs page counts agree.

#### 8.3 Manual workflows

1. Open and close every menu and drawer with mouse and keyboard.
2. Review ten images using only keyboard shortcuts.
3. Select a non-first LoRA character and non-first stage, switch through three routes, and return.
4. Begin/resume dataset classification and follow it from Dataset, the global tray, and Jobs.
5. Verify job completion updates all three surfaces.
6. Open Home and confirm the first viewport is useful without expanding infrastructure.
7. Confirm all former controls are still reachable in no more than two interactions.

## 5. Shared UI Architecture Recommendation

Avoid creating another collection of unrelated page-specific disclosures. Standardize on four patterns:

### Pattern A — Settings button

Use for configuration with multiple fields.

Examples:

- Chat Settings
- Character settings
- Image generation settings
- Video settings
- GPU settings
- Model settings

### Pattern B — More menu

Use for low-frequency item actions.

Examples:

- duplicate;
- move;
- export;
- reset;
- delete/danger actions.

### Pattern C — Details drawer

Use for inspecting one selected item.

Examples:

- dataset image details;
- job technical details;
- image metadata;
- LoRA run details.

### Pattern D — Full-width workspace

Use for visual comparison or rapid repeated decisions.

Examples:

- Images Review;
- Identity Set review;
- LoRA dataset curation;
- model comparison.

Do not represent the same content as a tab, accordion, drawer, and modal simultaneously.

## 6. File-Level Work Map

| File | Required work |
| --- | --- |
| `webui/src/main.css` | Define missing tokens; repair drawer surfaces; enforce single-line action buttons; add Review viewport layout; compact page styles. |
| `webui/src/components/ui/InspectorDrawer.tsx` | Header/body/footer API, size variants, scroll lock, one close control. |
| `webui/src/components/ui/AppHeader.tsx` | Integrate interactive JobTray; refine responsive account menu. |
| `webui/src/components/ui/JobTray.tsx` | Replace count-only link with active-jobs popover/sheet. |
| `webui/src/components/ui/JobProgress.tsx` | Compact reusable progress presentation for tray and pages. |
| `webui/src/components/ui/ReviewStage.tsx` | Viewport-sized media stage and sticky decision bar. |
| `webui/src/components/ImagePlayground.tsx` | Review persistence, filmstrip behavior, automatic cursor loading, generator grouping. |
| `webui/src/components/VideoPlayground.tsx` | Settings grouping and drawer footer. |
| `webui/src/components/DatasetPlayground.tsx` | Job-backed progress, compact source toolbar, direct details opening, stalled/retry states. |
| `webui/src/components/Playground.tsx` | Short Chat settings tabs, remove duplicate accordions, preserve route state. |
| `webui/src/components/HomePage.tsx` | Default collapsed infrastructure and Settings-based model/GPU configuration. |
| `webui/src/components/LoraPlayground.tsx` | Persist selection/stage/subview; compact Character; shorten embedded job history. |
| `webui/src/hooks/useLoraWorkspaceState.ts` | New versioned route/session state hook. |
| `webui/src/api.ts` | Classification job response and any job-summary progress fields. |
| `app/dataset.py` | Correct counters, cumulative progress, idempotent resume behavior. |
| `app/dataset_api.py` | Enqueue durable classification jobs instead of in-process task. |
| `app/jobs.py` | Classification job type/handler, heartbeat, progress, ETA inputs, stale reconciliation. |
| worker dispatch module | Execute `dataset_classify` jobs durably. |
| tests | Add responsive, persistence, drawer, review, and restart-recovery coverage. |

## 7. Acceptance Matrix

| Area | Must be true before completion |
| --- | --- |
| Drawers | Opaque, one close action, independent scroll, sticky header/footer where applicable, no content bleed. |
| Buttons | Routine labels never wrap; toolbars wrap controls or use More. |
| Images Review | Image and decision controls visible together at 812 × 726; filmstrip compact/collapsible. |
| LoRA | Selected character, stage, dataset, and working context survive route switching. |
| LoRA Character | Summary-first; advanced profile/identity controls behind Settings; no lost functions. |
| Dataset | `nenne_02` can resume 44 pending items without redoing 26 ready items; progress denominator is 70 actual images or explicitly explains skipped attempts. |
| Jobs | Dataset classification appears as a durable job with progress and heartbeat. |
| Global tray | Active jobs, progress, and ETA visible from every route. |
| Home | Infrastructure closed by default; attention, active work, and characters appear first. |
| Chat | Short settings tabs; no duplicated tab/accordion titles; loading does not flash false empty state. |
| Video | Generator readable and opaque; settings grouped; cards remain compact. |
| Accessibility | Keyboard/focus behavior verified; status not color-only; icon buttons labeled. |
| Regression | Every pre-existing action remains reachable and tested. |

## 8. Definition of Done

This plan is complete only when all of the following are satisfied:

- Shared CSS tokens are defined and no drawer is transparent.
- No professional action button breaks its label across lines at supported widths.
- Images Review supports continuous, no-document-scroll reviewing.
- LoRA returns to the same character, stage, dataset, and working position after route switches.
- LoRA Character presents the same capabilities in a substantially smaller default footprint.
- `nenne_02` classification is repaired through durable job execution and accurate counters.
- A global jobs popover/sheet displays active work, progress bars, and ETA.
- Home opens as a compact operational dashboard rather than an expanded infrastructure page.
- Chat, Video, Dataset, LoRA, and Jobs use the same Settings/More/Details/full-workspace interaction vocabulary.
- All changes pass automated tests and manual viewport validation.
- No API key, secret, private filesystem path, or sensitive raw prompt is introduced into logs, fixtures, or screenshots.

## 9. Guardrails for the Coding Agent

- Do not delete advanced settings merely to reduce visual density.
- Do not solve wrapping by shrinking text below readable sizes.
- Do not store API keys or secrets in local storage as part of workspace persistence.
- Do not persist transient confirmation dialogs.
- Do not silently reset invalid saved state; fall back safely and provide a clear state when needed.
- Do not repair `nenne_02` by deleting or re-importing its existing data.
- Do not keep dataset classification in an API-process background task.
- Do not display a fabricated ETA.
- Do not create separate drawer implementations for each page.
- Keep commits phase-scoped so each phase can be reviewed or reverted independently.
