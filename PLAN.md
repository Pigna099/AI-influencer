# AI Influencer Platform — Detailed Product, UI, Backend, and Workflow Plan

**Prepared:** 14 October 2026  
**Implementation baseline:** `/data/data_ssd/pigni/ai-influencer/backend-v6`  
**Companion document:** `report.md`

## 1. Goal

Evolve the current single-user playground into a reliable local-first production system for fully synthetic adult AI characters. The system should guide an operator through:

1. character definition;
2. identity creation from one approved synthetic or consented adult reference;
3. multi-angle identity selection;
4. a diverse, curated 50–70 image training dataset;
5. family-specific LoRA training and validation;
6. repeatable image and video production using a pose/style reference library;
7. simulated conversation testing;
8. later, controlled Instagram and Fanvue publishing and inbox workflows.

All model inference should remain compatible with open-source models running locally. External platform integrations should be adapters around the local core, not dependencies of generation or training.

## 2. Non-negotiable product principles

1. **Character-first context.** A selected character remains active across all creative tabs and is encoded in the URL.
2. **Workflow before model controls.** Show the next useful action first; put expert model settings behind an Advanced section.
3. **One job model.** Import, classification, generation, consistency checks, captioning, video, and training share the same job states and monitoring UI.
4. **Review gates.** Generated identity, training, publishing, PPV, and outbound messages require explicit review until separately enabled by policy.
5. **Reproducibility.** Every asset records prompt, negative prompt, seed, model, checkpoint, adapters, weights, pose, source/reference IDs, workflow version, and software version.
6. **Local-first privacy.** Raw media, face embeddings, chat history, and model artifacts stay local by default.
7. **Adult and synthetic by construction.** Character age must be explicitly adult; real-person likeness requires documented consent and rights.
8. **Progressive disclosure.** The normal path is simple; expert settings remain available without dominating the page.
9. **No false states.** Loading, empty, partial, failed, and stale are distinct UI states.
10. **Safe failure.** A failed model call never silently produces an empty item or publishes an unreviewed result.

## 3. Target information architecture

Replace the current flat, implementation-oriented navigation with a workflow-oriented shell.

### 3.1 Primary navigation

1. **Overview** — character readiness, active jobs, review queue, service warnings.
2. **Character** — bible, identity anchor, style, voice, monetization policy, platform profile.
3. **Identity & LoRA** — reference intake, multi-view candidates, canonical set, dataset, training, evaluation.
4. **Studio**
   - Images
   - Video
   - Asset Library
5. **References** — external datasets, pose library, style/moodboards, provenance.
6. **Conversations** — simulation first; connected inboxes later.
7. **Publishing** — content calendar, Instagram/Fanvue adapters, approval queue, analytics.
8. **Jobs & System** — queue, services, GPUs, installed models, logs, settings.

If a full navigation migration is too risky, retain the existing routes initially and add a persistent workflow rail above them. Migrate routes after state and job handling are stable.

### 3.2 Global character context

Add a persistent context bar below the header:

- avatar and character name;
- readiness stage;
- active image LoRA and family;
- current default image/video/chat model;
- warnings;
- quick switcher;
- “Continue setup” or “Next action.”

Use character-scoped routes such as:

- `/characters/:characterId/overview`
- `/characters/:characterId/chat`
- `/characters/:characterId/studio/images`
- `/characters/:characterId/studio/video`
- `/characters/:characterId/identity`

Persist the most recent character, but treat the URL as the source of truth. Never allow independent tabs to silently select different characters.

### 3.3 Three interface modes

Separate three jobs that are currently mixed:

- **Create:** configure and generate.
- **Review:** compare, rate, approve, reject, tag, select.
- **Operate:** jobs, publishing, conversations, system health.

Each page should have one primary mode and link to the others.

## 4. Target system architecture

Keep the current React/FastAPI/PostgreSQL/ComfyUI/vLLM/Ollama foundation. Refactor around four explicit layers:

```text
React workflow UI
        |
FastAPI domain services and typed API contracts
        |
Unified persistent job orchestrator + asset/provenance registry
        |
Adapters: vLLM, Ollama, ComfyUI, trainer, Instagram, Fanvue
```

Do not move business rules into React components. Components render state and submit commands; backend services decide eligibility, compatibility, transitions, and policy.

## 5. Target domain model

Extend existing tables instead of replacing them in one migration.

### 5.1 Core entities

- `workspaces`: owner/security boundary, even if only one exists initially.
- `characters`: name, adult age, synthetic/consented status, lifecycle state.
- `character_versions`: immutable personality/bible snapshots.
- `identity_profiles`: anchor asset, embedding version, canonical set, readiness.
- `source_collections`: imported source plus rights/provenance and intended use.
- `source_assets`: imported image/video and structured classification.
- `poses`: source, skeleton, crop, quality, intended use.
- `datasets`: purpose, family, target distribution, version, freeze state.
- `dataset_items`: asset, caption, role, selected state, quality metrics, provenance.
- `lora_artifacts`: family, base model, trigger, rank, hashes, status, metrics, active state.
- `generation_recipes`: versioned model/checkpoint/LoRA/pose/prompt settings.
- `assets`: unified image/video metadata, review state, origin, recipe, derivatives.
- `jobs`: one normalized job table.
- `job_events`: progress, warnings, structured errors, logs.
- `campaigns` and `content_items`: briefs, platform variants, schedule, approval.
- `channel_accounts`: encrypted connector configuration and capabilities.
- `fans`, `conversations`, `messages`, `memories`: retain and extend current chat entities.
- `offers` and `unlocks`: simulated first; real external IDs only through connectors.
- `audit_events`: who/what changed state and why.
- `policy_decisions`: age, provenance, platform, content, and publication checks.

### 5.2 Unified state conventions

Use common enums wherever possible.

**Job:** `queued -> claimed -> running -> awaiting_review | succeeded | failed | canceled`

**Asset:** `draft -> approved | rejected -> archived`

**Dataset:** `building -> curating -> frozen -> training -> validated`

**LoRA:** `draft -> training -> ready -> validated -> active | retired`

**Content:** `idea -> generating -> review -> approved -> scheduled -> published | failed`

All transitions must be validated server-side, idempotent, timestamped, and written to `audit_events`.

## 6. Phase 0 — Establish a safe implementation baseline

### Objective

Make future changes reversible and ensure the agent works against the actual v6 source.

### Steps

1. Treat `/data/data_ssd/pigni/ai-influencer/backend-v6` as the only active server codebase.
2. Read the server `AGENTS.md`, README, current Alembic head, Compose file, and startup scripts before editing.
3. Create a branch with the required `codex/` prefix.
4. Back up together:
   - PostgreSQL database;
   - `data/media`, datasets, LoRAs, presets, and workflows;
   - private environment configuration;
   - current ComfyUI workflow files.
5. Record current service, model, and GPU-plan state without storing secrets in Git.
6. Run the existing Python tests, Ruff checks, TypeScript build, and frontend lint.
7. Add a browser smoke test for login and every top-level route.
8. Add a feature flag mechanism for navigation and job-system migrations.

### Acceptance criteria

- A documented backup/restore drill succeeds on a staging copy.
- Baseline tests and build results are recorded.
- No production data is modified by automated tests.
- Existing routes remain usable while new work is feature-flagged.

