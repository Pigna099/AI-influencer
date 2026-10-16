# UI Modification Plan

## 1. Purpose

This document describes a UI-only redesign of the current AI Influencer WebUI. It is intended to be handed directly to an implementation agent.

The goal is to make the interface calmer, more compact, and easier to scan without removing or weakening any existing capability. Complex controls must remain available, but they should appear only when they are relevant: in drawers, expandable advanced sections, contextual menus, or dedicated full-width review screens.

The audit covers the current Home, Chat, Images, Video, Dataset, LoRA, and Jobs pages in the v6 application.

## 2. Audit Conditions

- Audit date: 2026-10-16.
- Application observed in the in-app browser at approximately 812 × 726 CSS pixels.
- Current application source: `/data/data_ssd/pigni/ai-influencer/backend-v6/webui/src`.
- The application was inspected after authentication and after waiting for asynchronous data to load.
- This is a visual and interaction-architecture plan. Preserve the current API contracts, data model, workflows, permissions, and generation behavior unless a UI requirement explicitly needs a small presentation-layer adapter.
- Never place API keys, secrets, private prompt data, or full local filesystem paths in the rendered UI, logs, screenshots, or source fixtures.

## 3. Main Findings

The largest problem is not the amount of functionality; it is that too much of it is visible at the same time.

The current shell frequently forces three columns into a viewport that cannot support them. The shared workspace uses fixed side widths, while Images and LoRA use even wider variants. At medium and narrow widths this produces the following failures:

- The primary content becomes too narrow to use comfortably.
- Image and video generation inspectors can be positioned outside the visible viewport.
- Grid pages degrade into a single narrow card column.
- LoRA displays the character rail, workflow, and guide simultaneously, leaving insufficient space for every one of them.
- Header elements wrap or become ambiguous.
- Important actions compete visually with secondary and destructive actions.
- Long pages combine navigation, configuration, review, monitoring, and help content in one scroll surface.

The redesign should use progressive disclosure: show status and the next action first, then reveal detailed configuration on demand.

## 4. Non-Negotiable Requirements

1. Do not remove any current action, field, filter, review control, configuration option, or status detail.
2. Every relocated action must remain reachable in no more than two interactions from its page.
3. Primary content must never be horizontally clipped or hidden behind an off-screen inspector.
4. Every route must open at the top of its relevant scroll container.
5. Draft, approved, rejected, failed, active, and pending states must remain visually distinct without relying on color alone.
6. Destructive actions must not share the same visual prominence as routine actions.
7. Loading should not briefly present valid data as zero or empty.
8. Desktop efficiency must be preserved while the 812 px in-app viewport becomes fully usable.
9. Keyboard shortcuts and bulk-review workflows must continue to work.
10. The implementation must be responsive through CSS and reusable layout components, not route-specific viewport hacks.

## 5. Priority Order

### P0 — Correctness and access

- Prevent off-screen inspectors and horizontal overflow.
- Make the full navigation usable at 812 px.
- Reset route scroll position correctly.
- Replace literal or untranslated UI strings such as `jobs.state.active` and `9/{imported}`.
- Resolve the job badge inconsistency: the header currently exposes a number as “active jobs” while the Jobs page can report zero active jobs.
- Add stable loading states so asynchronous totals do not flash as zero.

### P1 — Information architecture

- Introduce responsive rails and inspectors.
- Reduce simultaneous panels.
- Move advanced and infrequent settings behind progressive disclosure.
- Split LoRA into a staged workflow.
- Turn Images review into a dedicated full-width mode.

### P2 — Density and polish

- Standardize spacing, type scale, buttons, cards, metadata, badges, and empty states.
- Improve action hierarchy and duration formatting.
- Add hover menus and compact toolbars.
- Improve keyboard, focus, and screen-reader behavior.

## 6. Responsive Layout Specification

Use four explicit layout ranges.

