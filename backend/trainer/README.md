# Clone.dna — Trainer Module

The `trainer/` package owns the entire `.dna` minting pipeline: fetching source code from GitHub, generating instruction-response training pairs via Grok, running QLoRA fine-tuning, packaging the adapter as a `.dna` block, and serving inference with per-request adapter hot-swapping and a sandboxed tool-use agent loop.

---

## Module Map

| File | Responsibility |
|---|---|
| `github.py` | Fetch raw source code from a candidate's top public repos |
| `grok.py` | Call Grok-4 to generate `(instruction, response)` training pairs and a persona system prompt |
| `training.py` | QLoRA fine-tuning loop, eval metric computation, `.dna` block packaging |
| `model_utils.py` | Base model loading, optional GPTQ quantization, cached model resolution |
| `inference.py` | Base model cache, LoRA adapter hot-swap, streaming generation, tool-use agent loop |
| `orchestrator.py` | PM orchestration: Grok assigns per-specialist tasks from the PM's plan |
| `tools.py` | Sandboxed tool executors (`read_file`, `write_file`, `run_command`, …) |
| `tool_examples.py` | 24 hardcoded tool-use `(instruction, response)` pairs injected into every training run |

---

## Stage 1 — Source Code Collection (`github.py`)

`collect_training_data(candidate, emit)` fetches usable source code from the candidate's top 3 public repos by star count.

**Per repo:**
- Fetches the HEAD tree recursively via the GitHub Contents API
- Filters to a fixed set of code extensions: `.py .ts .tsx .js .jsx .go .rs .java .cpp .c .h .rb .swift .kt .md .txt`
- Skips directories named `test`, `vendor`, `node_modules`, `.github`, `dist`, `__pycache__`
- Selects the 4 shortest-path blobs (top-level files preferred)
- Downloads each blob (base64 decoded), capped at **12,000 bytes per blob**
- Annotates output with `// FILE: {path}` separators

Returns a list of `{"repo": str, "code": str}` dicts — one entry per repo with all blobs concatenated.

**Authentication:** Set `GITHUB_TOKEN` to raise the rate limit from 60 to 5,000 requests/hour.

---

## Stage 2 — Training Pair Generation (`grok.py`)

`generate_training_pairs(candidate, code_blobs, emit)` calls Grok-4 for each code blob to produce `(instruction, response)` pairs.

### Prompt design

The Grok teacher receives:
- A system message describing the candidate (name, GitHub handle, top skills, role)
- The raw source code blob
- An instruction to produce exactly **6 pairs** (`PAIRS_PER_BLOB = 6`) as a JSON array

Each pair captures a real task that would naturally produce the developer's actual code as the answer. The instruction side is synthetic; the response side is the developer's real output.

### Output

- Parses the JSON array, filters for dicts containing both `"instruction"` and `"response"` keys
- Returns a flat list — 3 repos × up to 6 pairs/blob = **up to 18 pairs** minimum (more if repos have multiple blobs)
- Results are **cached** to `grok_cache/{handle}.json` as `{"pairs": [...], "system_prompt": "..."}` — reruns skip the API call entirely

### System prompt generation

`generate_system_prompt(candidate, code_sample)` makes a separate Grok call to produce a **200–350 word first-person persona prompt** capturing the candidate's:
- Coding philosophy and aesthetic preferences
- Communication and explanation style
- Technical strengths and domain vocabulary
- How they approach architectural decisions

Fallback: if the Grok call fails, a minimal template prompt is constructed from the candidate's profile fields.

### Model

Pair generation uses `grok-4.20-0309-reasoning`. Profile extraction (in `extractor/schema.py`) uses `grok-4.20-0309-non-reasoning`.

---

## Stage 3 — QLoRA Training (`training.py`)

`train_lora(candidate, pairs, system_prompt, output_dir, emit)` fine-tunes a LoRA adapter on the generated pairs.

### Training data mix

Every training run combines three sources to prevent catastrophic forgetting:

| Source | Ratio | Purpose |
|---|---|---|
| Candidate pairs | baseline | Capture the developer's style and domain |
| Alpaca-cleaned (`yahma/alpaca-cleaned`) | 50% of candidate pairs | Preserve general instruction-following ability |
| Tool-use examples (`tool_examples.py`) | 24 fixed examples | Preserve structured tool-call formatting |

### LoRA configuration

| Hyperparameter | Value |
|---|---|
| Rank (`r`) | 32 |
| Alpha | 128 |
| Dropout | 0.05 |
| Target modules | `q_proj`, `k_proj`, `v_proj`, `o_proj` |
| Optimizer | AdamW (`lr=2e-4`) or `paged_adamw_8bit` (QLoRA) |
| Per-device batch size | 2 |
| Gradient accumulation steps | 4 (effective batch = 8) |
| Epochs | 2 |
| Max sequence length | 2048 |

### Sequence formatting

Pairs are formatted via the tokenizer's `apply_chat_template` (chat-style with system + user + assistant turns). Fallback: markdown `### Instruction / ### Response` format for tokenizers without a chat template.

### Eval metrics (computed post-training)

Four metrics are computed and stored in `eval.json`:

**Style Consistency** (`compute_style_metrics`):
Analyzes the candidate's code for:
- Naming convention dominance (snake_case vs. camelCase)
- Average line length variance
- Comment density (comment lines / total lines)
- Average function length

Returns a `consistency_score` between 0 and 1.

**Domain Accuracy** (`compute_domain_accuracy`):
Keyword matching between the candidate's skills/languages/repo topics and the training pair content.
`score = 0.6 × coverage + 0.4 × density`