## 7. Phase 1 — Fix correctness and trust defects

Complete this phase before redesigning the layout.

### Frontend fixes

1. Replace initial empty states with skeleton/loading states on every page.
2. Do not render “0 items” until the relevant request has completed successfully.
3. Fix the v5 browser title/v6 header mismatch.
4. Fix literal `{count}` and `{frames}` placeholders in Video.
5. Fix `NaN GB` with a nullable, formatted model-size field; hide size when unknown.
6. Rename the Images “Photo checkpoint” status filter to “Status.”
7. Resolve the contradictory LoRA availability message in Images.
8. Add a `disabledReason` pattern to all primary actions and show it as helper text/tooltip.
9. Replace opaque icons with labelled buttons or accessible tooltips.
10. Truncate long prompts visually while retaining full text in the inspector.
11. Distinguish generation time from clip duration.
12. Show only eligible approved images in the Video source selector.

### Backend/data fixes

1. Validate counts and formatted labels at API boundaries instead of interpolating raw values in components.
2. Investigate the concatenated-caption dataset item and add a one-item/one-caption invariant.
3. Return structured trainer errors: `code`, `summary`, `remediation`, `technical_details`.
4. Map missing checkpoint errors to a model-management remediation action.
5. Add stable display names to every training job.
6. Add pagination parameters to image library, source assets, LoRA dataset items, videos, and job history.

### Tests

- loading vs empty vs error component tests;
- format tests for counts, frames, sizes, and durations;
- API schema tests for nullable model size;
- regression test for one caption per dataset item;
- route smoke test for all six current tabs.

### Progress log — 14 October 2026 (Milestone A, partial)

Done:
- Frontend: browser title now v6; literal `{count}`/`{frames}` placeholders fixed (double-brace keys);
  `NaN GB` model size fixed (nullable, formatted, hidden when unknown); Images "Photo checkpoint"
  filter renamed to "Status"; Images LoRA contradiction fixed; opaque `⌕`/`≡` icons replaced with
  labelled Open/Select; generation time vs clip duration distinguished in Video cards; Video source
  picker restricted to approved images with a visual preview; loading states (spinner + "Loading…")
  instead of false empty states on Images, Video, Dataset and LoRA; helper text under the primary
  Generate actions explaining why they are disabled.
- Backend: stable training-job display names (`nikita_qwen_fp8`, `... (qwen-image)` instead of
  "Training jobs"); one-caption invariant (captions normalized to a single line on save).
- Tests: 148 passing (caption invariant + job-name fallbacks added); ruff clean; frontend tsc/lint/build clean.

Done (second block):
- **Structured trainer errors** (Phase 1 item): migration `0021_job_error_info`; worker `classify_failure`
  maps failures to `{code, summary, remediation, technical_details}` (`checkpoint_missing`, `gpu_oom`,
  `trainer_assets_missing`, `dataset_too_small`, `trainer_failed`); API stores/returns `error_info`;
  LoRA UI renders code + summary + remediation + collapsible technical details, hides raw log paths;
  `checkpoint_missing` shows an action link to model management. Live-verified (checkpoint deleted
  after QA job → `checkpoint_missing` shown).
- **Pagination** (Phase 1 item): `limit`/`offset` on library items, training jobs, videos, dataset
  images; "Load more" buttons in Images, Dataset, Video and LoRA job list (dedup + auto-hide).
- **UI primitives** (Phase 2 start): `components/ui/AsyncBoundary.tsx` (loading/empty/skeleton-grid
  boundary) and `components/ui/StatusBadge.tsx`; adopted in Images, Video, Dataset grids and LoRA
  job badges; skeleton-card CSS.
- **API smoke test** for every tab (`tests/test_smoke_tabs.py`); suite now **149 passing**; ruff,
  tsc, lint, build clean; deployed and verified.
- **Phase 2 slice — shared shell**: `ui/AppHeader.tsx` (single sticky topbar + nav with
  `aria-current`, replaces the six duplicated headers in Chat/Images/Video/Dataset/LoRA/Home),
  `ui/Banner.tsx`; CSS design tokens (spacing/type/surfaces/borders/status) used by the new
  primitives.
- **Phase 2 primitives**: `ui/EmptyState` (adopted in Images/Video/Dataset/chat memories) and
  `ui/JobProgress` (ARIA progressbar for running training jobs).
- **Frontend test runner**: vitest + Testing Library (`npm test`, jsdom); first component tests for
  AsyncBoundary/StatusBadge/JobProgress/AppHeader/Banner (11 tests). Destructive confirmation copy
  sharpened (character delete lists LoRA/datasets/jobs/artifacts; dataset delete notes published LoRAs).
- **`ui/PageHeader`** extracted and adopted in Chat/Images/Video/Dataset/LoRA (eyebrow/title/subtitle
  + right-hand slot), removing the last duplicated page header markup.
- **`ui/DangerZone`**: character deletion moved out of the avatar action row into a labelled danger
  zone with explicit consequence copy (chats, memories, LoRAs, datasets, jobs, artifacts).
- **Regression test for structured errors**: LoraPlayground renders code summary + remediation +
  model-management link and keeps raw log paths behind the details disclosure (mocked api).
- **Effective-recipe summaries**: the collapsed Advanced sections in Images and Video now show
  style/checkpoint/LoRA count/pose count/seed (Images) and resolution/frames/steps/LoRA/seed (Video).
- **`ui/AdvancedSettings`** primitive adopted by the Images and Video advanced sections (title +
  live effective-recipe summary).
- **Dataset queue progress**: spinner banner with imported/classified counters while a source is
  active, plus a ready/pending/failed summary line once it settles.
- **Home operational overview**: `GET /api/overview` (draft images/videos, running/failed jobs,
  ready LoRAs, characters) and a "Needs attention" section on Home linking to the right tab;
  live-verified (4 characters, 126 draft images, 11 failed jobs).
- **Video review states**: `videos.review_status` (draft/approved/rejected, migration `0022`;
  existing clips backfilled to approved), `PATCH /api/videos/{id}` + `review_status` list filter,
  StatusBadge + Approve/Reject on video cards. Live-verified (patch, filter, restore); 150 tests.
- **LoRA workflow readiness line** (character / selected dataset images / ready LoRAs / active LoRA)
  and **job history declutter**: older failed/cancelled jobs collapse behind "Show all jobs (+N)",
  always keeping the latest failure per LoRA visible.
- **Backend messages are English at the source** (~100 user-facing strings across `app/` and the
  trainer worker translated; the legacy it/en shim stays as a compatibility passthrough). Tests
  updated to the English copy; live-verified `/api/characters/does-not-exist` -> "Item not found"
  without any language header.

Remaining in Phase 1: no false zeros/placeholders left in the audited set — kept under watch;
component-test coverage to grow beyond the shell primitives.

### Acceptance criteria

- No known false-zero, placeholder, `NaN`, or contradictory status remains.
- Every disabled primary action explains the unmet prerequisite.
- Technical errors have a concise operator-facing summary.

## 8. Phase 2 — Introduce the shared design system and ergonomic shell

### Steps

