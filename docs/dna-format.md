# The `.dna` Block Format

A `.dna` block is a self-describing directory artifact containing a LoRA adapter trained on a developer's public work, plus structured metadata for provenance, benchmarking, and consent tracking.

---

## Directory Layout

```
dnas/{team_id}/{github_handle}/
├── adapter_config.json         # PEFT LoRA adapter configuration
├── adapter_model.safetensors   # LoRA adapter weights
├── tokenizer_config.json       # Tokenizer configuration
├── tokenizer.json              # Tokenizer vocabulary
├── special_tokens_map.json     # Special tokens
├── manifest.json               # Block metadata and eval summary
├── eval.json                   # Full training metrics and benchmark scores
├── sources.json                # Source repo provenance
├── consent.json                # Consent and licensing record
└── profile.md                  # Human-readable candidate profile
```

---

## `manifest.json`

Top-level metadata for the block. Used by the registry, the agent router, and external tooling.

```json
{
  "name": "swe-alice-chen",
  "version": "1.0.0",
  "candidate": {
    "handle": "alice-chen",
    "name": "Alice Chen",
    "expertise_domains": ["backend", "distributed-systems", "Go"],
    "consent_verified": true
  },
  "base_model": "Qwen/Qwen2.5-Coder-14B-Instruct-GPTQ-Int4",
  "rank": 32,
  "alpha": 128,
  "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
  "vllm_compatible": true,
  "tags": ["Go", "distributed-systems", "API-design"],
  "eval_summary": {
    "final_loss": 1.42,
    "best_loss": 1.31,
    "style_consistency": 0.87,
    "domain_accuracy": 0.83,
    "humaneval_proxy": 0.74,
    "latency_overhead_ms": 12.8,
    "pair_count": 36,
    "teacher_model": "grok-4"
  }
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `name` | string | Slug: `{role}-{handle}` |
| `version` | string | Semver — increments on retrain |
| `candidate.handle` | string | GitHub handle |
| `candidate.expertise_domains` | string[] | Top skill labels extracted during profiling |
| `candidate.consent_verified` | bool | Whether the developer has authorized minting |
| `base_model` | string | HuggingFace model ID the adapter was trained on |
| `rank` | int | LoRA rank |
| `alpha` | int | LoRA alpha |
| `target_modules` | string[] | Which projection layers have adapters |
| `vllm_compatible` | bool | Whether weights are compatible with vLLM `--enable-lora` |
| `tags` | string[] | Searchable skill/domain tags for registry queries |
| `eval_summary` | object | Abbreviated benchmark scores for registry display |

---

## `eval.json`

Full training and benchmark metrics. Superset of `manifest.eval_summary`.

```json
{
  "pair_count": 36,
  "base_instruct_pairs": 18,
  "tool_use_examples": 24,
  "total_training_samples": 78,
  "epochs": 2,
  "final_loss": 1.42,
  "best_loss": 1.31,
  "loss_history": [2.11, 1.89, 1.74, 1.61, 1.52, 1.45, 1.42],
  "style_consistency": 0.87,
  "domain_accuracy": 0.83,
  "humaneval_proxy": 0.74,
  "latency_overhead_ms": 12.8,
  "training_duration_seconds": 847,
  "lora_rank": 32,
  "lora_alpha": 128,
  "base_model": "Qwen/Qwen2.5-Coder-14B-Instruct-GPTQ-Int4",
  "teacher_model": "grok-4.20-0309-reasoning"
}
```

### Metric definitions

| Metric | Range | How computed |
|---|---|---|
| `style_consistency` | 0–1 | Naming convention dominance, line length variance, comment density, function length uniformity |
| `domain_accuracy` | 0–1 | `0.6 × skill_coverage + 0.4 × domain_keyword_density` across training pairs |
| `humaneval_proxy` | 0–1 | Heuristic: function defs, error handling, type hints, docstrings, import structure |
| `latency_overhead_ms` | ms | Estimated from adapter size in MB |
| `final_loss` | float | Cross-entropy loss at end of training |
| `best_loss` | float | Lowest loss observed during training |

---

## `sources.json`

Full provenance for every repo used to generate training pairs. Required for consent and auditability.

```json
{
  "repos": [
    {
      "name": "alice-chen/ratelimiter",
      "url": "https://github.com/alice-chen/ratelimiter",
      "language": "Go",
      "stars": 412,
      "description": "Token bucket rate limiter with Redis backend",
      "topics": ["golang", "redis", "rate-limiting"],
      "license": "MIT"
    }
  ],
  "collected_at": "2026-03-29T14:22:00Z",
  "total_bytes_collected": 34182
}
```

---

## `consent.json`

Records the consent scope for this block.

```json
{
  "consent_status": "pending",
  "public_repos_only": true,
  "revocable": true,
  "revocation_endpoint": "/registry/{team_id}/{handle}/revoke",
  "licensed_repos_only": true,
  "permitted_licenses": ["MIT", "Apache-2.0"]
}
```

`consent_status` is `"pending"` until the developer explicitly authorizes minting via the registry enrollment flow. Blocks with `"pending"` status are functional but flagged in registry listings.

To soft-delete a block, `POST /registry/{team_id}/{handle}/revoke` — this writes a `revoked.json` marker. The block remains on disk for audit trail but is excluded from registry listings and download endpoints.

---

## `profile.md`

Human-readable candidate summary used by the agent router to match tasks to the right adapter. Read once during orchestration planning; never injected into the inference context window.

```markdown
# Alice Chen (@alice-chen)