| Viewport | Shell behavior | Side rail | Inspector |
| --- | --- | --- | --- |
| ≥ 1440 px | Full desktop | 216–232 px expanded rail | 312–344 px persistent panel where useful |
| 1280–1439 px | Compact desktop | 64 px icon/avatar rail or 200 px collapsible rail | Persistent only if the center remains at least 720 px; otherwise drawer |
| 1024–1279 px | Two-area layout | Collapsed rail or page-level selector | Right drawer/sheet |
| < 1024 px | Single content column | Hidden; replace with selector/drawer | Modal drawer or bottom sheet |

Implementation rules:

- Never define a three-column grid whose minimum widths exceed the viewport.
- The center content should have a minimum usable width, not merely `minmax(320px, 1fr)`.
- At widths below 1280 px, generation and details inspectors must be overlays, not grid columns.
- At widths below 1024 px, page-specific selection rails become a compact top selector plus an optional drawer.
- Use `min-width: 0` on grid children and wrap toolbar content deliberately.
- Avoid page-level horizontal scrolling. Only intentionally wide data tables may scroll inside their own bounded container.
- A drawer must preserve its state when closed and reopened.
- A persistent drawer trigger should display a concise summary of the current configuration.

Suggested structural component:

```tsx
<ResponsiveWorkspace
  rail={<PageRail />}
  main={<PageContent />}
  inspector={<PageInspector />}
  inspectorSummary="Real · Default · 1 LoRA"
/>
```

Do not copy this layout logic independently into every page. Replace the inline LoRA grid columns and the special Images grid with the same reusable responsive system.

## 7. Global Visual System

### Density

Use a compact but not cramped rhythm:

- Page padding: 20–24 px desktop, 16 px medium, 12 px narrow.
- Section gap: 20 px desktop, 16 px medium, 12 px narrow.
- Card padding: 14–16 px; dense list rows: 10–12 px.
- Control height: 36 px standard, 32 px compact.
- Header height: 56–60 px instead of 76 px.
- Default border radius: 8 px controls, 10–12 px cards.
- Use one border and one subtle surface change for grouping; avoid nested boxes with equal visual weight.

### Typography

- One clear page title, 24–28 px.
- Section titles, 15–17 px semibold.
- Body and form labels, 13–14 px.
- Metadata, 11–12 px.
- Truncate long identifiers and paths; reveal their full value in a tooltip or details panel.
- Prefer short human labels over internal enum names.

### Action hierarchy

- One visually primary action per section.
- Secondary actions use neutral buttons.
- Tertiary actions use text or icon buttons.
- Destructive actions live in overflow or Danger Zone areas and require confirmation.
- Disabled controls should remain legible and explain why they are disabled via tooltip or nearby text.

### Status and feedback

- Use icon + label + color for state.
- Use skeletons for initial loading and spinners/progress bars for ongoing operations.
- Empty state means a completed request returned no data; it must not be used during loading.
- Toasts are for transient confirmation. Persistent errors stay near the affected item.
- Format durations for people: `3h 31m`, `2m 1s`, `18s`, never `12657.5s` in the normal UI.

## 8. Shared Components to Add or Refactor

Create or standardize the following primitives under `webui/src/components/ui`:

1. `ResponsiveWorkspace`
   - Owns rail/main/inspector breakpoints.
   - Converts side areas to drawers automatically.
   - Ensures the main panel always has `min-width: 0`.

2. `ContextSelector`
   - Compact top control for character, fan, source, or project selection.
   - Displays avatar/icon, primary name, short status, and chevron.
   - Opens the original selection list in a drawer at narrow widths.

3. `InspectorDrawer`
   - Accessible desktop side sheet and narrow bottom sheet.
   - Has title, summary, close button, scrollable body, and sticky action footer.
   - Returns focus to its trigger on close.

4. `CompactToolbar`
   - Supports search, filters, segmented state controls, selection count, and overflow.
   - Wraps intentionally or collapses secondary filters into a Filters popover.

5. `KpiStrip`
   - Small metric cards/chips for counts and health summaries.
   - Never renders a long unstructured sentence of numbers.

6. `OverflowMenu`
   - Moves low-frequency and destructive card actions out of the default layout.

