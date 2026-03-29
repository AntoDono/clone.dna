# CLONE.dna

**Hire the Mind. Not the Body.**

Clone.dna turns a developer's public GitHub work into a portable, executable LoRA adapter — a `.dna` block — that encodes their coding style, architectural patterns, and domain vocabulary. Hiring teams load the block and interact with it before scheduling a single interview. Developers become testable artifacts, not keyword-matched resumes.

---

## Architecture

```
GitHub / Website / Resume
         │
         ▼
  [ Extractor Layer ]          backend/extractor/
    github.py · website.py · resume.py
         │  candidate profile (skills, repos, bio)
         ▼
  [ Grok-3 Pair Generation ]   trainer/grok.py
    70B teacher reads code → generates (instruction, response) pairs
         │  ~18–60 training pairs per candidate
         ▼
  [ LoRA Training ]            trainer/training.py
    PEFT + HuggingFace Trainer on BASE_MODEL
    mixed with alpaca-cleaned + tool-use examples
         │
         ▼
  [ .dna Block ]               dnas/{team_id}/{handle}/
    manifest.json · eval.json · sources.json
    consent.json  · profile.md · adapter weights
         │
         ├──▶ [ Talent Registry ]    GET /registry
         │      browse · search · download .dna zips
         │
         └──▶ [ Chat / Build ]       POST /teams/{id}/build/chat
                hot-swap LoRA adapters per candidate
                tool-use agent loop (read/write files, run commands)
                PM orchestration: PM plans → Grok assigns → specialists respond
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | via `uv` |
| CUDA GPU | ≥ 8 GB VRAM | 16 GB+ recommended for training |
| Bun | 1.x | or Node 20+ |
| `XAI_API_KEY` | — | [console.x.ai](https://console.x.ai) — required for Grok pair generation |
| `GITHUB_TOKEN` | optional | raises GitHub API from 60 → 5000 req/hr |

---

## Backend Setup

```bash
cd backend
cp .env.example .env          # fill in XAI_API_KEY and optionally GITHUB_TOKEN
uv sync                        # install Python deps (creates .venv)
uv run python main.py          # starts on http://localhost:8000
```

The server pre-warms the base model in a background thread on startup.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `XAI_API_KEY` | — | **Required.** Grok API key for training pair generation |
| `GITHUB_TOKEN` | — | Optional. Raises GitHub API rate limit to 5000 req/hr |
| `BASE_MODEL` | `Qwen/Qwen2.5-0.5B-Instruct` | HuggingFace model ID or local path. Supports GPTQ quantized models |
| `DB_PATH` | `clone_dna.db` | SQLite database path |
| `DNAS_DIR` | `dnas` | Root directory for saved .dna blocks |
| `GROK_CACHE_DIR` | `grok_cache` | Cache directory for Grok-generated training pairs (skips API on reruns) |
| `CUDA_VISIBLE_DEVICES` | — | GPU index(es) to use, e.g. `0` or `0,1` |
| `QUANTIZATION_BITS` | — | Set to `4` or `8` to quantize `BASE_MODEL` locally via GPTQ on first run |
| `QUANTIZED_MODELS_DIR` | `quantized_models` | Cache dir for locally quantized models |
| `NUM_OF_PARALLEL_TRAINING` | `1` | Max concurrent LoRA training jobs (limited by GPU VRAM) |
| `AGENT_WORKSPACE_DIR` | `agent-workspace` | Sandbox directory for agent tool use (file read/write/run) |

---

## Frontend Setup

```bash
cd frontend
bun install
bun run dev    # starts on http://localhost:3000
```

The frontend expects the backend at `http://localhost:8000` (configured in `nuxt.config.ts`).

---

## Running the Full Stack

```bash
# Terminal 1 — backend
cd backend && uv run python main.py

# Terminal 2 — frontend
cd frontend && bun run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Demo Walkthrough

1. **Create a team** — name it and add role slots (PM, SWE, Designer)
2. **Headhunt candidates** — search GitHub by username or paste a resume/website URL; the extractor builds a candidate profile
3. **Select candidates** — pick one candidate per role slot
4. **Clone DNA** — click "Clone DNA" to start the pipeline:
   - Collects code from the candidate's top GitHub repos
   - Calls Grok-3 to generate instruction-response training pairs in their style
   - Trains a LoRA adapter on the base model
   - Saves the `.dna` block to `dnas/{team_id}/{handle}/`
5. **Chat with the clone** — open the Build tab and message any cloned candidate; the adapter hot-swaps per candidate
6. **Orchestrate** — send a project prompt to the full team; the PM plans, Grok assigns tasks, specialists respond in sequence
7. **Browse the Registry** — `GET /registry` to list all minted `.dna` blocks and download them as zips

---

## .dna File Format

Each `.dna` block is a directory at `dnas/{team_id}/{github_handle}/` containing:

| File | Description |
|---|---|
| `manifest.json` | Name, version, candidate metadata, base model, rank/alpha, eval summary, vLLM compatibility flag |
| `eval.json` | Training metrics: loss history, pair counts, benchmark scores (populated post-training) |
| `sources.json` | Full repo provenance: name, URL, language, stars, topics for every source repo |
| `consent.json` | Opt-in record: consent status, public-repos-only flag, revocability note |
| `profile.md` | Human-readable candidate profile: bio, skills, top repos, training stats, usage example |
| `adapter_config.json` | PEFT LoRA adapter config (auto-generated by HuggingFace) |
| `adapter_model.safetensors` | LoRA adapter weights — load with PEFT or vLLM `--enable-lora` |

### Loading a Block with PEFT

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct", device_map="auto")
model = PeftModel.from_pretrained(model, "dnas/1/torvalds")
tokenizer = AutoTokenizer.from_pretrained("dnas/1/torvalds")
```

---

## API Overview

The FastAPI backend runs on port 8000. Interactive docs at [http://localhost:8000/docs](http://localhost:8000/docs).

| Router | Prefix | Key Endpoints |
|---|---|---|
| Teams | `/teams` | `GET /teams`, `POST /teams`, `GET /teams/{id}`, `DELETE /teams/{id}` |
| Candidates | `/teams/{id}/roles/{slot_id}` | `GET .../search`, `POST .../select`, `POST .../extract-website`, `POST .../extract-resume` |
| Clone DNA | `/teams/{id}/clone-dna` | `GET .../stream` — SSE stream of the full training pipeline |
| Build | `/teams/{id}/build` | `POST .../chat` (SSE), `POST .../orchestrate` (SSE), `GET .../messages` |
| Registry | `/registry` | `GET /registry`, `GET /registry/search`, `GET /registry/{team_id}/{handle}`, `GET /registry/{team_id}/{handle}/download` |

---

## Stack

**Backend:** Python · FastAPI · Peewee (SQLite) · HuggingFace Transformers · PEFT · xAI Grok API

**Frontend:** Nuxt 3 · Vue 3 · Tailwind CSS · Bun

**Models:** configurable via `BASE_MODEL` (default: `Qwen/Qwen2.5-0.5B-Instruct`; supports GPTQ quantized variants up to 27B+)

---

*CLONE.dna · [yconic New England Inter-Collegiate AI Hackathon 2026](https://yconic.com)*