1. Define tokens for spacing, type, surfaces, borders, focus, status, and tab accents.
2. Create shared primitives:
   - `PageHeader`;
   - `CharacterContextBar`;
   - `StatusBadge`;
   - `AsyncBoundary`;
   - `EmptyState`;
   - `JobProgress`;
   - `AssetPicker`;
   - `AssetGrid`;
   - `InspectorPanel`;
   - `DangerZone`;
   - `FieldHelp`;
   - `AdvancedSettings`;
   - `ErrorSummary`.
3. Make the global header and context bar sticky.
4. Standardize page structure: navigation rail, workspace, inspector.
5. Use resizable panels only where state is remembered and keyboard alternatives exist.
6. Move destructive controls into menus or danger zones and add precise confirmation copy.
7. Add responsive behavior for 1280, 1440, and ultrawide screens.
8. Add keyboard navigation, visible focus, and descriptive accessible names.
9. Preserve the useful color accents but do not use color alone to convey status.

### Acceptance criteria

- All pages use the same async, status, error, and destructive-action patterns.
- The main action and current character are always visible.
- The full normal workflow is usable at 1280 px without horizontal page scrolling.

## 9. Phase 3 — Build a unified persistent job system

Progress log — 14 October 2026 (first slice):
- Tables `execution_jobs` + `job_events` (migration `0023`; the legacy v1 `jobs` table used by the
  dead content-jobs pipeline is untouched). Fields: type, state, character/dataset/asset scope,
  progress current/total/unit, worker, GPU, heartbeat, idempotency key, error_info
  (code/summary/remediation/technical_details), cancel_requested, retry_of, timestamps.
- `app/jobs.py` service: create (idempotent), start, progress+heartbeat, finish, cancel request,
  retry linkage, per-type stale-heartbeat policy + `recover_stale`.
- API: `GET /api/jobs` (state/type/character filters + limit/offset), `/api/jobs/summary`,
  `/api/jobs/{id}`, `/api/jobs/{id}/events`, `POST .../cancel`, `POST .../retry`.
- Producers wired: training jobs mirror queue/claim/progress/complete/cancel into the unified job
  (external_id = training job id); video generation records start/success/failure with structured
  errors.
- Frontend: job tray in the header (active spinner count + failed badge, 5 s poll) and a
  **Jobs & System** page (`/jobs`) with filters, compact rows, progress bars, cancel/retry and
  events behind a Technical details disclosure. 153 backend tests + 13 frontend tests; live-verified
  endpoints and migration.

Remaining in Phase 3: SSE for detail views, concurrency limits per GPU/family, orphan-file
reconciliation task.

Progress log — 15 October 2026 (second slice):
- All remaining producers wired into the unified jobs: playground image batches, avatar
  generation/edit, dataset candidates, dataset variations, pose extraction, consistency checks
  (create → start → progress → finish with structured errors; live-verified with a real pose
  extraction -> `pose_extract succeeded 1/1`).
- Jobs page auto-refreshes every 5 s while any job is running/queued (bounded polling).
- Concurrency + retention: per-character video guard (409 while a video job is active for the
  character), finished jobs auto-pruned after 30 days (events included) from the summary endpoint.
  Tests added (prune, guard); 155 backend tests.
- Orphan reconciliation: `POST /api/system/reconcile` (report, or delete with `?delete=true`)
  removes media files nobody references that are older than 24 h; button + result in the Jobs page.
  Test added. Phase 3 acceptance met: every long-running operation is in one job list, refresh keeps
  progress (SPA fallback + persistent jobs), cancel/retry auditable, old failures do not dominate.
- **SPA fallback**: direct loads/refreshes of `/images`, `/video`, `/dataset`, `/loras`, `/jobs` now
  serve the SPA (registered after all API routes so endpoints keep returning JSON) — refreshing a
  page no longer 404s.

### Why first

Images, video, imports, classification, consistency checks, and training all have long-running behavior but currently expose different progress models. A common orchestrator is required before further automation.

### Backend steps

1. Add/normalize `jobs` and `job_events` with:
   - job type;
   - workspace/character/dataset/asset scope;
   - state;
   - progress current/total/unit;
   - queue position;
   - worker and GPU;
   - heartbeat;
   - request idempotency key;
   - error code/summary/remediation/detail;
   - cancellation request;
   - retry source;
   - created/started/finished timestamps.
2. Refactor current worker and trainer updates through a shared job service.
3. Keep domain tables as the source of domain state, with jobs recording execution state.
4. Add stale-heartbeat detection and explicit recovery policy per job type.
5. Add server-sent events or bounded polling for updates.
6. Add concurrency controls per GPU/model family.
7. Make retry create a new linked attempt, never overwrite the original.
8. Add a reconciliation task for orphaned files and incomplete records.

### API

- `GET /api/jobs?state=&type=&character_id=&cursor=`
- `GET /api/jobs/{id}`
- `GET /api/jobs/{id}/events`
- `POST /api/jobs/{id}/cancel`
- `POST /api/jobs/{id}/retry`

### Frontend

1. Add a global job tray with active count and failures.
2. Add a Jobs & System page with filters and compact rows.
3. Show inline progress where a job was started.
4. Put raw logs behind an explicit “Technical details” disclosure.

### Acceptance criteria

- Every long-running operation appears in one job list.
- Refreshing or restarting the UI does not lose progress.
- Cancel/retry behavior is consistent and auditable.
- Old failed jobs do not dominate normal creative screens.

## 10. Phase 4 — Character foundation and identity intake

Progress log — 15 October 2026 (first slice):
- Character policy fields: `age` (validated 21-99), `synthetic_declared`, `provenance`
  (original/synthetic/consented) — migration `0024`, schemas, create/update/clone and output.
- Character editor UI: adult-age field, provenance select and the synthetic/consented-likeness
  declaration checkbox; `(copia)` clone suffix fixed to `(copy)`. Test added (age validation +
  update); live-verified (migration 0024 applied, characters expose the fields).
- Home "Needs attention" now flags characters missing policy details (adult age / declaration) and
  links to the editor; `/api/overview` exposes `characters_incomplete`.
Progress log — 15 October 2026 (slice 3):
- Identity intake from upload: `POST /api/characters/{id}/avatar/upload` (base64, PNG/JPEG/WebP,
  max 12 MB, min 512 px short side) validated with the local vision model (adult 21+, exactly one
  person, face visible, sharp); rejected uploads explain why; accepted ones store the anchor hash
  and a validation record (`avatar_validation`, migration `0035`) + audit event. "Upload photo"
  button with validation display in the LoRA tab. Tests added; live-verified with the real model.
- Remaining in Phase 4: local face embeddings (needs a face model download).
- Identity provenance (slice 2): `source_category` (generated/owned/consented/reference_only),
  rights notes, source reference/hash, permitted uses, lifecycle state and `avatar_sha256`
  (migration `0025`); reference-only characters cannot generate/edit an avatar (anchor guard, API
  + UI); avatar hash stored on every generation/edit. Editor UI updated (source category, rights,
  permitted uses, lifecycle, warning). Test added; live-verified.

### Character schema

Add required fields:

