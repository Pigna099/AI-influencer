# AI Influencer Playground v6 — Current-State Product and Interface Report

**Audit date:** 14 October 2026  
**Audited application:** `http://192.168.1.60:8010/`  
**Active server codebase:** `/data/data_ssd/pigni/ai-influencer/backend-v6`  
**Scope:** Read-only inspection of Home, Chat, Images, Video, Dataset, and LoRA, including the most important secondary panels. No generation, deletion, training, publishing, or message sending was performed.

## 1. Executive summary

The application is already much more than a simple model playground. It is a single-user, local-first production lab for synthetic adult characters. It currently combines:

- character and personality management;
- simulated fan conversations with per-fan memory;
- chat model comparison;
- image generation, classification, approval, and reuse;
- image-to-video and text-to-video generation;
- reference-dataset import and AI description;
- pose extraction;
- a multi-stage character LoRA dataset and training workflow;
- GPU allocation and service monitoring;
- simulated PPV photo/video unlocking.

The technical foundation is useful and the individual capabilities are substantial. The main product problem is not missing raw functionality; it is that the interface exposes too much implementation detail at once and does not yet present the work as one coherent character-production pipeline.

The strongest existing idea is the per-character workflow:

`character -> identity references -> curated dataset -> LoRA -> images -> videos -> chat`

The weakest areas are information architecture, asynchronous loading behavior, job visibility, error presentation, library scalability, and the absence of real publishing/inbox integrations. Instagram and Fanvue are not connected. The chat is a simulation and all PPV payments are simulated.

## 2. Product and technical baseline

### 2.1 Runtime architecture

The active application uses:

- React 18, TypeScript, Vite, and React Router for the WebUI;
- FastAPI, SQLAlchemy, Alembic, and PostgreSQL for the backend;
- a database-backed worker system for generation and training jobs;
- ComfyUI for image and video workflows;
- vLLM as the active text provider, with Ollama as fallback and for auxiliary models;
- NVML for GPU telemetry;
- a host LoRA trainer using kohya for SDXL-family LoRAs and musubi-tuner for Qwen-Image.

The server code is reasonably modular. Important frontend files are under `backend-v6/webui/src/components/`, including `HomePage.tsx`, `Playground.tsx`, `ChatPanel.tsx`, `BenchmarkPanel.tsx`, `ImagePlayground.tsx`, `VideoPlayground.tsx`, `DatasetPlayground.tsx`, `LoraPlayground.tsx`, and `PoseLibrary.tsx`. Backend responsibilities are split across `characters.py`, `dataset_api.py`, `lora_api.py`, `video_api.py`, `pose_api.py`, `presets_api.py`, `consistency_api.py`, `settings_api.py`, `worker.py`, and the model integrations.

### 2.2 Authentication and audience

The login screen accepts a shared API key and keeps it in the browser session until logout. This is suitable for a private LAN laboratory, but it is not a multi-user authorization model. There are no roles, no per-user workspaces, and no separation between operator, reviewer, and administrator.

The inspected data and product copy indicate that the platform is intended for fully synthetic adult characters. Imported real-person material can currently be used as reference material, which creates a need for explicit provenance, consent, likeness, and license controls before this becomes an operational content system.

### 2.3 Global shell

The global header contains:

- brand mark and product name;
- version label;
- Home, Chat, Images, Video, Dataset, and LoRA tabs;
- logout.

The dark visual language is coherent. Each working area has a different accent color, which helps orientation. The top navigation remains stable across pages.

Current shell issues:

- the browser title says v5 while the in-page header says v6;
- navigation reflects technical modules rather than the user's end-to-end workflow;
- the selected character is not a global route/context, so each tab repeats a character rail and can temporarily show a different or empty state;
- infrastructure configuration and creative work have equal prominence even though they serve different operating modes;
- several pages load data after the first render and briefly claim that no data exists.

## 3. Tab-by-tab description

## 3.1 Home

### Purpose

Home is both a system dashboard and a global model/GPU configuration page.

### What is visible

