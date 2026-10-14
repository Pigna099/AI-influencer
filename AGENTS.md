# AGENTS.md

## Active codebase

The active (and only) backend is **`backend-v6/`** — the AI influencer playground v6. Older folders (`backend/`, `backend-v3-stage`, `backend-v3p3`, `backend-v4`) were removed on 19 Sep 2026; snapshots live in the gitignored `backups/` folder.

Use `backend-v6/README.md` (operations, UI guide) and `backend-v6/STATO.md` (current status, recent changes) as the source of truth. `PLAN.md` at the root tracks the roadmap.

## What it does

- **Chat playground**: characters + simulated fans, per-fan memory, model benchmarking, personality A/B, simulated PPV.
- **Image playground**: ComfyUI NSFW generation with checkpoints/families/LoRAs, per-character image library, AI tagging, curation, reuse in chat.
- **Video playground**: text-to-video and image-to-video clips per character (Wan 2.2 I2V/T2V + lightx2v; LTX-2.3 distilled/dev, WebM).
- **Dataset pipeline**: importers (Telegram channels, image URLs, server folders, X/Twitter profiles, public Nextcloud shares), AI descriptions, pose extraction (DWPose) into the pose library.
- **LoRA pipeline**: per-character LoRA registry, dataset curation with canonical references, training jobs (SDXL families via kohya sd-scripts; `qwen-image` via musubi-tuner), automatic publishing to ComfyUI.

## Repository layout

| Path | Purpose |
|------|---------|
| `backend-v6/app/` | FastAPI app + routers (`characters.py`, `lora_api.py`, `pose_api.py`, `presets_api.py`, `video_api.py`, `dataset*.py`, `main.py`) |
| `backend-v6/app/db.py` | SQLAlchemy models |
| `backend-v6/app/integrations/` | ComfyUI (multi-instance), Ollama, GPU helpers |
| `backend-v6/alembic/versions/` | Migrations (currently up to `0017`) |
| `backend-v6/webui/` | React + Vite frontend (built into the Docker image; `webui_dist/` is untracked) |
| `backend-v6/scripts/` | Model downloads, startup scripts, trainer (`scripts/trainer/`) |
| `backend-v6/tests/` | Pytest suite (mock providers) |
| `/data/data_ssd/pigni/comfyUI/ComfyUI` | ComfyUI install + models (4 instances, ports 8188-8191, one per GPU) |
| `/data/data_ssd/pigni/trainer/` | Host training: `venv` (kohya), `musubi-venv`, `runs/`, `worker.log` |
| `/data/data_ssd/pigni/Ollama/models` | Ollama models |
| `/data/data_ssd/pigni/huggingface` | HuggingFace cache (HF_HOME) |

## Entrypoints

Development (from `backend-v6/`):

```bash
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Docker (deployed):

```bash
cd backend-v6
docker compose up -d --build --wait
```

Boot script: `~/start-ai-influencer.sh` (also copied in `backend-v6/scripts/`) starts Ollama, Docker, the 4 ComfyUI instances, the trainer worker and the opencode web UI. The trainer worker is `scripts/trainer/train_worker.py`, run with `/data/data_ssd/pigni/trainer/venv/bin/python`.

## Configuration

Environment lives in `backend-v6/.env` (API_KEY required). Notable settings: `COMFYUI_URLS` (dispatcher targets), `DATASET_*`, `INSTAGRAM_COOKIES` (optional cookie header for Instagram), `X_BEARER` (optional, defaults to the public web bearer), `PPV_*`, `CHAT_*`, `LORA_*`.

## Dataset importers

`kind` field of a dataset source: `telegram`, `urls`, `folder`, `x`, `nextcloud`.

- **Nextcloud** (`app/dataset.py`): public share link (`/s/TOKEN`, also subfolder links) via WebDAV; the recommended path for Instagram content (the user's own scraper pushes to Nextcloud). Instagram scraping was removed on 14 Oct 2026.

- **X/Twitter** (`XClient` in `app/dataset.py`): anonymous guest-token GraphQL, no account involved. Warms up x.com, activates a guest token, resolves operation queryIds from the community document (`fa0311/TwitterInternalAPIDocument`, cached 6h) with a bundle-scan fallback, then calls `UserByScreenName` + `UserTweets` over **GET** (POST is walled) and collects `pbs.twimg.com` photo URLs (`?name=large`). Handles 401/403 (re-activate), 404 `Query not found` (re-bootstrap), 429 (error, back off), HTTP 400 missing features (self-heals by adding them). Skip retweets; dedupe by media URL.
- Imported images flow into AI tagging and pose extraction; they are pose/style references, not likenesses. Instagram/X ToS compliance is the user's responsibility (stated in the UI).

## Pose pipeline

DWPose extraction via ComfyUI (`app/pose_api.py`, `POST /api/poses/extract`), skeleton library per character, used as ControlNet at generation time. IG/X imports are the main source of reference poses.

## LoRA training

- Families: `real`, `pony`, `anime` (kohya `sdxl_train_network.py`) and `qwen-image` (musubi-tuner `qwen_image_train_network.py`, latent/text-encoder pre-cache, `--fp8_base --fp8_scaled --blocks_to_swap 20`).
- `qwen-image` requires bf16 weights in `models/diffusion_models` (`qwen_image_2512_bf16.safetensors`) + `text_encoders/qwen_2.5_vl_7b.safetensors`; fp8 checkpoints are mapped automatically. The API rejects family/checkpoint mismatches.
- The worker picks the GPU with the most free memory, prefers **x16 PCIe links** (GPU 0/1 are x8 and block-swap training is ~2x slower there), frees ComfyUI VRAM via `/free` when needed, kills the whole process group on cancel, and retries once on CUDA OOM.
- Deleting a LoRA leaves a marker in `data/loras/pending_delete`; the worker removes the published ComfyUI file.

## Tests and quality

```bash
cd backend-v6
uv run ruff check .
uv run pytest -q            # 149 tests, mock providers, temporary DB
cd webui && npm run lint && npm test && npm run build
```

## Risky areas

- `alembic/versions/`: never edit existing migrations; create new ones.
- `webui/src/i18n.tsx`: edit only by re-reading the file in the same pass (past incident: a patch script overwrote it). Use `json.dumps` for values.
- Worker lease: `WORKER_LEASE_SECONDS` > generation timeout.
- ComfyUI VRAM: 4 instances cache models; free them before training (worker does it automatically).
- Deploy with `--build`; `docker compose up` without build keeps old code.
- Never commit `.env`, backups or model files.

## External dependencies (see STATO for the latest list)

Docker data-root (`/data/data_ssd/docker`, move script pending), ComfyUI venv base interpreter (`miniconda`), Ollama binary + systemd unit, `/usr/bin/python3.12` (venv base), `~/start-ai-influencer.sh`, opencode. HF cache and the trainer worker run entirely from `/data/data_ssd/pigni`.