7. `ProgressSummary`
   - Displays completed, pending, failed, percentage, and optional ETA.

8. `AsyncContent`
   - Standard loading, empty, error, and success states.
   - Prevents zero-count flashes.

9. `AdvancedSettings`
   - Keep the existing component, but use it consistently for model-specific and expert controls.

10. `RouteScrollReset`
    - Scrolls the relevant main, rail, and inspector containers to the expected position on route change.
    - Preserve scroll only when returning to a list from an item detail, if explicitly implemented.

## 9. Application Header

Current issue: brand, version, seven navigation items, the job count, and logout compete in one row. At the audited width the version and logout wrap, and the bare job count has unclear meaning.

### Target behavior

#### ≥ 1280 px

- Keep the brand, route navigation, jobs indicator, and account menu on one 56–60 px row.
- Render `v6` as a small badge beside the brand, never on a second line.
- Use a compact jobs icon with a labeled badge and tooltip, for example “3 jobs need attention.”
- Replace the wide Logout button with an account/menu button containing Logout.

#### 1024–1279 px

- Keep the most important route tabs visible.
- Move lower-frequency routes into a More menu if necessary.
- Keep active-route indication visible.

#### < 1024 px

- Show brand, current section title, jobs indicator, and menu button.
- Put all route links and logout in the menu drawer.

### Required fixes

- Define whether the job badge means active, failed, or attention-required jobs and use the same query/label everywhere.
- Add accessible names to icon buttons.
- Keep the header sticky without making every inner panel appear independently sticky.

Files: `components/ui/AppHeader.tsx`, `components/ui/JobTray.tsx`, `main.css`, and possibly `App.tsx` for route metadata.

## 10. Home Page

### Problems observed

- “Needs attention” is a series of loose rows with excessive vertical space and repeated Open actions.
- Service cards leave awkward empty space when their count does not fill the row.
- GPU cards are informative but very large, with oversized circular gauges and process details always visible.
- Operational summaries and infrastructure diagnostics compete on the same level.

### New structure

1. Page header: title, last refresh, refresh button.
2. Compact attention strip: maximum four cards in an adaptive grid.
3. Running/recent jobs summary.
4. Character summary and quick actions.
5. Default models.
6. Collapsible “System and infrastructure” section containing services, GPUs, and installed-model accordions.

### Detailed changes

- Convert each attention item into a compact card with icon, title, count/status, short explanation, and chevron. Make the entire card clickable instead of repeating “Open.”
- Use `repeat(auto-fit, minmax(190px, 1fr))` for attention and service cards.
- Display service health as compact pills or one-row cards.
- Replace each default GPU card with a dense summary row containing GPU name/number, assigned role, utilization, VRAM, temperature, and health.
- Expand a GPU row to reveal power, process list, and role controls.
- Keep character cards and installed-model accordions; reduce redundant surrounding padding.
- Place infrastructure below product workflow information and remember whether the user expanded it.

### Acceptance criteria

- At 812 px the first screen shows page title, attention summary, and at least part of the job/character content.
- No GPU process list is open by default.
- A user can still change GPU role and inspect every existing metric.

Primary file: `components/HomePage.tsx`.

## 11. Chat Page

### Problems observed

- The left rail mixes character selection, character editing, FanVue account, test notes, and conversations.
- “Edit personality” and “Open in Character tab” are redundant or poorly differentiated.
- The no-chat empty state consumes too much central space while configuration sections create a very long page below it.
- Character settings, photo settings, memory, and timing settings sit below the transcript instead of beside or behind it.
- The page can inherit the previous route’s scroll position.

### New structure

#### Main page

- Top context row: character selector, fan selector, current model, and New chat.
- Left rail on wide screens: conversations only, with search and New chat.
- Center: Chat/Compare tabs, transcript or compact empty state, sticky composer.
- Right inspector on wide screens: Character, Media, Memory, and Timing tabs.
- At narrower widths, conversations and settings each become independently opened drawers.

### Detailed changes

