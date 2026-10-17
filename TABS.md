# TABS.md — AI Influencer Playground v6: complete tab-by-tab description

Purpose of this document: a precise, structured description of every tab (page) and feature of the
application, written so an external LLM can design structured workflows (checklists, automations,
prompt templates) on top of it. English only. Last updated: 14 October 2026.

---

## 0. System overview

Single-user local platform (FastAPI backend + React WebUI, Docker Compose) that runs a playground for
**fully synthetic adult characters (25+)**: chatting with simulated fans, generating photo/video
content with ComfyUI, building LoRA datasets, training character LoRAs on a host worker, and simulating
pay-per-view (PPV) monetization. No real-person likeness; Instagram/X/Nextcloud imports are used as
pose/style references only.

- **Auth**: single API key (`X-API-Key`, from `.env`), WebUI stores it locally.
- **Frontend**: React + Vite (`backend-v6/webui`), one top navbar: Home, Chat, Images, Video, Dataset,
  LoRA (English only).
- **Backend**: FastAPI routers in `backend-v6/app/` (`characters.py`, `lora_api.py`, `video_api.py`,
  `dataset_api.py`, `pose_api.py`, `presets_api.py`, `settings_api.py`, `consistency_api.py`, `main.py`).
- **Text models (2 providers)**:
  - **Ollama** (current default): text models, embeddings (`nomic-embed-text`) and vision tagging
    (`gemma3:27b`) from `TEXT_PROVIDER=ollama`.
  - **vLLM** (optional): OpenAI-compatible API at `http://127.0.0.1:8000`, used when the GPU plan
    reserves two GPUs for text (`TEXT_PROVIDER=vllm`); it is currently stopped because all four GPUs
    run photo/video ComfyUI instances (8188-8191).
- **Image/video models (ComfyUI)**: on the media GPUs from the saved GPU plan (currently all four,
  ports 8188-8191, discovered automatically), families:
  - SDXL: `real`, `pony`, `anime`, `playground` (Playground v2.5, EDM sampling).
  - Diffusers families: `qwen-image` (2512 + **2.1**), `z-image`, `flux2` (**Klein 4B** base/distilled).
  - Video: `wan` (2.2 I2V/T2V + lightx2v 4-step), `ltx-distilled`/`ltx-dev` (LTX-2.3, 24 fps),
    `hunyuan` (HunyuanVideo 1.5 480p distilled, 24 fps).
- **Trainer (host)**: `train_worker.py` runs LoRA training jobs: SDXL families via kohya
  (`sdxl_train_network.py`), `qwen-image` via musubi-tuner. Publishes trained LoRAs to ComfyUI and the
  registry. Also applies the GPU plan and cleans deleted LoRA files.
- **GPU plan**: per-GPU assignment (Media / Text / Off) from the Home page; applied on the host by the
  worker (`apply_gpu_plan.sh`): ComfyUI instances per media GPU (port = 8188 + GPU index) and vLLM on
  exactly two text GPUs (tensor parallel).

### Model families and compatibility (important for planning)
- **Image LoRA** families: `real`/`pony`/`anime` (SDXL, kohya) and `qwen-image` (musubi). Playground
  checkpoints accept SDXL LoRAs. LoRA/checkpoint mismatches are rejected by the API.
- **Video LoRAs** are family-specific (`wan`, `ltx`, `hunyuan`); speed LoRAs (lightx2v/distilled) are
  applied automatically and hidden from pickers.
- **Chat visuals**: `[PHOTO: ...]`/`[PPV: ...]` → generated or library photo; `[PPV-VIDEO: ...]` → an
  existing ready clip from the character's video library, sent **locked** (simulated payment to unlock).

---

## 1. Home (`/`)

Purpose: configuration hub + system status. Layout top→bottom:

1. **Status flags**: API, ComfyUI (usable checkpoints count), Ollama, vLLM, trainer, scheduler.
   Each flag shows ok/warn/down with a short detail.
2. **Default models** (saved globally, used as preselects in the other tabs):
   - Chat model (dropdown of chat-capable models; when vLLM is active its served models appear).
   - Image generation checkpoint (all usable checkpoints, with family).
   - Video generation model (wan / ltx-distilled / ltx-dev / hunyuan).
   - Badge shows the active text provider (vLLM active / fallback / Ollama) and a Save button.
3. **GPU plan**: one dropdown per GPU (Photo/Video ↔ Media, Text ↔ vLLM, Off) + **Apply plan** button.
   Validation: ≥1 media GPU; text 0 or exactly 2 GPUs (vLLM TP=2). The worker applies it asynchronously
   (status: applying… / applied at HH:MM). `POST /api/settings/gpu-plan`.
4. **GPU cards**: per-GPU memory bar, utilization, power, temperature, processes with VRAM; a
   **Free VRAM** button (unloads Ollama models and ComfyUI caches).
5. **Characters** (collapsible): avatar tiles linking to Chat, with style and active LoRA count.
6. **Checkpoints / LoRAs / Ollama models** (collapsible lists): installed assets with family/kind.