- display name;
- explicit adult age, minimum 21 for product policy;
- synthetic/consented-likeness declaration;
- source/provenance status;
- physical identity description;
- personality and voice;
- boundaries and prohibited topics;
- image style defaults;
- chat and monetization policy;
- platform profile copy;
- lifecycle state.

### Identity intake workflow

1. The operator creates a character or chooses “Start from one reference.”
2. The UI requires the source category:
   - generated synthetic image;
   - owned self-image;
   - licensed/consented adult model;
   - reference-only inspiration.
3. Store rights notes, source URL/file hash, permitted uses, expiry if any, and reviewer.
4. Validate image resolution, face count, occlusion, sharpness, and adult-age policy.
5. Generate a normalized identity crop and face embedding locally.
6. Display the anchor, crop, quality results, and provenance before continuing.
7. Reference-only material must never be selectable as an identity anchor.

### Acceptance criteria

- A character cannot enter identity generation without adult-age and provenance decisions.
- Every anchor has a stable hash and audit record.
- Face embeddings never leave the local system.

## 11. Phase 5 — One image to multi-angle canonical identity set

This phase implements the first part of the requested LoRA workflow.

### Generation matrix

Create a versioned angle template. Begin with 18–24 candidates:

- front neutral;
- yaw ±20°, ±40°, ±60°, and profile ±90°;
- three-quarter left/right;
- slight pitch up/down;
- neutral and slight smile;
- controlled studio light plus one natural-light set.

Keep hair, age, skin features, and identity descriptors fixed. Vary only angle/expression/light according to the template. Use the strongest locally available identity-preserving edit/reference model, with deterministic seed families and recorded recipe versions.

### Candidate scoring

For each output, compute and store:

- face-embedding similarity to the anchor;
- face detection confidence;
- landmark/pose estimate;
- blur and resolution quality;
- occlusion;
- artifact/anatomy score where available;
- perceptual similarity to detect duplicates;
- requested-angle accuracy.

The AI may rank candidates, but the operator must approve the canonical set.

### Review UI

1. Show the anchor fixed on the left.
2. Group candidates by requested angle.
3. Provide side-by-side and overlay/face-crop comparison.
4. Display identity score and quality warnings, with thresholds explained.
5. Let the operator Accept, Reject, Regenerate, or Mark uncertain.
6. Require a balanced canonical set of 6–10 references:
   - close front;
   - left/right three-quarter;
   - left/right profile;
   - upper body;
   - at least one full body.
7. Freeze the canonical set as an immutable version.

### Proposed API

- `POST /api/characters/{id}/identity-runs`
- `GET /api/identity-runs/{id}`
- `PATCH /api/identity-candidates/{id}`
- `POST /api/identity-runs/{id}/regenerate`
- `POST /api/identity-runs/{id}/freeze`

Progress log — 15 October 2026 (slice 1):
- Backend: versioned angle template (18 angles, template v1), `identity_runs` + `identity_candidates`
  (migration `0026`), run creation via Qwen-Image-Edit with deterministic seed family and recorded
  anchor hash/recipe, `PATCH` candidate review, `freeze` with balance check (6-10 accepted + required
  roles, explicit override reason). Job type `identity_run` recorded. 4 tests.
- UI: Identity set panel in the LoRA tab (generate, candidates grid with accept/reject/uncertain,
  freeze + override reason); live-verified endpoints; real generation intentionally left to the user.
- Candidate scoring: each candidate is scored against the anchor with the local vision model
  (similarity, same_person, angle accuracy, quality notes), stored in `scores` and shown on the
  review cards (flagged below 60 / different person); mocked in tests.
- Regenerate endpoint (`POST /api/identity-runs/{id}/regenerate`): rejected/uncertain candidates (or
  explicit ids) get fresh seeds as new candidates, old ones marked `replaced`, replacements scored;
  accepted candidates blocked; frozen runs immutable. UI button in the panel. 5 tests.
- Overlay comparison: "Overlay anchor" toggle blends the anchor over every candidate thumb for
  side-by-side review.
- Remaining: face-embedding similarity, requested-angle check via pose.

### Acceptance criteria

- Every candidate can be traced to anchor, template, model, seed, and recipe.
- The UI prevents freezing an unbalanced set without an explicit override reason.
- Accepted identities meet configured similarity/quality thresholds or have a recorded human override.

## 12. Phase 6 — Build the 60-image training dataset

### Dataset workflow redesign (DISCUSSION OPEN — 16 October 2026)

Goal: the **initial LoRA dataset must be built starting from the profile picture (anchor)**, not
from plain text-to-image. Today it does not behave that way:

- `generate_dataset_candidates` calls `generate_image(...)` with the anchor as `reference_path`, but
  for the diffusion families (`qwen-image`, `z-image`, `flux2`) the reference is **ignored** in
  `generate_image` (only `playground` uses IPAdapter; SDXL `real/pony/anime` uses the IPAdapter
  reference workflow). So with a Qwen checkpoint the candidates are pure txt2img: identity is lost.
- The identity-preserving paths that DO start from the anchor are **Variations** and the
  **Identity set** (Qwen-Image-Edit from the anchor / canonical references).

First slice implemented (16 October 2026):
- `DatasetGenerate.reference_mode` (`auto`/`edit`/`txt2img`): with `auto`, a **qwen-image** dataset
  generates candidates by **editing from the canonical reference/anchor** (Qwen-Image-Edit,
  identity-preserving) instead of text-to-image; SDXL keeps the IPAdapter path. The job message
  records the mode; `edit` is rejected for non-qwen families; missing anchor is rejected.
- Fixed a blocker: `DatasetCreate.family` now accepts `qwen-image` (qwen datasets could not be
  created via the API) and the dataset creation UI has a family selector (was hardcoded to `real`).
- Tests added.

LoRA dataset redesign (16 October 2026, implemented):
- Step 1 **Canonical references**: 7 role sets (close face, 3/4 face, profile, upper body, front/3-4/
  side full body), **4 images per role** generated by editing the profile picture; **insightface**
  (buffalo_l, local CPU) scores each image against the anchor and the top 2 are marked
  recommended; selection is always manual; each role's photos appear inline under its button.
  (`POST /api/datasets/{id}/references`)
- Step 2 **Pose variations**: fixed standard poses (standing, walking, sitting, leaning, lying,
  looking back), 4 per pose, edited from the **selected canonical references**, scored against the
  selected close-face reference (fallback anchor) with the same recommendation. (`POST
  /api/datasets/{id}/pose-variations`)
- Step 3: LoRA creation/training with the selected photos (existing flow).
- Panel rewritten: 3 steps, role/pose galleries with similarity badges and ★ recommendations,
  SDXL candidate step and old variations step removed; family selector on creation.
- insightface + onnxruntime added (models in `data/insightface`, `libgl1/libxcb1` in the image);
  live-verified: 4 close-face refs in 124 s with scores, 2 pose variations in 46 s.

Decisions (16 October 2026):
- A frozen identity set is **required** before generating dataset images; dataset images are
  generated by **editing the accepted identity photos** (face + body) — no text-to-image for scene
  variety. SDXL is out of scope for now (the user does not use it); pose variety comes from the
  scene prompts and the canonical angle coverage (ControlNet is not used with Qwen-Edit).