- Replace long character content in the rail with `ContextSelector`.
- Put personality editing in the Character inspector tab. Remove the duplicate route wording while preserving both underlying destinations if they are functionally different.
- Show test notes as a one-line preview with Expand; do not let notes push conversations below the fold.
- Place New chat in the conversation header and in the empty state.
- Empty-state copy should say exactly how to proceed: choose a conversation or create one.
- Keep the composer visible at the bottom of the center panel; disable it with an explanatory label only when no chat exists.
- Move Photo style, Photo checkpoint, Realism, Fan memory, and Chat timings into inspector tabs.
- Preserve Compare as a primary tab. If model comparison needs more width, open a full-width comparison view rather than squeezing it beside rails.
- Scroll only the transcript, not the complete page, during active conversations.
- Reset route scroll on entry.

### Acceptance criteria

- At 812 px the user sees the current context, empty state or transcript, and composer without scrolling through settings.
- New chat is immediately discoverable.
- All current settings remain accessible through a single Settings button/drawer.
- Transcript and composer widths remain useful at all supported viewports.

Primary files: `components/Playground.tsx`, `components/ChatPanel.tsx`, `components/BenchmarkPanel.tsx`.

## 12. Images Page

### Problems observed

- The three-column layout makes the grid extremely narrow and moves the generation inspector outside the visible viewport.
- The grid becomes one card wide even when the viewport could support a useful two-column layout without rails.
- The toolbar contains too many filters and disabled bulk controls simultaneously.
- The complete LoRA catalog is rendered as a long configuration form.
- Review mode is squeezed between side panels and cannot prioritize the selected image.
- The initial empty state can appear before the image collection finishes loading.

### New Grid mode

- Top row: context selector, Grid/Review/Trash tabs, result count, and primary Generate button.
- Second row: compact search/filter toolbar.
- Full-width responsive image grid.
- Generator appears as a persistent inspector only on sufficiently wide screens; otherwise it is a drawer.
- Bulk action toolbar appears only after one or more images are selected.

Grid columns should be driven by card minimum width, for example `repeat(auto-fill, minmax(220px, 1fr))`, with an upper bound on card width if needed.

### Generator redesign

Default view should contain:

- Prompt.
- Negative prompt only if currently used frequently; otherwise place it in Advanced.
- Preset or recipe summary.
- Count.
- Selected character/identity.
- Selected LoRAs shown as removable chips.
- Primary Generate button in a sticky footer.

Advanced view should contain:

- Checkpoint.
- LoRA manager, weights, category, and CLIP controls.
- Pose/source controls.
- Seed and sampler/model-specific parameters.
- Classification and other expert options.

Do not render dozens of LoRAs as a permanently expanded list. Add “Manage LoRAs,” with search, compatibility filtering, multi-select, and selected-only editing. Preserve the “incompatible LoRAs hidden” information as a compact message with a reveal option.

Keep the current recipe summary such as “Real · Default · 1 LoRA”; make it the drawer trigger and allow it to be clicked to edit.

### Review mode redesign

- Review becomes a dedicated full-width subview.
- Large image is the visual priority.
- Compact action bar contains previous/next, rating, approve/reject, content class, and position count.
- Filmstrip is at the bottom or in a collapsible side strip.
- Caption and metadata use an expandable panel.
- Keyboard help is accessible through a shortcut/help button, not permanently displayed.
- Left rail and generator are closed by default in review mode.

### Card behavior

- Keep status and rating visible.
- Show prompt as one or two lines.
- Move low-frequency actions and Delete into an overflow menu.
- Reveal review actions on hover/focus for pointer devices, but keep them reachable through keyboard focus and touch menus.

### Acceptance criteria

- At 812 px the generator is never off-screen and the grid uses the entire available content width.
- At least two practical image columns appear when card width permits.
- Initial loading never shows “0 images” as a completed empty state.
- Review mode displays a large, useful image and all review actions without horizontal scrolling.

Primary files: `components/ImagePlayground.tsx`, `components/ui/ReviewStage.tsx`, `main.css`.