1. **Service status**
   - API and database health;
   - ComfyUI status;
   - Ollama availability;
   - GPU/NVML availability;
   - LoRA trainer status.

2. **Default models**
   - default chat model;
   - default image checkpoint;
   - default video model;
   - active text-provider indicator;
   - Save action.

3. **Live GPUs**
   - one assignment selector per GPU: Text, Photo/Video, or Off;
   - Apply plan action;
   - Free VRAM action;
   - memory, utilization, power, temperature, and process information.

4. **Characters**
   - collapsible character list with avatar, style, and LoRA count;
   - links into Chat.

5. **Installed assets**
   - collapsible ComfyUI checkpoints;
   - ComfyUI LoRAs;
   - Ollama models.

### How it works

The page polls service and GPU state. The GPU plan is a real operational control: it assigns devices to text or media workloads and is applied asynchronously by the host worker. The model selectors save global defaults used to preselect controls elsewhere.

### UX assessment

Home is useful for an administrator, but it is not yet an effective creator dashboard. The most prominent content is infrastructure, while the user’s real work—finish an identity, review a dataset, inspect a failed job, approve media, answer a conversation—is not summarized.

Recommended direction: turn Home into an operational overview with a “continue workflow” card, pending review counts, running/failed jobs, recent assets, and character readiness. Move detailed GPU allocation and installed-model inventories to a dedicated System/Settings area.

## 3.2 Chat

### Purpose

Chat simulates a Fanvue-like conversation. The operator plays the fan and tests how a character behaves, remembers details, handles tone, and offers media.

### What is visible

The page uses a dense three-area layout.

**Left rail:**

- character list with avatar and personality summary;
- Edit personality;
- photo style selector;
- PPV photo toggle and price;
- collapsible realism controls;
- simulated fan selector and fan creation;
- test notes that are not sent to the model;
- conversation list with model/date/version;
- delete-chat controls.

**Main area:**

- character and personality version;
- selected fan;
- Chat and Compare models tabs;
- model selector;
- New chat;
- message history;
- composer and Send action.

**Supporting panels:**

- fan memory for the character/fan pair;
- manual test-fact entry;
- latency statistics by model.

### Personality editor

The editor includes name, language, identity description, physical appearance, personality traits, tone, writing style, background, interests, dislikes, phrases, relationship style, boundaries, and custom instructions. An installed model can expand the profile into a draft before the user saves it.

This is a strong schema for a character bible. The editor correctly separates “generate draft” from “save,” which reduces accidental modification.

### Compare models

The benchmark area supports:

- multiple chat models;
- temporary personality variants;
- predefined scenarios such as natural conversation, light flirting, memory recall, and respecting boundaries;
- a shared test message;
- 1–5 runs per model;
- temperature;
- loading the most recent comparison.

Runs are isolated from normal chat history. This is valuable for evaluating tone and model quality.

### How it works

Memory belongs to the character/fan pair, not to a model or one conversation. Conversations snapshot the personality version. Replies can be delayed for realism, split into human-like bubbles, and may include generated or library media. PPV is only simulated; unlocking writes a simulated payment record.

### UX assessment

Chat has strong capabilities but the left rail is overloaded. Character configuration, fan management, monetization, realism, conversation selection, and memory are all visible in the same workspace. The initial selected state can also be confusing: a character, fan, and model may appear selected while the composer remains disabled because no active conversation has been chosen.

Observed defect: the model-comparison card displayed `NaN GB` for the active model. The disabled Start comparison action did not explain that no model checkbox had been selected.

Recommended direction: keep the chat transcript central, move character and monetization settings into an inspector/drawer, make fan/conversation navigation its own rail, and expose the exact reason for every disabled primary action.

## 3.3 Images

### Purpose

Images is both a generation studio and the canonical media library for a character. Approved items can be reused by Chat and used as starting frames for Video.

### What is visible

**Left rail:**

- character selection;
- status filter;
- style filter.

**Library:**

- image cards with draft/approved/rejected state;
- one-to-five-star rating;
- caption and tags;
- checkpoint/model, use count, and origin;
- Approve, Reject, Classify, and Delete;
- multi-selection and bulk deletion.