- Implemented: dataset generation requires a frozen identity run (400 with remediation otherwise);
  references come from the frozen run's accepted candidates (ordered body > three-quarter > close-up,
  max 8, anchor fallback if files are missing); qwen-image always edits from those references; the
  dataset creation UI gained a family selector and a gate warning that disables generation until an
  identity set is frozen. Tests updated (40 in test_lora).

Open questions for the redesign:
1. Default the dataset generation to an Edit-based flow (Qwen-Image-Edit from a canonical
   reference) instead of txt2img candidates? Keep txt2img only as a secondary "scene variety" tool?
2. For SDXL families: keep IPAdapter candidates (with pose/ControlNet) and require a frozen
   canonical identity set as the reference source?
3. Should the flow enforce the sequence anchor → identity set (frozen) → dataset generation, with
   the dataset generator refusing to start without canonical references?
4. How to cover pose/angle variety in the Edit flow (prompt-driven angles vs. canonical set
   coverage vs. ControlNet where available)?
5. Should the blueprint categories drive the scene list automatically (fill-the-gap generation)?

### Dataset blueprint

Generate 70–90 candidates and curate to 50–70. Default target: 60 selected items.

Suggested selected distribution:

| Category | Target |
|---|---:|
| Close face and head/shoulders | 12 |
| Three-quarter/profile portraits | 8 |
| Upper body | 10 |
| Full body front/side/back | 15 |
| Seated, walking, leaning, dynamic poses | 8 |
| Lifestyle/environment diversity | 7 |

Across the set, balance:

- expressions;
- camera distance and focal feel;
- indoor/outdoor locations;
- day/night and light direction;
- outfits without changing core identity;
- standing, seated, walking, athletic, candid, and formal poses;
- SFW and adult content as separate labelled subsets, never mixed invisibly.

### Pose-dataset use

External datasets are pose/style sources, not identity sources by default.

1. Import with provenance and intended-use metadata.
2. Detect duplicates and low-quality files before classification.
3. Extract DWPose/OpenPose skeletons and crop/framing metadata.
4. Remove or block source-person identity features from the generation path.
5. Store a reusable pose record with source attribution.
6. Generate the synthetic character using canonical identity references plus the pose skeleton.

### Automated quality control

Run after every candidate batch:

- face identity similarity;
- duplicate/near-duplicate clustering;
- requested pose match;
- caption/image agreement;
- face/hand/anatomy artifact detection;
- age-policy check;
- blur/upscale detection;
- distribution coverage;
- train/validation leakage detection.

### Curation UI

1. Replace one giant page with a dedicated dataset route.
2. Use virtualized grid and keyboard review shortcuts.
3. Provide filter chips: angle, crop, pose, scene, outfit, subset, score, warning.
4. Show distribution bars and missing-category warnings.
5. Make captions editable in a selected-item inspector, not inline on every card.
6. Provide AI-suggested selection, but require final human freeze.
7. Hold back 8–12 validation prompts/images that are never used for training.

### Acceptance criteria

- A frozen dataset has 50–70 selected items, a balanced distribution, and no unresolved critical warning.
- Every item has one caption, one provenance chain, and stored QC metrics.
- Validation items are separate from the training set.

## 13. Phase 7 — LoRA training, evaluation, and activation

Progress log — 15 October 2026 (first slice):
- Validation grid (`POST /api/loras/{id}/validation`): seven fixed prompts (close face, profile,
  upper body, full body, two lifestyle scenes, one difficult pose) rendered with the trained LoRA
  before activation, stored as draft library images tagged `validation` + LoRA file; recorded in the
  unified jobs (`lora_validation`). "Validate" button on ready LoRAs; test added.
- Also this block: dataset blueprint (`GET /api/datasets/{id}/blueprint`) with per-category targets
  (close face 12, three-quarter/profile 8, upper body 10, full body 15, dynamic 8 of 60) shown in
  the dataset panel; test added.
- Preflight (`GET /api/loras/{id}/preflight`): checkpoint presence/family, run conflicts, trainer
  busy/stale, dataset size + trigger-in-captions, disk space — rendered as a remediation checklist in
  the queue panel. Activation gate: successful training no longer auto-activates; the operator
  validates and activates explicitly (tests updated). Test added.
- Rollback: activation records `previous_active_id` (migration `0027`); `POST /api/loras/{id}/rollback`
  re-activates the previous artifact (toggle-safe) with a Rollback button on the active LoRA; test added.
- Traceability hashes: every queued job stores `spec_sha256` (canonical training spec) and every
  completed artifact stores `artifact_sha256` in the LoRA metrics/job params. Test added.
- Auto-recommended hyperparameters (`GET /api/loras/{id}/recommendation`): rank/steps/LR/resolution/
  repeats from family and dataset size with a rationale string; test added. UI prefill next block.

### Preflight

Before Queue training, validate:

- base checkpoint exists in the expected model directory;
- trainer and dependencies are healthy;
- dataset is frozen;
- trigger appears correctly in captions;
- requested family matches the checkpoint;
- disk and VRAM estimates fit;
- no existing active run conflicts.

Show failures as remediation cards, not filesystem exceptions.

### Training

1. Create an immutable training specification.
2. Auto-recommend rank, alpha, steps, learning rate, resolution, and GPU from family and dataset size.
3. Preserve Expert override controls.
4. Stream step, loss, ETA, GPU, and checkpoint events through the unified job system.
5. Save intermediate samples at configured intervals.
6. Make cancel terminate the whole process group and mark artifacts incomplete.
7. Hash and register the final safetensors file.

### Evaluation gate

Do not auto-activate immediately after successful training.

1. Render a fixed validation grid across:
   - close face;
   - profile;
   - upper body;
   - full body;
   - two lifestyle scenes;
   - one difficult pose;
   - one adult-content prompt if that subset is enabled.
2. Compare candidate LoRA against the active LoRA and no-LoRA baseline.
3. Compute identity, prompt adherence, artifact, and diversity metrics.
4. Present a blind A/B review when possible.
5. Let the operator Validate & Activate, Keep inactive, or Reject.
6. Keep rollback to the previous active artifact.

### Acceptance criteria

- Missing models are detected before a job is queued.
- Successful training always produces a validation report.
- Activation is explicit and reversible.
- Raw logs remain accessible but collapsed.

## 14. Phase 8 — Redesign the image studio and asset library

Progress log — 15 October 2026 (first slice):
- **Review mode** in the Images page: Grid/Review switch, large stage with previous/next, filmstrip,
  keyboard shortcuts (←/→ navigate, A approve, R reject, 1-5 rating, O anchor overlay, Esc back),
  anchor overlay comparison, caption and status/rating controls. Reuses the library filters.
- **Trash (soft delete)**: `POST /api/library/{id}/trash` + `/restore`, `?trash=true` listing,
  `deleted_at` (migration `0028`); trashed assets are excluded from generation pickers, dataset
  references, consistency checks and chat scene matching; Trash tab in the library with Restore and
  Delete forever. Test added.
- Remaining: Generate/Review/Library mode split with saved filters, duplicate clustering,
  virtualization, effective-recipe line before submission (partially done).

### Page structure

Use three modes under Studio:

1. **Generate** — recipe builder and batch submission.
2. **Review** — fast approve/reject/compare workflow.
3. **Library** — search, metadata, usage, collections, archive.