## 13. Video Page

### Problems observed

- The same three-column overflow makes the generator inaccessible.
- The character rail contains very little information but consumes a fixed width.
- Video cards are tall, single-column, and show every action and metadata field at once.
- Source selection is form-oriented instead of visual.

### New structure

- Context selector at top rather than a permanent rail below 1440 px.
- Full-width responsive video grid.
- Review/status filters in a compact toolbar.
- Primary Generate video button opens the generator drawer below 1280 px.
- Wide desktop may retain a right generator inspector only if the grid center remains at least 720 px.

### Generator changes

- Use a visual source-image picker with thumbnail, state, and search/filter rather than only a long select.
- Keep motion presets as selectable chips/cards.
- Show the current output summary prominently, for example resolution, clip duration, frames, and steps.
- Put model-specific parameters under Advanced Settings.
- Keep Generate in a sticky footer.

### Card changes

- Use a fixed media aspect ratio.
- Prompt is one or two lines with full text on demand.
- Display content class and state as badges.
- Group clip duration, resolution, and generation time into a compact metadata row.
- Put Approve/Reject in a review overlay or focused action bar.
- Put Delete and secondary actions in overflow.
- Ensure Play has a real accessible label and visible keyboard focus.

### Acceptance criteria

- At 812 px the video grid and Generate action are visible without horizontal scrolling.
- Source image, motion preset, and all advanced settings remain available.
- Clip duration and generation duration remain clearly differentiated.

Primary file: `components/VideoPlayground.tsx`.

## 14. Dataset Page

### Problems observed

- Pending cards are large empty blocks with little useful feedback.
- The progress label contains an unresolved placeholder.
- Routine actions and Delete have equal prominence.
- Hash-like filenames and repeated buttons dominate cards.
- The detail inspector is not reliably available at the audited width.
- Large datasets need stronger filtering and rendering strategy.

### New structure

- Top context selector for dataset source at medium/narrow widths.
- Source rail remains available on wide screens with compact count/status summaries.
- Header includes source name, concise status, primary next action, and overflow menu.
- Progress summary shows ready, pending, failed, percentage, and ETA when available.
- Compact filter bar: search, status, classification, sort, selection.
- Responsive dataset grid.
- Details open in a right drawer below 1280 px.

### Detailed changes

- Replace `Classifying 9/{imported}…` with real computed values and a progress bar.
- Use a skeleton or spinner in pending media areas; do not present a blank card as if content is missing.
- Treat generated hashes as secondary metadata and truncate them visually.
- Make the card itself open details.
- Move Delete image to overflow.
- Move Delete source to the source header overflow or a dedicated Danger Zone with confirmation.
- Show Classify as the primary action when classification is incomplete. Export and Generate profile remain secondary.
- Add bulk selection and bulk classification/review actions if those APIs already exist; do not invent unsupported backend operations.
- Convert New Source into a modal/drawer import flow so it does not permanently consume rail space.
- Add pagination, incremental loading, or virtualization for large datasets.

### Acceptance criteria

- Progress is accurate and contains no template placeholders.
- Pending, ready, and failed items are distinguishable without opening details.
- Delete is never adjacent to the primary routine action with equal emphasis.
- The inspector is accessible at every supported width.

Primary files: `components/DatasetPlayground.tsx`, `components/DatasetPanel.tsx`, `components/PoseLibrary.tsx`.

## 15. LoRA Page

### Problems observed

- This is the most overloaded page: character rail, workflow, and guide are visible simultaneously.
- The main workflow becomes too narrow, causing clipped buttons and forms.
- The guide duplicates close/hide controls and permanently consumes a third column.
- Character, identity set, dataset, training, active LoRAs, errors, and job history all share one very long page.
- Danger Zone appears inside the normal first step.
- Technical errors and paths can dominate failed job cards.

### Target information architecture

Use a staged workflow with a sticky horizontal stepper:

1. Character
2. Identity Set
3. Dataset
4. Train & Validate

