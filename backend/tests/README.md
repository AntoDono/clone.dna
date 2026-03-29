# Clone.dna — Backend Tests

```bash
cd backend
uv run pytest tests/ -v
```

---

## Test Files

### `test_dna_packaging.py`

Validates the structure and schema of every `.dna` block in `dnas/`. Scans the directory at test time, so it covers all blocks minted during a run.

**Covers:**
- `manifest.json` — required keys (`name`, `version`, `candidate`, `base_model`, `rank`, `alpha`, `eval_summary`), types, and value ranges (`rank > 0`, `alpha > 0`, loss values are floats)
- `eval.json` — training metrics present (`pair_count`, `final_loss`, `best_loss`, `style_consistency`, `domain_accuracy`)
- `sources.json` — repos array non-empty, each entry has `name` and `url`
- `consent.json` — `public_repos_only` is a bool, `revocable` is a bool
- `profile.md` — file exists and is non-empty
- Adapter weights — `adapter_config.json` and `adapter_model.safetensors` present (skipped for emergency-calibrated blocks)

**Block type detection:** A block is classified as "emergency-calibrated" (no real adapter weights) if `manifest.json` lacks an `eval_summary.style_consistency` key. Weight-presence assertions are skipped for those blocks.

---

### `test_eval_metrics.py`

Unit tests for the four evaluation metric functions in `trainer/training.py`.

**Covers:**

`compute_style_metrics(code_samples: list[str]) → dict`
- Empty input returns `consistency_score = 0`
- Single-sample input handled without division errors
- Pure snake_case code scores high on naming consistency
- Mixed naming conventions score lower
- Returned dict always contains: `consistency_score`, `naming_convention`, `avg_line_length`, `comment_density`, `avg_function_length`

`compute_domain_accuracy(pairs: list[dict], candidate_profile: dict) → float`
- Empty pairs returns `0.0`
- Pairs referencing the candidate's own skills score higher
- Score is bounded `[0.0, 1.0]`

`compute_humaneval_proxy(code_samples: list[str]) → float`
- Empty input returns `0.0`
- Code with type hints, docstrings, error handling, and imports scores above `0.5`
- Bare code with no structure scores low
- Score is bounded `[0.0, 1.0]`

`estimate_latency_overhead_ms(adapter_dir: str) → float`
- Returns a positive float for a valid adapter directory
- Returns a default estimate if the directory is missing

---

### `test_tool_parsing.py`

Tests the tool-call parsing and sandboxed execution pipeline.

**Covers:**

`_parse_tool_calls(text: str) → list[dict]` (from `trainer/inference.py`)
- Correctly extracts JSON from `<tool_call>{"name": "write_file", ...}</tool_call>` blocks
- Returns empty list when no tool call tags present
- Handles malformed JSON inside tags without raising (returns empty list)
- Handles multiple tool calls in a single response

`execute_tool(name, arguments, workspace_dir) → tuple[str, bool]` (from `trainer/tools.py`)
- `write_file` creates the file and returns success
- `read_file` returns file contents
- `list_files` returns directory listing
- `run_command` captures stdout/stderr, respects 30s timeout
- Unknown tool name returns `(error_message, False)`

`_safe_path(workspace_dir, path) → str` (from `trainer/tools.py`)
- Paths within the workspace resolve correctly
- Path traversal attempts (`../../etc/passwd`) raise `PermissionError`
- Absolute paths outside the workspace raise `PermissionError`

---

## Running a subset

```bash
# Single file
uv run pytest tests/test_eval_metrics.py -v

# Single test
uv run pytest tests/test_eval_metrics.py::test_style_metrics_snake_case -v

# With output (useful for debugging training metrics)
uv run pytest tests/ -v -s
```
