# Clone.dna — Backend

The Clone.dna backend is a FastAPI application that drives the entire `.dna` minting pipeline: extracting candidate profiles from GitHub, websites, and resumes; generating instruction-response training pairs via Grok; training LoRA adapters; serving inference against hot-swapped adapters; and exposing a talent registry.

## Stack

- **Python 3.11+** managed by `uv`
- **FastAPI** — async HTTP + SSE streaming
- **Peewee** — SQLite ORM (`clone_dna.db`)
- **HuggingFace Transformers + PEFT** — LoRA training and adapter loading
- **xAI Grok API** — 70B teacher model for training-pair generation
- **SQLite** — lightweight persistence (teams, roles, messages, clone jobs)

## Setup

```bash
cd backend
cp .env.example .env     # fill in XAI_API_KEY; GITHUB_TOKEN is optional but recommended
uv sync                  # creates .venv and installs all dependencies
uv run python main.py    # starts on http://localhost:8000
```

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

On startup the server pre-warms the base model (loaded once into VRAM, reused across all inference requests).

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `XAI_API_KEY` | — | **Required.** Grok API key for training pair generation |
| `GITHUB_TOKEN` | — | Optional. Raises GitHub API rate limit to 5000 req/hr |
| `BASE_MODEL` | `Qwen/Qwen2.5-Coder-14B-Instruct-GPTQ-Int4` | HuggingFace model ID or local path |
| `DB_PATH` | `clone_dna.db` | SQLite database path |
| `DNAS_DIR` | `dnas` | Root directory where `.dna` blocks are stored |
| `GROK_CACHE_DIR` | `grok_cache` | Cache for Grok-generated training pairs (avoids re-calling the API on reruns) |
| `CUDA_VISIBLE_DEVICES` | — | GPU index(es), e.g. `0` or `0,1` |
| `QUANTIZATION_BITS` | — | `4` or `8` to quantize `BASE_MODEL` locally via GPTQ on first run |
| `QUANTIZED_MODELS_DIR` | `quantized_models` | Cache dir for locally quantized models |
| `NUM_OF_PARALLEL_TRAINING` | `1` | Max concurrent LoRA training jobs (limited by VRAM) |
| `AGENT_WORKSPACE_DIR` | `agent-workspace` | Sandbox directory for agent tool use (file read/write/run) |

## Directory Structure

```
backend/
├── main.py                  # FastAPI app factory, startup pre-warm, router registration
├── db.py                    # Peewee models (Team, RoleSlot, Message, CloneJob)
├── models.py                # Pydantic request/response schemas
│
├── extractor/               # Candidate profile extraction
│   ├── github.py            # GitHub API: repos, languages, commit stats, README scraping
│   ├── website.py           # Playwright/httpx scraping for personal sites and portfolios
│   ├── resume.py            # PDF/DOCX resume parsing via Grok
│   └── schema.py            # Shared CandidateProfile dataclass
│
├── trainer/                 # .dna minting pipeline
│   ├── grok.py              # Grok-4 client: generates (instruction, response) training pairs
│   ├── github.py            # Repo downloader used during training (separate from extractor)
│   ├── training.py          # PEFT LoRA training loop, manifest/eval/sources/consent writes
│   ├── model_utils.py       # Model loading, quantization, VRAM estimation helpers
│   ├── inference.py         # Adapter hot-swap, single-candidate and multi-candidate chat
│   ├── orchestrator.py      # PM orchestration: PM plans → Grok assigns → specialists respond
│   ├── tools.py             # Agent tool definitions (read_file, write_file, run_command)
│   └── tool_examples.py     # Few-shot tool-use examples injected into training data
│
└── routes/                  # FastAPI routers
    ├── teams.py             # CRUD for teams and role slots
    ├── candidates.py        # Candidate search, selection, website/resume extraction
    ├── clone_dna.py         # SSE stream for the full minting pipeline
    ├── build.py             # Chat (SSE), PM orchestration (SSE), message history
    └── registry.py          # Talent registry: browse, search, download .dna zips
```

## API Routes

### Teams — `/teams`

| Method | Path | Description |
|---|---|---|
| `GET` | `/teams` | List all teams |
| `POST` | `/teams` | Create a team |
| `GET` | `/teams/{id}` | Get team with role slots and candidates |
| `DELETE` | `/teams/{id}` | Delete team and all associated data |

### Candidates — `/teams/{id}/roles/{slot_id}`

| Method | Path | Description |
|---|---|---|
| `GET` | `.../search` | Search GitHub by username and return a candidate profile |
| `POST` | `.../select` | Assign a GitHub candidate to a role slot |
| `POST` | `.../extract-website` | Extract a candidate profile from a URL (personal site / portfolio) |
| `POST` | `.../extract-resume` | Extract a candidate profile from an uploaded PDF/DOCX resume |
| `DELETE` | `.../candidate` | Clear the candidate from a role slot |