### Generation recipe

The normal form should show:

- campaign/brief or free prompt;
- character identity version;
- preset;
- checkpoint;
- active character LoRA;
- pose;
- count and aspect ratio;
- Generate.

Advanced controls contain negative prompt, additional LoRAs, CLIP weights, sampler, steps, CFG, seed, ControlNet strength, and model-specific options.

Always show a compact “Effective recipe” before submission.

### Review mode

- one large selected image plus a filmstrip/grid;
- compare to identity anchor and sibling generations;
- keyboard shortcuts for approve/reject/rating;
- AI consistency and artifact warnings;
- edit caption/tags in inspector;
- regenerate with one changed parameter;
- promote to campaign or send to video.

### Library

- cursor pagination and virtualization;
- saved filters and collections;
- provenance, recipe, usage history, derivatives;
- soft-delete to Trash with restore;
- bulk approve/reject/archive/export;
- duplicate clustering.

### Acceptance criteria

- A library with 10,000 assets remains responsive.
- An operator can review a 20-image batch without repeated scrolling.
- Every approved asset has a complete reproducibility record.

## 15. Phase 9 — Redesign video production

Progress log — 15 October 2026 (second slice):
- ETA on job progress: rate-based estimate shown for running jobs (Jobs page and LoRA training rows).
- Large-grid virtualization: `content-visibility: auto` + intrinsic sizes on library/video/dataset/
  identity cards (offscreen cards skip rendering).
- Video review filter (draft/approved/rejected) in the video toolbar (server-side), honored by
  Load more.
- First/last-frame support for LTX models: optional last-frame picker in the video form
  (`last_image_id`), `LTXVAddGuide` with `frame_idx=-1` in the graph (decoder/save nodes untouched),
  `last_frame` recorded in params; graph + API tests; live-verified with a real 84 s generation.


Progress log — 15 October 2026 (first slice):
- Model capability cards replace the model select (FPS, I2V+T2V, step range, LoRA notes);
  duration expressed in seconds first, frames second (select + effective-recipe summary);
  motion preset chips (subtle portrait, turn to camera, walking, hair/wind, camera push, orbit)
  append to the prompt. Source preview and approved-only picker were already in place.
- Params now store fps/frames/duration (cards use them); duplicate detection in the library
  (exact phash grouping, "Duplicates (N)" filter + per-card ×N badge).
- Bulk review: `POST /api/library/bulk-status` + bulk Approve/Reject/Draft in the selection bar
  (test added); always-visible effective-recipe line before Generate (Images and Video).
- Content policy metadata: `policy` JSON on library images and videos (age-safety enforced, adult
  only, timestamp) recorded at generation (migration `0029`), exposed in the API.
- Collections (migration `0030`): `GET/POST /api/collections`, add/remove items, delete; library
  filter by collection; bulk "Add to collection" in the selection bar. Test added.

### Steps

1. Replace the HTML select with the shared visual Asset Picker.
2. Default to approved character assets; allow drafts only through an explicit filter.
3. Show the selected source frame next to the motion prompt.
4. Add model capability cards for aspect ratio, FPS, frames, duration, I2V/T2V, and LoRA compatibility.
5. Express duration primarily in seconds and secondarily in frames.
6. Add motion presets: subtle portrait, turn to camera, walking, hair/wind, camera push, orbit.
7. Add first-frame/last-frame support when the selected model can use it.
8. Use the unified job system for queue, ETA, progress, cancel, retry, and errors.
9. Add review states and approved-video library collections.
10. Store poster, recipe, source asset, family, model, seed, FPS, duration, and content policy result.

### Acceptance criteria

- No ineligible asset appears as a disabled wall of options.
- Source, motion, duration, and model are visible before submission.
- A generated video must be reviewed before becoming chat/publishing eligible.

## 16. Phase 10 — Conversation simulator and content offers

Progress log — 15 October 2026 (second slice):
- Per-conversation PPV override (migration `0034`): conversation-level enable/disable and price
  falling back to the character defaults, editable in the chat rail; PPV defaults moved to the
  character editor (Monetization section). Effective PPV is used for chat photos and PPV videos.
  Test added.
- Rail/inspector split (lean): the character settings (style, checkpoint, PPV override, realism,
  activity hours) moved from the left rail into a collapsible section of the right inspector; the
  rail now holds character selection, fan and conversation lists.
- Structured proposals (first slice): the PPV marker can propose a price
  (`[PPV: price=12.50; <prompt>]`); the proposal is recorded in the message metrics
  (`proposal: {kind, locked, price_cents}`) and used for the locked photo when valid. Parsing and
  integration tests added.
- Follow-up scheduling from proposals: `[FOLLOWUP: 3h]` (15m-72h) schedules one re-engage via the
  scheduler; shown as a chip in the transcript. Parsing + scheduling tests added.
- Asset composer completed: the chat can also send a reviewed library video
  (`POST /api/conversations/{id}/video`, approved clips only, optional PPV price) with a picker modal;
  test added.
- Remaining: full routing split.

Progress log — 15 October 2026 (first slice):
- Conversation state chip in the Chat heading: No chat selected / Generating reply (with seconds) /
  Waiting for reply (with seconds) / Active — derived from conversation, busy and pending replies.
- Asset composer: the chat photo modal can now send an approved library photo (source picker;
  backend `library_id` already supported), or generate a new one. 
- **Policy validation** on outbound chat text (`app/policy.py`): hard block for underage references,
  soft block for child/kid/minor/teen terms combined with sexual content; blocked replies are
  replaced with a policy message and flagged in the message metrics. Unit + integration tests.
- Remaining: rail/inspector split, structured assistant proposals.

### UI redesign

1. First rail: fans/inboxes and conversation list.
2. Center: transcript and composer.
3. Right inspector: character version, memory, timing, model, policy, and assets.
4. Move personality editing to Character, with a link from Chat.
5. Move PPV defaults to Character/Monetization; keep a per-conversation override in the inspector.
6. Show conversation state clearly: no chat selected, creating, waiting, scheduled reply, failed, active.
7. Add an asset composer with approved photos/videos and generation requests.

### Backend workflow

1. Normalize inbound events into one conversation schema.
2. Build prompt context from character version, fan memory, recent messages, policy, and eligible assets.
3. Produce a structured assistant proposal:
   - text bubbles;
   - suggested asset IDs or generation request;
   - optional offer price;
   - follow-up schedule;
   - confidence and policy flags.
4. Keep the current injection guard and extend it to connector-provided text.
5. Run policy validation before saving/sending.
6. In assisted mode, show Draft -> Edit -> Approve & Send.
7. Keep simulation and real connectors clearly labelled and technically separate.

### Monetization rules

- use configurable price bands and rate limits;
- never fabricate payment confirmation;
- do not pressure after refusal;
- do not repeatedly gate normal conversation behind payment;
- keep an audit trail of offers and unlocks;
- make real payment state authoritative only from the platform connector.

### Acceptance criteria

- The simulator remains usable with no external platform connected.
- Real outbound messages cannot be confused with simulated ones.
- Every outbound proposal is tied to the exact character version and policy decision.

## 17. Phase 11 — Campaigns, Instagram, and Fanvue adapters