The stepper should show status, count, and next action, using the current compact summary as its foundation. Only one stage is expanded at a time. Completed stages can be revisited without losing state.

### Character selection

- Use the shared context selector at medium/narrow widths.
- On wide screens, a compact avatar rail is acceptable.
- Reduce long policy/status prose in character rows to icons and short labels with tooltips.

### Guide

- Replace the permanent guide column with a Help button.
- Open help as a contextual drawer or popover tied to the current step.
- Use one close mechanism, not duplicated “Hide guide” controls.
- Preserve all existing guide content.

### Stage 1 — Character

- Show identity summary and the minimum inputs required to proceed.
- Put full character editing in a settings drawer.
- Move Danger Zone out of the workflow into the settings drawer, collapsed by default.

### Stage 2 — Identity Set

- Use a dedicated full-width review/selection view for face-angle candidates.
- Emphasize similarity, selection status, and the required target count.
- Keep generation settings behind Advanced.
- Provide a clear “Continue to Dataset” action when requirements are met.

### Stage 3 — Dataset

- Open a full-width dataset curation subview rather than embedding the complete dataset UI in the main long page.
- Show progress, accepted count, required count, distribution/coverage summary, and next action.
- Keep pose/style generation and filtering available in a drawer or secondary toolbar.

### Stage 4 — Train & Validate

- Show training configuration summary first.
- Put expert training parameters under Advanced Settings.
- Display one active job prominently, then the three most recent relevant jobs.
- Link to Jobs for full history instead of duplicating the entire job history.
- For failures, show a short human-readable cause and recommended next step. Keep raw logs and paths inside Technical details.
- Show the active LoRA and validation status clearly after success.

### Loading behavior

- Use skeletons for LoRA count, dataset count, active model, and workflow status.
- Do not flash “0 LoRAs” or “0 dataset images” before data is loaded.

### Acceptance criteria

- At 812 px only the workflow stage is visible by default; character selection and help use drawers.
- No controls are clipped.
- The next required action is obvious in every stage.
- Identity review and dataset curation have enough width for visual comparison.
- Full job history remains available through Jobs.

Primary file: `components/LoraPlayground.tsx`. Remove its inline grid-column decision and use shared responsive CSS/components.

## 16. Jobs Page

### Problems observed

- State, Type, and Character filters stack vertically and consume too much header space.
- Metrics are rendered as a long sentence rather than a visual summary.
- Durations use raw seconds.
- At least one state label is untranslated.
- The header badge and page active count can disagree.
- Internal failure codes are exposed without readable labels.
- Maintenance actions are too prominent, especially purge.
- System metrics use ambiguous symbols and the job list is clean but sparse.

### New structure

1. Page header with title, refresh status, and compact actions.
2. State tabs/chips: Active, Failed, Completed, All.
3. KPI strip: active, succeeded, failed, median/average duration where useful.
4. Compact filter toolbar: search, type, character, date range, Clear.
5. Job table/list.
6. Collapsible System metrics and Maintenance sections.

### Detailed changes

- Replace the inline metrics sentence with small labeled KPI cards.
- Humanize all durations.
- Map state and error codes to readable labels while preserving raw codes in Technical details.
- Clarify the header badge semantics and use the same source of truth in `JobTray` and Jobs.
- Make failure summaries clickable filters.
- Use a compact job row containing type, state, character, started time, duration/progress, and primary action.
- Expand a failed row inline for remediation; place raw events/logs in a drawer.
- Replace ambiguous marks in system tables with labeled columns or icons with tooltips.
- Place Scan orphaned files in Maintenance. Place Purge trash in a nested danger area with confirmation and consequence text.
- Add pagination or Load more.
- Use this page as the canonical full history for LoRA, dataset, image, and video jobs.

### Acceptance criteria

- At 812 px filters fit in one compact region, with secondary filters in a popover if required.
- Metrics are individually scannable.
- No raw localization keys are visible.
- Header and page job counts agree by definition.
- Purge cannot be triggered accidentally.

Primary files: `components/JobsPage.tsx`, `components/ui/JobTray.tsx`, `components/ui/JobProgress.tsx`.