### Clone DNA — `/teams/{id}/clone-dna`

| Method | Path | Description |
|---|---|---|
| `GET` | `.../stream` | **SSE stream** of the full pipeline: collect repos → generate pairs via Grok → train LoRA → write `.dna` block |

The stream emits JSON events at each pipeline stage so the frontend can display live progress. The job is idempotent — if a `.dna` block already exists for a candidate it is overwritten.

### Build — `/teams/{id}/build`

| Method | Path | Description |
|---|---|---|
| `POST` | `.../chat` | **SSE stream** — single-candidate chat; hot-swaps the LoRA adapter for the selected role |
| `POST` | `.../compare` | **SSE stream** — side-by-side: same prompt through raw base model and adapter-loaded model |
| `POST` | `.../orchestrate` | **SSE stream** — PM orchestration; PM plans the response, Grok assigns tasks, each specialist responds in sequence |
| `GET` | `.../messages` | Full message history for the team's build workspace |
| `GET` | `.../artifacts` | Latest orchestration artifact plus recent workspace tool-audit events |

### Registry — `/registry`

| Method | Path | Description |
|---|---|---|
| `GET` | `/registry` | List all minted `.dna` blocks with metadata |
| `GET` | `/registry/search` | Search blocks by candidate handle or skills |
| `GET` | `/registry/{team_id}/{handle}` | Get a specific block's manifest and eval |
| `GET` | `/registry/{team_id}/{handle}/download` | Download the full `.dna` block as a `.zip` |

## Training Pipeline

The minting pipeline (`clone_dna` route → `trainer/`) runs these stages in sequence:

1. **Repo collection** (`trainer/github.py`) — fetches the candidate's top public repos, enforces an MIT/Apache-2.0 license policy from GitHub repo metadata, then downloads source files up to a configurable token budget.

2. **Pair generation** (`trainer/grok.py`) — sends code chunks to Grok-4 (70B teacher). The teacher reads the developer's actual code and generates the *instruction* side of each pair (the problem statement, architectural context, or task description that would naturally produce that code). The developer's code is the *completion*. Results are cached to `GROK_CACHE_DIR` so reruns skip the API call. Typically generates 18–60 pairs per candidate.

3. **LoRA training** (`trainer/training.py`) — freezes the base model and trains a LoRA adapter (rank=32, alpha=128) using PEFT + HuggingFace `Trainer`. Training pairs are mixed with Alpaca-cleaned examples (50% ratio) and 24 tool-use demonstrations to preserve general capability.

4. **`.dna` block write** — saves the adapter weights plus metadata files to `dnas/{team_id}/{handle}/`:
   - `manifest.json` — candidate metadata, base model, rank/alpha, eval summary
   - `eval.json` — loss history, pair counts, benchmark scores
   - `sources.json` — provenance for every source repo
   - `consent.json` — opt-in record (consent scope, source URLs, revocation endpoint, public-repos-only flag)
   - `teacher_config.json` — exact Grok prompt templates used for pair generation (system + user templates, temperature, model)
   - `profile.md` — human-readable candidate profile used by the agent router

## Inference & Agent Loop

`trainer/inference.py` manages the loaded model:

- **Adapter hot-swap** — the base model is loaded once at startup; adapters are applied with PEFT's `set_adapter` / `load_adapter` on every chat request, enabling multiple role slots to share one GPU copy of the base weights.
- **Tool-use agent loop** — the model can emit structured tool calls (`read_file`, `write_file`, `run_command`, `list_files`, `search_registry`) that the backend executes inside `AGENT_WORKSPACE_DIR` and feeds back as tool results, enabling the clone to actually write and run code.
- **Command policy + audit trail** — `run_command` executes a single local command with no shell chaining, redirects, or network/destructive prefixes, and every tool invocation is appended to `.clone_dna/tool_audit.jsonl` inside the team workspace.
- **Reference-counted eviction** — when training jobs need VRAM, `borrow_model_for_training()` evicts the inference model. The first training job evicts; intermediate jobs proceed directly; the last job out reloads the model automatically.

## PM Orchestration Flow

The orchestration endpoint (`POST /teams/{id}/build/orchestrate`) coordinates a multi-expert build session across all cloned candidates on a team. The flow runs in three stages, all streamed over SSE:

### Stage 1 — PM Plans

The **lead candidate** (the PM role slot, or the first cloned candidate if no PM exists) receives the user's prompt and produces a task plan. The lead's LoRA adapter is hot-swapped in, and the response is generated through the full agent loop (including tool calls). The PM's plan is streamed token-by-token to the frontend and saved to the `orchestrate` message thread.

### Stage 2 — Grok Assigns Tasks

The PM's plan is sent to **Grok-4** (`trainer/orchestrator.assign_tasks()`) along with the list of specialist candidates and their roles. Grok reads the plan and returns a JSON array of `{"handle", "task"}` assignments — one short task sentence per specialist. If the Grok call fails, every specialist receives the original user prompt as a fallback.