Platform APIs and policies change. Before implementation, the agent must verify current official documentation and supported account capabilities. Do not hard-code assumptions from this plan.

### Common connector interface

Define an adapter contract:

- `connect()` / `refresh_credentials()`;
- `capabilities()`;
- `publish_media()`;
- `schedule_media()` when supported;
- `list_inbox_events()`;
- `send_message()`;
- `list_metrics()`;
- `webhook_verify()` and `webhook_ingest()`;
- idempotency and external-ID mapping.

Store secrets encrypted and never return them to the browser.

### Campaign workflow

1. Create a campaign with theme, audience, platforms, date range, tone, and content mix.
2. Generate a shot list and caption variants locally.
3. Produce image/video candidates.
4. Review media, caption, alt text, disclosure, tags, and platform crop.
5. Run platform and policy checks.
6. Approve and schedule/publish.
7. Record external IDs and immutable published snapshots.
8. Import metrics and link them back to recipe, character, and campaign.

### Rollout

1. Export package only: media + captions, no publishing.
2. Sandbox/test account connector.
3. Manual approval for every post/message.
4. Batch approval with limits.
5. Optional constrained automation only after monitoring and rollback are proven.

### Acceptance criteria

- Publishing is idempotent and cannot duplicate a post on retry.
- Connector failure never marks content as published without an external ID.
- Platform and simulation environments are unmistakable.

## 18. Phase 12 — Policy, provenance, and security

Progress log — 15 October 2026 (first slice):
- Content policy metadata on assets (age safety enforced, adult only, timestamp).
- **Audit log** (`audit_events`, migration `0031`): library approve/reject (single + bulk), trash,
  restore, delete-forever, video review, LoRA activate/rollback, identity freeze with override
  reason; `GET /api/audit` with filters. Test added.
- Content labels on images and videos (migration `0032`), editable in Review mode and on video
  cards.
- Failed-attempt limiter: 30 bad API-key attempts per minute from one IP → 429 for 5 minutes
  (per-IP block, cleared by a valid key before the threshold); test added.
- Trash retention: `POST /api/system/purge-trash?days=30` permanently deletes trashed assets
  older than the window (rows + files, dataset/video references cleaned) with a button on the Jobs
  page; test added.
- "Empty trash now" button in the Trash tab (`days=0` purge, with confirmation); test extended.
- Session security: API key stays in sessionStorage with a 12 h expiry (cleared on expiry/logout);
  key rotation supported via `API_KEY_PREVIOUS` (old key keeps working while clients migrate).
  Test added.
- Per-platform policy checklists (migration `0033`): platforms in use + AI disclosure / terms /
  content-rules checks per platform, edited in the character editor with a publish warning when
  disclosure is missing. Test added.
- Home "Needs attention" flags characters publishing without AI disclosure (`characters_undisclosed`
  in `/api/overview`).
- Policy blocks are recorded in the audit log (`chat.policy_block` with the matched rules); test
  extended.
- Remaining: roles, per-conversation PPV override.
- Audit UI: recent actions list on the Jobs & System page (time, action, object, counts).
- Content labels (`sfw`/`suggestive`/`explicit`, migration `0032`) on library images and videos,
  editable in Review mode (select) and via `PATCH /api/library/{id}` / video review; badge in cards.
  Test added.

### Required controls

1. Require adult age and synthetic/consented identity status.
2. Add source rights, license, consent, intended use, and expiry fields.
3. Block identity training from reference-only collections.
4. Keep minors and ambiguous-age content out of import promotion, training, generation, and publishing.
5. Add content labels: SFW, suggestive, explicit; apply separate storage/access/review policies.
6. Add audit logs for approvals, overrides, publication, deletion, and connector actions.
7. Encrypt connector credentials and private configuration.
8. Add user roles before remote or shared access: Admin, Creator, Reviewer, Operator.
9. Add session expiry and key rotation; stop storing a long-lived shared API key in normal browser storage.
10. Add rate limits and CSRF/origin protection appropriate to the deployment model.
11. Add backup, retention, trash, restore, and secure-delete policies.
12. Add per-platform policy checklists and disclosure settings.

### Acceptance criteria

- Every training and published asset has a complete provenance chain.
- A policy block cannot be bypassed without an explicit role, reason, and audit event.
- Secrets and face embeddings are not exposed through normal API responses or logs.

## 19. Phase 13 — Observability, quality, and operations

Progress log — 15 October 2026 (first slice):
- Jobs page shows recent failures grouped by error code (not raw exceptions); `errors_by_code` in
  `/api/jobs/summary`.
- `GET /api/metrics`: jobs by state/type with average queue and run times, library approval rate,
  video review counts, dataset coverage, identity runs, characters with ready LoRAs. Smoke test
  covers the endpoint.
- Storage usage in `/api/metrics` (media files/bytes, disk free) and in the Jobs metrics strip.
- Model registry check (LoRAs with a missing checkpoint) and backup status (last `.tgz` in
  `backups/`, mounted read-only into the container) in `/api/metrics` + Jobs strip.

### Metrics

- queue time and run time by job/model;
- success/failure/cancel rate;
- GPU utilization and out-of-memory failures;
- asset approval rate;
- identity-consistency distribution;
- dataset coverage and duplicate rate;
- LoRA validation scores;
- content reuse and derivative counts;
- message latency and intervention rate;
- connector delivery and publishing failures.

### Operational screens

- service health with actionable remediation;
- active workload by GPU;
- stuck jobs;
- storage usage and orphaned files;
- model registry and missing dependency checks;
- recent errors grouped by error code, not raw exception;
- backup status.

### Acceptance criteria

- An operator can identify the cause and remediation of a failed job without reading a stack trace.
- Alerts are deduplicated and tied to a domain object.
- File/database reconciliation can run safely in dry-run mode.

## 20. Frontend implementation map

Progress log — UI modification plan (16 October 2026, first hour):
- **P0**: fixed the untranslated `jobs.state.active` label and the `{imported}` placeholder in the
  dataset classifying progress; header/tray semantics unified (tray badge = "N jobs need attention"
  when failures exist, otherwise "N jobs running"); route scroll reset on navigation
  (`RouteScrollReset` in `App.tsx`); compact 58 px header with an account menu (Logout + nav on
  narrow screens); bulk toolbar in Images appears only with a selection.
- **Responsive foundation**: `useMediaQuery` hook, `InspectorDrawer` primitive, breakpoint CSS
  (below 1280 px workspaces stack instead of clipping; nav collapses below 1024 px; panel resizers
  hidden).
- **Phase 3 migrations**: Images generator, Video generator, LoRA guide and Dataset details are now
  drawers below 1280 px (single instance via conditional render, Escape closes, focus moves into the
  panel); LoRA guide column no longer duplicates a close control.
- **Density/polish**: humanized durations (`formatDuration`: `3h 31m`, `2m 1s`, `18s`) in Jobs and
  LoRA ETAs and metrics; failure chips show readable error labels with the raw code in the tooltip;
  Home attention items are compact clickable cards; GPU process lists collapsed by default; Home
  services/GPUs moved into a remembered "System and infrastructure" section; Purge trash nested in a
  Danger zone; video Delete moved to an overflow menu.