---

## 2. Chat (`/chat`)

Purpose: simulate a fan talking to a character (the playground user plays the fan).

- **Left rail**: character list, fan list (+ create/edit fan: name, notes), conversation list
  (+ new conversation with a model selector), memory panel for the selected fan.
- **Chat area**: message bubbles per role; per-message metrics (model, seconds, tok/s, kind, guards).
  Assistant messages may carry:
  - **Photos**: inline; PPV photos show blurred with a lock + price and an **Unlock** button (records a
    simulated payment, then reveals the full image).
  - **Videos**: poster + lock + price while PPV; after unlock a play button streams the clip inline.
- **Toolbar / settings**:
  - Chat model for the conversation; character **profile picture checkpoint** and **style** (real/anime).
  - **PPV toggle + price** for the character (simulated payments only).
  - **Human mode** (multi-bubble replies, typos), **auto-photo** toggle, proactive/absence scheduler.
  - **Benchmark panel**: run the same message against multiple models and personality variants, compare
    tok/s, latency and answers (each run isolated, no history pollution).
- **Backend behavior worth knowing for workflows**: per-fan long-term memory extraction after each
  user message; injection guard on model output; reply delays to simulate human timing; the character
  may attach photos proactively or when asked, and PPV content only after a free photo in the same
  conversation (photos) or when engaged (videos). Photo prompts are generated by the chat model itself
  (`[PHOTO: english tags]`), identity comes from the avatar reference + active LoRAs.

---

## 3. Images (`/images`)

Purpose: generate and curate the character photo library (the source of truth for approved content).

- **Left rail**: character selection; filters (status, style); multi-select delete.
- **Library grid**: cards with thumbnail, status badge (draft/approved/rejected), rating stars (1-5),
  caption, tags, checkpoint/style/usage info, per-card actions (approve, reject, classify with AI,
  delete).
- **Right inspector — generation form**:
  - **Presets** (CRUD): save/load full generation settings.
  - **Prompt** (any language, translated), **direction** + **Amplia con AI/Augment** (LLM expands the
    prompt), **negative**, **style**, **checkpoint** (family-aware), **LoRA stack** (many LoRAs with
    per-LoRA weight and CLIP weight, categories, compatibility filtering against the checkpoint family),
    **pose** (pick from the character's pose library + strength → ControlNet OpenPose), count (1-4),
    seed, generate.
  - Reference identity: the character's profile picture is used automatically (IPAdapter on SDXL,
    reference image on Qwen-Edit variations).
  - **Character consistency**: a vision model (vLLM qwen3.8, Ollama fallback) compares the library
    images against the character reference and returns a score (0-100) + reason per image, worst first,
    with a threshold (default 60) and a flagged count. Slow: ~2 s per image.
- **Profile picture**: generated/edited per character (also accessible from the LoRA tab), with model
  and style selection; the avatar is the identity reference for chat and dataset workflows.

---

## 4. Video (`/video`)

Purpose: short clips per character, from an image or text, in three model families.

- **Left rail**: character selection.
- **Clip grid**: cards with **thumbnail** (first frame, auto-generated), play on demand (streams the
  WebM inline), prompt, frames/seconds/seed, delete.
- **Right inspector**:
  - **Mode**: *From image* (uses a library image as the first frame) or *Text only*.
  - **Source image** (library dropdown, in image mode).
  - **Model**: Wan 2.2 (I2V/T2V), LTX-2.3 distilled, LTX-2.3 dev + distilled LoRA, HunyuanVideo 1.5.
    Each family has its own resolution/duration/step presets (e.g. LTX 768×512/512×768/1216×832,
    49/97/121 frames, 5/8 steps, 24 fps; Wan 832×480/1280×720, 49/81/121 frames, 4/8 steps; Hunyuan
    832×480/480×832, 8/20 steps).
  - **Prompt / negative**, **seed**, **LoRA picker** (family-filtered: `wan`, `ltx`, `hunyuan`; the
    automatic speed LoRAs are hidden), generate + interrupt.
- Behavior: text mode switches Wan to its T2V checkpoints and T2V lightx2v LoRAs automatically; LTX
  and Hunyuan text modes use their dedicated checkpoints. Duration/reference identity: image mode keeps
  the source identity (LTX/Hunyuan i2v verified). All clips are silent WebM (16 fps Wan, 24 fps others).

---

## 5. Dataset (`/dataset`)

Purpose: import bulk images (moodboard/pose/style references) and produce AI descriptions.