The assignment prompt includes a workspace listing (files already created by prior turns) so Grok can direct specialists to build on existing work rather than starting from scratch.

### Stage 3 — Specialists Respond

Each specialist runs **sequentially** — one at a time, in assignment order. For each specialist:

1. Their LoRA adapter is hot-swapped onto the base model
2. They receive their assigned task as a single-message history
3. They generate a response through the agent loop (with tool access to the shared workspace)
4. Their response is streamed to the frontend and saved to the `orchestrate` thread

Because specialists share a workspace directory (`agent-workspace/{team_id}/`), each specialist can read and build on files created by prior specialists in the same orchestration turn.

Every orchestration run is also persisted to `.clone_dna/orchestrations/<timestamp>.json` and mirrored to `.clone_dna/latest_orchestration.json`, so the PM plan, specialist assignments, and final outputs are inspectable after the SSE stream ends.

### SSE Event Sequence

```
{"phase": "start", "prompt": "..."}              ← orchestration begins
{"speaker": "lead-handle", "token": "..."}        ← PM tokens stream
{"phase": "specialist", "speaker": "...", "task": "..."}  ← specialist assigned
{"speaker": "spec-handle", "token": "..."}        ← specialist tokens stream
  ... (repeats for each specialist) ...
{"done": true}                                    ← orchestration complete
```

## SSE Event Schemas

### Clone DNA stream (`GET /teams/{id}/clone-dna/stream`)

```json
{"event": "phase",     "data": {"phase": "collecting|generating|training|saving", "candidate": "handle"}}
{"event": "message",   "data": {"message": "Fetching repos...", "candidate": "handle"}}
{"event": "step",      "data": {"step": 12, "total": 48, "loss": 1.82, "candidate": "handle"}}
{"event": "loss",      "data": {"loss": 1.74, "bestLoss": 1.68, "candidate": "handle"}}
{"event": "path",      "data": {"path": "dnas/1/handle", "candidate": "handle"}}
{"event": "error",     "data": {"error": "...", "candidate": "handle"}}
{"event": "done",      "data": {"total": 4, "succeeded": 4, "failed": 0}}
{"event": "heartbeat", "data": {}}
```

### Build chat stream (`POST /teams/{id}/build/chat`)

```json
{"event": "token",       "data": {"token": "Here is", "handle": "alice-chen"}}
{"event": "thinking",    "data": {"on": true}}
{"event": "tool_call",   "data": {"name": "write_file", "arguments": {"path": "main.go", "content": "..."}}}
{"event": "tool_result", "data": {"name": "write_file", "output": "OK", "success": true}}
{"event": "done",        "data": {}}
```

### Orchestrate stream (`POST /teams/{id}/build/orchestrate`)

```json
{"event": "phase",    "data": {"phase": "start", "prompt": "Build a REST API"}}
{"event": "speaker",  "data": {"handle": "pm-handle", "role": "pm"}}
{"event": "token",    "data": {"token": "I'll break this into...", "handle": "pm-handle"}}
{"event": "phase",    "data": {"phase": "specialist", "speaker": "alice-chen", "task": "Implement the user endpoints"}}
{"event": "token",    "data": {"token": "Sure, starting with...", "handle": "alice-chen"}}
{"event": "done",     "data": {}}
```

### Headhunt stream (`GET /teams/{id}/headhunt/stream`)

```json
{"event": "candidate", "data": {"role": "swe", "github_handle": "...", "name": "...", "skills": [...], ...}}
{"event": "done",      "data": {"total": 15, "cached": false}}
{"event": "error",     "data": {"role": "pm", "error": "GitHub rate limit exceeded"}}
```

---

## Data Model (SQLite)

| Table | Key Columns |
|---|---|
| `Team` | `id`, `name`, `created_at` |
| `RoleSlot` | `id`, `team_id` (FK), `role` (`pm`/`swe`/`designer`), `slot_index`, `filled` (bool) |
| `Candidate` | `id`, `slot_id` (FK), `github_handle`, `name`, `avatar_url`, `bio`, `location`, `followers`, `public_repos`, `skills` (JSON), `soft_skills` (JSON), `languages` (JSON), `top_repos` (JSON), `description`, `system_prompt`, `dna_cloned` (bool), `dna_path`, `dna_cloned_at` |
| `ChatMessage` | `id`, `team_id` (FK), `thread` (handle or `"orchestrate"`), `sender`, `content`, `created_at` |

## Loading a `.dna` Block Externally

Any `.dna` block can be loaded outside the backend with PEFT:

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-Coder-14B-Instruct-GPTQ-Int4", device_map="auto")
model = PeftModel.from_pretrained(base, "dnas/1/torvalds")
tokenizer = AutoTokenizer.from_pretrained("dnas/1/torvalds")
```

The adapter weights are standard PEFT safetensors and are compatible with vLLM's `--enable-lora` dynamic loading interface.