**Generation inspector:**

- presets and Save preset;
- prompt;
- optional creative direction;
- AI prompt augmentation;
- negative prompt;
- style;
- checkpoint;
- character and other LoRAs;
- pose selection;
- image count;
- optional seed;
- optional AI classification after generation;
- Generate.

**Additional tools:**

- character-consistency checking with a vision model;
- pose library with active/inactive poses and editing/deletion.

### How it works

The character's profile image and active compatible LoRA provide identity conditioning. A selected pose can drive ControlNet/OpenPose. Generated items enter the library as drafts. AI classification adds captions and tags. Approval makes an asset available to downstream chat/video selection. A consistency check compares assets against the character reference and can flag weak matches.

### UX assessment

This page exposes the correct professional concepts, but it does not scale well with tens or hundreds of assets. Every card contains many always-visible actions and long metadata. The inspector can become taller than the viewport, and opening advanced accordions shifts focus far down the page.

Observed problems:

- the filter labelled “Photo checkpoint” actually contained status values All, Drafts, Approved, and Rejected;
- the page briefly showed zero images before asynchronously loading a large library;
- the LoRA area simultaneously said “No LoRAs installed” and showed an active character LoRA path;
- prompts and captions can become extremely long and dominate card layout;
- destructive actions are repeated on every card without a softer archive/trash model;
- large libraries appear to render all cards instead of using pagination or virtualization;
- advanced settings are not summarized after collapse, so the operator cannot verify the effective configuration at a glance.

Recommended direction: use a virtualized asset grid, a single selected-item inspector, a sticky generation panel, saved view filters, a compare/review mode, and an explicit “effective recipe” summary containing checkpoint, LoRA stack, pose, seed, and reference.

## 3.4 Video

### Purpose

Video turns an approved character image—or a text prompt—into a short clip and stores it in the character’s video library.

### What is visible

- character rail;
- existing clip cards with thumbnail/poster, Play, prompt, frame count, generation time, seed, and Delete;
- mode: From image or Text only;
- start-image selector;
- motion/scene prompt;
- negative prompt;
- resolution;
- duration in frames;
- steps;
- seed;
- model selector;
- compatible video LoRAs;
- Generate video.

The available models include Wan 2.2, LTX-2.3 variants, and HunyuanVideo 1.5.

### How it works

Image mode uses a library image as the identity anchor and first frame. Text mode uses the chosen family's text-to-video path. Model-specific presets control supported resolution, frame count, steps, and frame rate. Clips are stored as WebM with generated thumbnails.

### UX assessment

The page is functionally clear but has library-selection and loading issues.

Observed problems:

- the first render claimed that no library images existed, then later loaded them;
- the source-image select included a very long list of draft and rejected assets as disabled entries; only eligible assets should be presented;
- literal template placeholders such as `{7}`, `{49}`, and `{81}` were visible in UI text;
- generation time and clip duration are not clearly distinguished;
- cards show Delete prominently but do not expose stronger review states such as draft/approved/rejected;
- the form lacks a compact visual preview of the selected source image;
- no unified job progress/queue is visible while long video jobs run.

Recommended direction: use an asset picker with thumbnails, search, filters, and approved-only default; show the selected source prominently; use seconds plus frames; display ETA, queue position, cancel/retry, and job logs through the shared job system.

## 3.5 Dataset

### Purpose

Dataset imports external reference media and converts it into structured descriptions for inspiration, pose/style analysis, profile generation, and export.

### What is visible

**Source creation:**

- name;
- source type;
- reference;
- maximum images;
- classify with AI after import;
- Import.

Visible source types include public Telegram channel, direct image URLs, server folder, public X/Twitter profile, and public Nextcloud share.

**Source list:**

- source name;
- source type;
- image/video count;
- ready/importing/failed state.

**Dataset workspace:**

- imported media grid;
- PENDING and other status badges;
- per-item detail and delete controls;
- Classify unclassified;
- Export JSONL;
- Generate profile;
- Delete source;
- detail panel with pose, setting, lighting, scene, outfit, body, skin, camera, mood, style;
- Extract pose.