## 17. File-Level Implementation Map

Start by reading the current components and tests before editing. Expected areas:

| File | Work |
| --- | --- |
| `webui/src/main.css` | Replace fixed workspace assumptions; add breakpoints, density tokens, responsive grids, drawers, compact controls, and focus styles. |
| `webui/src/App.tsx` | Route metadata, scroll reset integration, shell behavior. |
| `webui/src/components/ui/AppHeader.tsx` | Compact responsive header and overflow navigation. |
| `webui/src/components/ui/JobTray.tsx` | Explicit badge semantics and accessible label. |
| `webui/src/components/ui/AdvancedSettings.tsx` | Consistent expert-control disclosure. |
| `webui/src/components/HomePage.tsx` | Compact dashboard and collapsible infrastructure. |
| `webui/src/components/Playground.tsx` | Chat page information architecture. |
| `webui/src/components/ChatPanel.tsx` | Transcript/empty state/composer layout. |
| `webui/src/components/BenchmarkPanel.tsx` | Full-width comparison behavior. |
| `webui/src/components/ImagePlayground.tsx` | Full-width grid, generator drawer, conditional bulk toolbar. |
| `webui/src/components/ui/ReviewStage.tsx` | Dedicated image review layout. |
| `webui/src/components/VideoPlayground.tsx` | Responsive grid and generator drawer. |
| `webui/src/components/DatasetPlayground.tsx` | Source selector, progress, grid, and details drawer. |
| `webui/src/components/DatasetPanel.tsx` | Compact cards and dataset review behavior. |
| `webui/src/components/PoseLibrary.tsx` | Align filters/cards with the shared dataset patterns. |
| `webui/src/components/LoraPlayground.tsx` | Staged workflow; remove inline three-column layout. |
| `webui/src/components/JobsPage.tsx` | KPI strip, compact filters, table/list, maintenance hierarchy. |
| `webui/src/components/ui/*` | Add the reusable layout and interaction primitives described above. |

Do not perform a full visual rewrite inside each page independently. Establish tokens and responsive primitives first, then migrate pages.

## 18. Step-by-Step Implementation Sequence

### Phase 1 — Baseline and regression protection

1. Capture screenshots at 812, 1024, 1280, 1440, and 1920 px for all seven routes.
2. List every current action and form field per route.
3. Add tests asserting that those actions remain reachable after the redesign.
4. Record current keyboard shortcuts in Images review and Chat.
5. Add test fixtures for loading, empty, populated, active, failed, and mixed-state pages.

### Phase 2 — Foundation

1. Add spacing, type, control-height, surface, border, and status tokens.
2. Implement `ResponsiveWorkspace`, `ContextSelector`, `InspectorDrawer`, `CompactToolbar`, `KpiStrip`, `OverflowMenu`, `ProgressSummary`, and `AsyncContent`.
3. Implement route scroll reset.
4. Refactor header and JobTray.
5. Add breakpoint tests and a no-horizontal-overflow assertion.

### Phase 3 — Highest-severity responsive fixes

1. Migrate Images to the shared workspace; make generator a drawer at medium widths.
2. Migrate Video the same way.
3. Remove the LoRA inline three-column layout and convert guide/character selection to drawers.
4. Migrate Dataset details to a drawer.
5. Verify all functionality at 812 px before continuing.

### Phase 4 — Workflow restructuring

1. Build the staged LoRA flow and dedicated Identity/Dataset subviews.
2. Build the full-width Images review mode.
3. Reorganize Chat into conversations, transcript, and settings inspector.
4. Make Jobs the canonical full job-history surface.

### Phase 5 — Page density improvements

1. Compact Home attention, service, and GPU areas.
2. Redesign Jobs metrics, filters, rows, and maintenance section.
3. Improve Dataset progress and cards.
4. Compact Video and Images card metadata/actions.

### Phase 6 — Accessibility and polish