**Role:** SWE
**Location:** San Francisco, CA
**Skills:** Go, Distributed Systems, Redis, API Design, gRPC

## Summary
Alice is a backend engineer specializing in high-throughput distributed systems...

## Top Repos
- **ratelimiter** ★412 — Token bucket rate limiter with Redis backend
- **grpc-gateway** ★287 — Type-safe gRPC-to-REST proxy

## Training Stats
- Pairs generated: 36 (from 3 repos)
- Style consistency: 0.87
- Domain accuracy: 0.83

## Loading this block
\`\`\`python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-Coder-14B-Instruct-GPTQ-Int4", device_map="auto")
model = PeftModel.from_pretrained(base, "dnas/1/alice-chen")
tokenizer = AutoTokenizer.from_pretrained("dnas/1/alice-chen")
\`\`\`
```

---

## Loading a Block

### With PEFT (standalone)

```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

base = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-Coder-14B-Instruct-GPTQ-Int4",
    device_map="auto"
)
model = PeftModel.from_pretrained(base, "dnas/1/alice-chen")
tokenizer = AutoTokenizer.from_pretrained("dnas/1/alice-chen")

inputs = tokenizer("Implement a Redis-backed rate limiter in Go:", return_tensors="pt").to("cuda")
outputs = model.generate(**inputs, max_new_tokens=512)
print(tokenizer.decode(outputs[0]))
```

### With vLLM (production)

The adapter weights are standard PEFT safetensors and are compatible with vLLM's `--enable-lora` dynamic loading interface:

```bash
vllm serve Qwen/Qwen2.5-Coder-14B-Instruct-GPTQ-Int4 \
  --enable-lora \
  --lora-modules alice-chen=./dnas/1/alice-chen
```

### Via the Clone.dna API

```bash
# Chat with a cloned candidate (SSE stream)
curl -N -X POST http://localhost:8000/teams/1/build/chat \
  -H "Content-Type: application/json" \
  -d '{"github_handle": "alice-chen", "message": "Design a rate limiter for our API"}'
```

---

## Block Versioning

When a developer ships more public work, their `.dna` block can be updated by rerunning the minting pipeline against the same `output_dir`. The `version` field in `manifest.json` increments (e.g. `1.0.0 → 2.0.0`). v2 reflects a more senior engineer than v1 — the weights encode the delta in their public work.

---

## Format Stability

The `.dna` format is designed as an open spec:
- `adapter_config.json` and `adapter_model.safetensors` follow the PEFT standard exactly — no proprietary extensions
- `manifest.json`, `eval.json`, `sources.json`, `consent.json` follow a versioned schema (current: `v1`)
- `profile.md` is human-readable markdown with no required structure