- **ContextSelector** primitive added and adopted in Video (character selector at the top below
  1280 px; the fixed rail is hidden there). Jobs KPI strip restyled as labelled cards; chat empty
  state compact with a New chat action.
- Remaining (next hours): CompactToolbar primitive, visual regression pass, Dataset source header
  overflow, Images review refinements, BenchmarkPanel full-width comparison.

Progress log — UI modification plan (16 October 2026, second hour, 18:48-19:05):
- Drawer focus trap (Tab cycling, focus enters the panel) + drawer tests (Escape, focus restore,
  closed state); 16 frontend tests green.
- Images generator: selected LoRAs as removable chips, "Manage LoRAs" disclosure with search; card
  low-frequency actions (classify/trash) moved into an overflow menu.
- `OverflowMenu` primitive extracted and adopted in Images and Video cards.
- LoRA: one stage at a time (stepper) with per-stage next-action hints.
- Jobs: state chips (All/Active/Failed/Succeeded/Canceled), maintenance behind a Maintenance
  disclosure, purge inside the Danger zone.
- Chat: conversations search, compact fan-notes preview, inspector tabs (Character/Memory/Timing),
  review shortcuts behind a help disclosure.
- Dataset: the card thumb selects the item (details) and "+ New source" is now a modal instead of
  occupying rail space.
- Home: compact service pills (auto-fit grid).
- Video: visual source picker (thumbnail grid with search) replacing the long select; review mode
  caption/metadata in an expandable panel; dataset source actions follow the primary/secondary/
  danger hierarchy (Classify primary when pending, Export/Profile/Delete in overflow).
- Performance: `GET /api/library/{id}/thumb` (cached 320 px JPEG) and the Images/Video grids now load
  thumbnails instead of full-resolution files; test added.

Refactor incrementally from the current files.

- `App.tsx`: character-scoped routing, feature flags, global job tray.
- `HomePage.tsx`: Overview first; move deep infrastructure controls to Jobs & System.
- `Playground.tsx`: split character/fan/conversation concerns.
- `ChatPanel.tsx`: transcript/composer only; move settings to inspector.
- `BenchmarkPanel.tsx`: fix metadata formatting; make selection prerequisites explicit.
- `ImagePlayground.tsx`: split into Generate, Review, Library routes/components.
- `VideoPlayground.tsx`: shared Asset Picker and job progress.
- `DatasetPlayground.tsx`: import wizard, provenance, virtualized grid.
- `LoraPlayground.tsx`: routed wizard; remove giant one-page composition.
- `PoseLibrary.tsx`: reference provenance, filtering, preview, usage count.
- `api.ts`: generated or strongly typed API client, structured errors, cursor pagination.
- `i18n.tsx`: enforce complete keys and test placeholder interpolation.

Add directories:

- `components/ui/` for design-system primitives;
- `components/jobs/`;
- `components/assets/`;
- `features/identity/`;
- `features/datasets/`;
- `features/training/`;
- `features/publishing/`;
- `hooks/` for character context, jobs, pagination, and async state.

## 21. Backend implementation map

Keep routers thin and introduce services.

- `services/job_service.py`
- `services/asset_service.py`
- `services/identity_service.py`
- `services/dataset_service.py`
- `services/training_service.py`
- `services/policy_service.py`
- `services/provenance_service.py`
- `services/campaign_service.py`
- `services/conversation_service.py`
- `connectors/base.py`
- `connectors/instagram.py`
- `connectors/fanvue.py`

Existing adapters under `app/integrations/` should remain low-level model/runtime adapters. Domain services choose adapters and enforce compatibility/policy.

Migration sequence:

1. job/event normalization;
2. provenance and source intended-use fields;
3. identity profiles and canonical-set versioning;
4. unified assets and generation recipes;
5. dataset QC/evaluation fields;
6. LoRA validation/activation history;
7. campaigns/content items;
8. connectors/external IDs;
9. audit and policy decisions;
10. roles/sessions if multi-user access is introduced.

Every migration needs a downgrade path or a documented irreversible step with a verified backup.

## 22. Testing strategy

### Backend

- unit tests for state transitions and compatibility rules;
- API contract tests for every router;
- idempotency tests for jobs and connectors;
- cancellation/retry/heartbeat tests;
- database migration tests from a copy of the current schema;
- storage cleanup and reconciliation tests;
- policy/provenance tests;
- deterministic fixtures for caption and dataset invariants.

### Model workflows

- small fixed image fixture set;
- mocked fast path in CI;
- opt-in real GPU smoke suite;
- golden metadata assertions rather than pixel-perfect output;
- identity and duplicate-score threshold regression reports;
- one validation workflow per supported model family.

### Frontend

- component tests for AsyncBoundary, disabled reasons, error summaries, and placeholders;
- route tests with loading/empty/error/populated states;
- keyboard and accessibility checks;
- Playwright end-to-end flows:
  1. login and route navigation;
  2. create character draft;
  3. create identity run with mocked jobs;
  4. curate dataset;
  5. queue and inspect training;
  6. generate/review asset;
  7. create video from approved asset;
  8. simulated conversation and PPV unlock;
  9. connector dry-run package export.

### Performance

- 10,000-asset library;
- 2,000-item source collection;
- 500-job history;
- four simultaneous GPU jobs with enforced concurrency;
- slow network and server restart during polling/SSE.

## 23. Delivery order and milestones

### Milestone A — Trustworthy v6.1

- Phase 0 baseline;
- Phase 1 correctness fixes;
- cursor pagination;
- structured errors;
- basic UI component primitives.

### Milestone B — Coherent operator experience v6.2

- global character context;
- Overview and Jobs & System split;
- unified job tray;
- virtualized asset/source grids;
- redesigned Chat layout.

### Milestone C — Identity pipeline v7.0

- provenance-aware identity intake;
- multi-angle identity generation and scoring;
- canonical set versioning;
- routed dataset wizard;
- dataset QC and validation holdout.

### Milestone D — Validated LoRA and Studio v7.1

- training preflight;
- validation grid and reversible activation;
- Generate/Review/Library image modes;
- redesigned Video with asset picker.

### Milestone E — Content operations v8.0

- campaigns and content calendar;
- export packages;
- assisted conversation drafts;
- platform policy checks;
- analytics schema.

### Milestone F — Controlled integrations v8.1+

- official Instagram adapter if supported for the account type;
- official Fanvue adapter if supported;
- manual approval rollout;
- webhook/event reconciliation;
- constrained automation only after production validation.

## 24. Definition of done for the product vision

The product vision is achieved when an operator can:

1. create a documented synthetic adult character;
2. start from one valid identity image;
3. generate and review a balanced multi-angle canonical set;
4. build and freeze a quality-controlled 50–70 image dataset;
5. train, evaluate, activate, and roll back a LoRA;
6. generate reproducible images from pose references;
7. turn approved images into reviewed videos;
8. use only eligible media in a simulated fan conversation;
9. prepare platform-specific content packages;
10. connect and operate supported external channels with explicit approval, idempotency, provenance, auditability, and policy enforcement;
11. understand any failure and recover without reading raw implementation logs or editing database records.

Until those conditions are met, keep the product labelled as a private production playground rather than an autonomous influencer platform.