1. Verify tab order, focus trapping, focus restoration, Escape-to-close, and visible focus.
2. Add labels/tooltips to icon-only controls.
3. Verify all statuses have text/icons as well as color.
4. Check contrast and reduced-motion behavior.
5. Humanize durations and internal enum/error strings.
6. Verify loading states do not flash false zeros.

### Phase 7 — Final validation

1. Run unit/component tests.
2. Run responsive visual tests at all target widths.
3. Exercise complete workflows: create chat, generate/review image, generate/review video, import/classify dataset, progress through LoRA stages, inspect/retry a failed job.
4. Compare the final action inventory against the baseline.
5. Confirm there is no page-level horizontal overflow.
6. Confirm drawers do not lose unsaved form state when temporarily closed.

## 19. Accessibility Requirements

- All drawers and menus need correct dialog/menu semantics, focus trap, Escape behavior, and focus restoration.
- Icon buttons require visible tooltips and programmatic names.
- Segmented controls must expose selected state.
- Image and video review controls must be keyboard operable.
- Do not implement hover-only actions without a focus/touch alternative.
- Use descriptive labels for status symbols and progress.
- Announce async job completion and failure through an appropriate live region without repeatedly announcing polling updates.
- Preserve logical heading order after moving content into drawers.

## 20. Performance Requirements

- Virtualize or incrementally render large image, video, and dataset collections.
- Lazy-render closed inspector and guide content where safe, but preserve unsaved state.
- Avoid re-fetching every page merely because a drawer opens.
- Reserve media aspect-ratio space to prevent layout shift.
- Debounce search/filter inputs.
- Use thumbnail assets in grids and load full media only in review/detail views.
- Avoid rendering the entire LoRA catalog until its manager opens.

## 21. Test Plan

Extend the existing tests in:

- `webui/src/test/shell.test.tsx`
- `webui/src/test/ui.test.tsx`
- `webui/src/test/lora-jobs.test.tsx`

Add coverage for:

- Header navigation and menu behavior at each breakpoint.
- Correct JobTray badge label and consistency with Jobs.
- Route scroll reset.
- Images and Video generator drawer access at 812 px.
- LoRA help and character drawers; one active stage at a time.
- Dataset progress interpolation and no unresolved placeholders.
- Loading vs empty-state distinction.
- Bulk toolbar hidden at zero selection and visible after selection.
- Drawer keyboard behavior and focus restoration.
- No action loss after migration to overflow menus.
- Human-readable durations and localized job states.
- No horizontal overflow on each route.

For visual regression, capture at minimum:

- 812 × 726 — current in-app constraint.
- 1024 × 768 — compact tablet/desktop.
- 1280 × 800 — standard laptop.
- 1440 × 900 — wide desktop threshold.
- 1920 × 1080 — large desktop.

## 22. Definition of Done

The work is complete only when:

- All seven routes are usable at 812 px without page-level horizontal scrolling.
- No inspector or primary action is placed outside the viewport.
- Header content does not wrap awkwardly.
- Images and Video grids use the primary available width.
- LoRA shows one clear stage at a time and provides full-width visual review surfaces.
- Chat keeps transcript and composer visible while settings remain one interaction away.
- Dataset progress is accurate and pending cards communicate activity.
- Jobs uses readable metrics, states, failure labels, and durations.
- Home shows operational priorities before infrastructure detail.
- All existing capabilities remain reachable and tested.
- Loading states never masquerade as genuine zero/empty states.
- Destructive actions are separated, confirmed, and visually subordinate.
- Keyboard and screen-reader workflows are verified.

## 23. Implementation Guardrails for the Next Agent

- Do not change backend behavior to simplify the UI.
- Do not delete advanced options; relocate them.
- Do not replace useful dense workflows with oversized marketing-style cards.
- Do not solve the problem by shrinking text below readable sizes.
- Do not add a new permanent sidebar for every feature.
- Do not display raw secrets or API keys.
- Keep changes incremental and test after each page migration.
- Prefer shared primitives over route-specific CSS exceptions.
- If an API lacks information required by a proposed progress or summary element, show only verified values and document the missing data instead of inventing it.