### How it works

Import runs in the background. The vision model generates captions, tags, and structured attributes for images. JSONL can be exported. A profile can be synthesized from classified material. Pose extraction creates reusable pose-library items.

### UX assessment

The separation between a reference dataset and a character's own training/media library is not sufficiently prominent. A new operator could assume that imported people become the character or that all imports are automatically safe to train on.

Observed problems:

- a source briefly displayed “No sources yet” despite a populated source rail;
- the grid contains opaque hash filenames instead of human-friendly asset labels;
- icon-only controls use symbols such as `⌕` and `≡`, with weak semantics;
- pending items can fill the entire grid with little indication of queue progress or estimated completion;
- Delete sits beside routine actions and needs clearer confirmation and scope wording;
- no visible provenance, license, consent, or permitted-use fields exist;
- no strong visual distinction exists between pose/style reference use and identity training use;
- large sources appear to render very large grids without pagination/virtualization.

Recommended direction: add an import wizard with source rights/provenance, intended use, duplicate detection, progress, failures, and sampling. Make reference-only the safe default. Require explicit, auditable promotion before any imported asset can enter identity training.

## 3.6 LoRA

### Purpose

LoRA is the most complete and most complex page. It manages the character’s identity anchor, dataset creation, selection, training registry, and training jobs.

### What is visible

**Character rail:**

- characters and styles;
- New character.

**Step 1 — Character:**

- profile image;
- profile-image model;
- regenerate;
- edit with Qwen-Edit;
- duplicate and delete character.

**Step 2 — LoRA dataset:**

- dataset creation and trigger token;
- dataset list and selected count;
- a five-stage internal workflow:
  1. identity candidates;
  2. canonical references;
  3. Qwen-Image-Edit variations;
  4. SDXL + pose candidates;
  5. curation and selection.

The curation grid supports captions, canonical roles, training selection, bulk selection, deletion, target progress, and warnings about near duplicates.

**Step 3 — Training:**

- LoRA name;
- family: real, pony, anime, qwen-image;
- trigger;
- rank;
- base checkpoint;
- LoRA registry and active state;
- Queue training;
- training jobs and worker/log data.

**Guide column:**

- contextual explanation of Character, Dataset, Training, usage in Images, and a glossary.

### How it works

The profile picture acts as the first identity anchor. The operator generates multi-view identity candidates, assigns canonical roles to 4–8 strong references, generates two independent variation branches, curates approximately 50–70 selected images, creates a family-specific LoRA registry entry, and queues training. Successful weights are copied to ComfyUI and can become the active character LoRA for that family.

### UX assessment

The page already approximates the desired business workflow, but it compresses an entire product into one extremely long screen. The guide permanently consumes width, the curation grid renders inside the same document as training, and old jobs expose raw filesystem paths and Python stack traces.

Observed problems:

- the first render showed zero LoRAs/datasets before the real data arrived;
- the step header can say DONE while a downstream branch is still TODO, but overall readiness is not summarized;
- the target displays both `40/85 selected` and `40/60 selected for training`, which needs clearer meaning;
- a Qwen LoRA card exposes a missing-checkpoint filesystem path without a remediation action;
- the training history is dominated by old failed/cancelled jobs;
- raw stack traces and complete trainer commands are shown inline;
- some failed jobs are generically named “Training jobs,” so the affected LoRA is unclear;
- one generated training item appears to contain many prompts concatenated into a single caption, indicating a dataset-generation or captioning defect;
- destructive actions are repeated throughout a high-risk workflow;
- there is no dedicated validation-set comparison before activating a trained LoRA.

Recommended direction: make LoRA a routed wizard with one stage per screen, a persistent progress rail, explicit entry/exit criteria, a review queue, compact job cards, expandable technical logs, checkpoint-fix actions, and a mandatory validation gallery before activation.

## 4. Current end-to-end workflow

The application currently supports the following practical sequence:

1. Create a character and complete the character bible.
2. Generate a profile image as the identity anchor.
3. Create a LoRA dataset.
4. Generate identity candidates from the character prompt.
5. Select canonical close-up, three-quarter, profile, upper-body, and full-body references.
6. Generate Qwen variations and/or SDXL pose candidates.
7. Edit captions, remove duplicates, assign roles, and select training images.
8. Create and train a family-specific LoRA.
9. Activate the trained LoRA.
10. Generate images with compatible checkpoints, poses, presets, and LoRA weights.
11. Classify, rate, approve, or reject images.
12. Turn approved images into video.
13. Reuse approved photos and ready clips in simulated fan conversations.
14. Test memory, timing, tone, and simulated PPV unlock behavior.

This workflow is technically present but not represented as a single, persistent project pipeline. Users must understand how tabs depend on one another.

## 5. Cross-cutting interface issues

### P0 — correctness and trust

- False empty states appear before asynchronous data finishes loading.
- Literal template placeholders are visible in Video.
- `NaN GB` appears in model comparison.
- A status filter is mislabeled as “Photo checkpoint.”
- The Images LoRA summary contradicts itself.
- Raw backend paths, trainer commands, and stack traces are presented as primary UI content.
- Some training items show malformed or concatenated captions.

### P1 — workflow and ergonomics

- There is no persistent character context across tabs.
- Each page duplicates character selection and page-specific loading logic.
- Home emphasizes infrastructure instead of pending creative work.
- Long-running work lacks one unified queue, progress model, and retry experience.
- Images, Dataset, and LoRA load extremely large grids into long pages.
- Repeated per-card buttons create visual noise and make destructive actions too easy to hit.
- Disabled buttons rarely explain what prerequisite is missing.
- Advanced generation settings do not show a compact effective-configuration summary.
- Operational settings, creative tools, review tools, and destructive controls are mixed together.

### P2 — polish and accessibility

- Some icon-only controls have unclear labels.
- Long text is truncated inconsistently or overwhelms cards.
- Focus jumps after accordion expansion.
- Sticky headers/panels and viewport boundaries are inconsistent.
- Technical units and terminology are not consistently explained.
- Empty states sometimes describe a different prerequisite than the one actually missing.

## 6. Gaps relative to the intended product

The following are not yet complete product capabilities:

- no Instagram account connection, scheduling, publishing, comments, or analytics;
- no Fanvue inbox connection, media publishing, actual PPV offers, or payment state;
- no production-grade multi-user authentication or permissions;
- no content calendar or campaign planner;
- no centralized approval queue spanning images, videos, captions, posts, and messages;
- no explicit provenance/consent/license record for source media;
- no identity-similarity report with reproducible thresholds and validation set;
- no unified audit trail for prompts, models, seeds, adapters, reviews, and publishing;
- no automatic recovery policy for failed generation/training jobs;
- no storage quota, retention, reconciliation, or trash/restore interface;
- no product analytics for content performance or conversation outcomes;
- no clear separation between experimental playground behavior and production actions.

## 7. Safety, provenance, and compliance requirements

The intended NSFW use does not remove normal product obligations. Before external operation, the platform should enforce:

- synthetic adult characters only, with an explicit adult-age lock in the character schema;
- no identity creation from a real person without documented consent and permitted-use rights;
- provenance and license metadata for every imported source;
- a reference-only default for imported pose/style material;
- deterministic blocking of known or suspected minors and ambiguous-age material;
- no age-reduction prompts or youth-coded presentation;
- full audit records for dataset promotion, model training, asset generation, approval, and publication;
- encrypted secrets and restricted access to private media;
- human approval for publishing, paid offers, and outbound conversation until the system has been separately validated;
- platform-specific policy checks before Instagram/Fanvue publishing;
- transparent labeling/disclosure where required by law or platform rules;
- opt-out, block, and escalation behavior for real users in conversations;
- no deceptive pressure, impersonation of a real person, or coercive monetization behavior.

## 8. Overall assessment

The project has a credible technical core and already demonstrates the difficult local-model integrations. The next release should prioritize workflow coherence and reliability over adding more models. The user should feel that they are moving one character through a controlled production line, not operating six independent engineering consoles.

The implementation roadmap is defined in `PLAN.md`.