- **Import sources** ("+ New source" collapsible form): name, **kind**, reference, limit (1-2000),
  optional AI classification at import. Kinds:
  - `telegram`: public channel (`@name` or `t.me/s/name`), paginated.
  - `urls`: list of direct image URLs.
  - `folder`: a folder inside `data/imports` on the server.
  - `x`: public X/Twitter profile **or a single post link** (anonymous guest-token GraphQL, no account;
    collects `pbs.twimg.com` photos, skips retweets).
  - `nextcloud`: **public share link** (`https://server/s/TOKEN`, also subfolder links) — WebDAV
    (`/public.php/dav/files/TOKEN`, legacy fallback), recursive, images only. Recommended path for
    Instagram content (the user's own scraper pushes to Nextcloud).
  - Instagram direct scraping was removed (14 Oct 2026).
- **Sources list**: status (pending/importing/ready/failed), imported count, error message.
- **Images grid**: thumbnails, AI description details (caption, pose, scene, outfit, lighting, camera,
  tags...), manual tag/description edit, classify button (re-run AI), delete.
- Export endpoint available (images + captions).
- Note: images imported here are **references**, not the character's own library; they feed pose
  extraction and moodboards. Poses can be extracted into the pose library (see LoRA tab).

---

## 6. LoRA (`/loras`)

Purpose: everything per-character training: profile picture, dataset production, LoRA registry and
training queue. Layout: character rail, 3 numbered steps, optional guide column.

### Step 1 — Profile picture
Generate/edit the character avatar (model, style, prompt); it is the identity reference used everywhere
(chat photos, dataset candidates, consistency checks).

### Step 2 — Dataset (the branching pipeline)
Datasets are per character; each dataset has a trigger token and a curation grid. Sub-steps:
1. **Identity candidates**: generate 20-50 candidates with a configurable model (default Qwen-Image-2512)
   plus a collapsible **Character prompt** (the identity part of the profile-picture prompt; editable,
   saved on the character, automatically included in every candidate so ethnicity/features are kept).
2. **Canonical references**: assign a role to 4-8 chosen images (close face, three-quarter, profile,
   upper body, full body front/three-quarter/side). These become the identity anchors for later
   generation.
3. **Variations (Qwen-Image-Edit)**: batch scenes (20 default prompts) applied over the references.
4. **Candidates (SDXL)**: checkpoint + IPAdapter + optional ControlNet pose + pose strength.
5. **Curation**: the shared grid; per image caption (feeds training captions), role, select/deselect for
   training, bulk select-all/delete; a progress bar toward the target (60) and deterministic warnings
   (too few profiles/full-bodies, duplicates, same pose/scene, too frontal...).

### Step 3 — Training
- **"+ New LoRA"** registry form: name, family (`real`, `pony`, `anime`, `qwen-image`), trigger,
  rank, base checkpoint (checkpoint list is family-aware; Qwen checkpoints map to their bf16 weights
  automatically for musubi).
- **Queue training**: choose the curated dataset, GPU (optional), steps; the host worker trains
  (kohya or musubi), reports step/loss, and publishes the safetensors to ComfyUI + the registry.
- **LoRA cards**: status, family/rank/checkpoint, activate/deactivate, delete; **jobs list** with
  progress, loss, cancel (whole process group killed), retry on OOM, x16-PCIe GPU preference.
- The active LoRA per family is the default identity adapter used in Images/Chat/Variations.

---

## 7. Cross-tab workflows (typical)

1. **Character bootstrapping**: Home → create character (Chat rail or LoRA rail `+`) → profile picture
   (LoRA step 1) → dataset identity candidates (step 2.1) → canonical references (2.2) → variations +
   SDXL candidates (2.3-2.4) → curation (2.5) → training (step 3) → active LoRA → generate the photo
   library (Images tab).
2. **Content production**: Images tab (checkpoint + LoRAs + poses + presets) → curate library (approve)
   → Video tab (image → video, three families) → Chat tab (photos/videos, PPV simulation, unlock).
3. **Reference harvesting**: Dataset tab (Telegram, X, Nextcloud, URLs) → AI descriptions → pose
   extraction into the pose library → used as ControlNet in Images/dataset candidates.
4. **Quality control**: consistency checker (Images inspector) flags off-model pictures; dataset
   warnings flag curation issues; benchmark panel compares chat models.
5. **Infrastructure**: Home defaults + GPU plan control which models are used by default and how GPUs
   are split between media (ComfyUI) and text (vLLM).

---

## 8. Settings & environment (for planning)

- `backend-v6/.env`: `API_KEY` (required), `TEXT_PROVIDER=ollama|vllm`, `VLLM_URL`, `COMFYUI_URLS`,
  `OLLAMA_*`, `X_BEARER` (optional), `DATASET_*`, `PPV_*`, `CHAT_*`, `LORA_*`, `HF_HOME`.
- Global app settings (DB `app_settings`): default chat/photo/video models, GPU plan.
- Characters: profile bible (description, appearance, personality, boundaries, language...), avatar +
  avatar prompt (identity prompt), image style/checkpoint, PPV settings, LoRA registry.
- Training artifacts: `data/loras/`, published to `ComfyUI/models/loras/ai_influencer/`.
- Host services: Ollama, Docker Compose (API+DB+worker), ComfyUI instances, vLLM, trainer worker
  (boot: `~/start-ai-influencer.sh`).