**HumanEval Proxy** (`compute_humaneval_proxy`):
Heuristic code quality score based on 5 indicators: function definitions, error handling, type hints, docstrings, import organization.

**Latency Overhead** (`estimate_latency_overhead_ms`):
Estimated inference latency overhead from adapter size in MB.

### SSE events emitted during training

```json
{"event": "phase",   "data": {"phase": "training",  "candidate": "handle"}}
{"event": "step",    "data": {"step": 12, "total": 48, "loss": 1.82, "candidate": "handle"}}
{"event": "loss",    "data": {"loss": 1.74, "bestLoss": 1.68, "candidate": "handle"}}
{"event": "phase",   "data": {"phase": "saving",    "candidate": "handle"}}
{"event": "path",    "data": {"path": "dnas/1/handle", "candidate": "handle"}}
```

---

## Stage 4 — `.dna` Block Packaging

After training, `train_lora` writes the following to `dnas/{team_id}/{handle}/`:

| File | Contents |
|---|---|
| `adapter_config.json` | PEFT LoRA config (auto-generated) |
| `adapter_model.safetensors` | LoRA adapter weights |
| `tokenizer_config.json` + supporting files | Tokenizer for standalone loading |
| `manifest.json` | Candidate metadata, base model, rank/alpha, eval summary, vLLM flag |
| `eval.json` | Full training metrics: loss history, pair counts, all 4 benchmark scores |
| `sources.json` | Repo provenance: name, URL, language, stars, description, topics |
| `consent.json` | Opt-in record: consent scope, public-repos-only flag, revocability note |
| `profile.md` | Human-readable candidate summary + PEFT loading snippet |

---

## Inference Engine (`inference.py`)

### Model lifecycle

The base model is loaded **once** at server startup (`warmup_model()`) and shared across all requests. Adapters are hot-swapped per-request.

```
Server start → warmup_model() → base model in VRAM
                                      │
                          ┌───────────┴───────────┐
                    load_adapter("alice")    load_adapter("bob")
                    set_adapter("alice")     set_adapter("bob")
                          └───────────┬───────────┘
                                 inference
```

Due to GPTQ quantization constraints, only **one adapter is resident at a time**. Loading a new adapter evicts the previous one.

### Reference-counted VRAM eviction

When training jobs need VRAM, `borrow_model_for_training()` is used as a context manager:

```python
with borrow_model_for_training():
    train_lora(...)
```

- First training job evicts the inference model from VRAM
- Subsequent concurrent jobs proceed directly (model already evicted)
- Last job to exit reloads the model automatically
- Reference count is thread-safe via `threading.Lock`

This allows `NUM_OF_PARALLEL_TRAINING` concurrent training runs without premature model reloads.

### Tool-use agent loop (`agent_chat`)

`agent_chat(messages, adapter_path, system_prompt, emit, workspace_dir)` runs an iterative generate → parse → execute loop:

```
generate response
    │
    ├── contains <tool_call> JSON? ──→ execute_tool() → append tool result → regenerate
    │                                         (max MAX_TOOL_ITERATIONS = 10 iterations)
    └── no tool calls → return visible text
```

**Filtering:** `<think>...</think>` blocks and raw `<tool_call>` JSON are stripped from the visible output streamed to the frontend. Users see only the final assistant text.

**Inline fallback:** If no `<tool_call>` tags are found but the response contains a markdown JSON block that matches a tool schema, it is extracted and executed as a tool call.

### Available tools (via `tools.py`)

| Tool | Description |
|---|---|
| `write_file` | Create or overwrite a file in the sandbox |
| `read_file` | Read up to 8,000 chars from a file |
| `create_folder` | `mkdir -p` in the sandbox |
| `list_files` | List up to 50 entries in a directory |
| `edit_file` | Find-and-replace (first occurrence) in a file |
| `run_command` | Run a shell command with a 30s timeout |
| `search_registry` | Query the local `.dna` registry by skills or domain |

All file operations are path-validated via `_safe_path()` to prevent escaping `AGENT_WORKSPACE_DIR`.

---

## PM Orchestration (`orchestrator.py`)

`assign_tasks(pm_response, specialists, workspace_context)` calls Grok to derive one short task per specialist from the PM's plan.

Input:
- The PM's full generated text
- A list of `{"handle": str, "role": str}` specialist dicts
- A directory listing of the current workspace (so Grok can reference existing files)

Output: `[{"handle": str, "task": str}, ...]` — one entry per specialist.

Fallback: if the Grok call fails, every specialist receives the original user prompt.

---

## GPTQ Quantization (`model_utils.py`)

`resolve_model_path(model_name)` handles optional local quantization:

- If `QUANTIZATION_BITS` is not set: returns `model_name` unchanged
- If set to `4` or `8`:
  - Checks `QUANTIZED_MODELS_DIR` cache first
  - If missing: downloads the full-precision model, quantizes using wikitext-2 calibration, saves to disk
  - Falls back to the original model name on quantization error

This is separate from loading a pre-quantized model like `Qwen2.5-Coder-14B-Instruct-GPTQ-Int4` directly via `BASE_MODEL` (which requires no quantization step).

---

## Emergency Calibration Mode

For demos without GPU access, append `?emergency_calibration=1` to the clone-dna stream URL:

```
GET /teams/{id}/clone-dna/stream?emergency_calibration=1
```

This bypasses all real training steps and emits a realistic simulated progress stream with randomized loss curves and delays. The `.dna` block metadata files are written normally but no adapter weights are produced. The frontend is indistinguishable from a real training run.
