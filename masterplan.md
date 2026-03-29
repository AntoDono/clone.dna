# CLONE.dna

**Hire the Mind. Not the Body.**

yconic New England Inter-Collegiate AI Hackathon — March 28–29, 2026 · Providence, RI
Track: NVIDIA Supercomputer Hack (DGX Spark + $3,000)

---

## 1. Vision Clarity

**North Star:** The candidate's public work is the signal. The .dna file is the executable benchmark. The hire is the final step — not the first.

Hiring is broken at the evaluation layer. The numbers prove it at scale.

The U.S. staffing and recruiting market is projected to hit **$183.3 billion in 2026** (Staffing Industry Analysts). Within that, the **developer tools and technical evaluation segment** — coding assessments, technical screening platforms, take-home infrastructure, and AI-assisted interviewing — represents a fast-growing $4–8B slice growing at 22%+ CAGR, and it is the layer DNA Blocks directly replaces. Tech and engineering roles routinely cost companies **$8,000–$28,000+ per hire** in recruiter fees, sourcing, and interviewing time. Average time-to-hire still sits at 44–90 days. A documented **46% of new hires fail within 18 months** (Leadership IQ), generating an additional **$17,000–$240,000 per bad hire** in lost productivity, re-recruiting, and onboarding waste.

The core dysfunction is an evaluation problem: companies are making $150K+ annual commitments based on a 45-minute conversation and a self-reported document. Meanwhile, the strongest signal of a developer's ability — their public work — sits untouched in plain sight.

DNA Blocks turns that public work into an executable benchmark. Not a replacement for human judgment. A far better input to it.

**The hiring loop today vs. with DNA Blocks:**

- **Today:** Post job → wait weeks → screen 200 resumes → interview 10 people → hire 1 → pray they perform → pay $150K/year + $20–30K recruiter fee
- **DNA Blocks:** Identify candidates by actual output → mint a .dna block from their public work → load it into your codebase for evaluation in minutes → test their coding patterns on your actual problems → then decide if you want to hire the human

The .dna file is a new primitive: a portable, benchmarked LoRA adapter that encodes a developer's demonstrated domain working ability — how they decompose problems, which architectural patterns they reach for, what tradeoffs they make under real constraints — trained directly from their verified public contributions. It doesn't claim to replicate a person's mind. It does something more useful: it makes their demonstrated expertise testable, reusable, and comparable — before you spend a dollar on recruiting.

---

## 2. Technical Depth

### 2.1 What a .dna File Actually Is — and What It Isn't

A .dna block is a LoRA adapter trained on a developer's public work. The 70B teacher model reads their actual code and generates the instruction side of each training pair — the problem statement, architectural context, or task description that would naturally produce that code. The developer's code is the completion. This is not synthetic data generation. It is supervised fine-tuning on real, human-written output, with the teacher supplying the missing prompt context that GitHub never recorded.

What this captures empirically: **domain working ability** — how a developer decomposes problems, which architectural patterns they reach for, how they handle edge cases in their domain, what tradeoffs they make under real constraints. A senior distributed systems engineer trained into a .dna block will approach a rate-limiting problem differently than a frontend specialist. That difference is in the weights, not in a system prompt.

What a .dna block does not claim to do: it does not replicate judgment under novel pressure, transfer intuition, or replace an interview. It makes a developer's demonstrated problem-solving approach testable before you spend a dollar on recruiting. That is a more precise and more useful claim than "AI that thinks like them" — and it is verifiable. Every block ships with benchmark scores. Load it against your actual codebase and measure.

**Anatomy of a .dna file:**

- **manifest.json** — Candidate handle, expertise domains, base model compatibility hash, version, training sources (GitHub repos, papers), benchmark scores, file size, quantization level
- **profile.md** — Human-readable candidate profile: what they've built, what domains they operate in, what the block is optimized for. Used by the agent router for expertise selection. Read once by the router, never injected into context
- **weights/** — Adapter weights in safetensors format (adapter_config.json + adapter_model.safetensors), compatible with vLLM's LoRA loading interface
- **config.yaml** — Integration config: target layer indices, quantization format (INT4/INT8/FP16), rank, alpha scaling factor, memory footprint estimate
- **eval.json** — Benchmark results: HumanEval, MBPP, domain-specific evals, style consistency metrics. Companies know exactly what they're getting before loading
- **sources.json** — Full provenance: links to all public repos and contributions used for training. Every .dna block is traceable to its source material
- **consent.json** — Opt-in record: confirmation that the candidate has authorized their public work for adapter training via the DNA Blocks developer registry (see Section 3)

**Key properties:**

- **Portable** — works on any compatible base model (compatibility verified via model hash in manifest). Train once, deploy anywhere
- **Quantizable** — compress to INT4/INT8 for lightweight deployment. A 50MB fingerprint of a developer's patterns
- **Versionable** — as a developer ships more public work, their .dna block can be updated. v2.0 reflects a more senior engineer than v1.0
- **Hot-swappable** — swap expertise at inference time in milliseconds via vLLM's dynamic adapter API. No restart. No redeployment
- **Composable** — load different .dna blocks for different phases of a project: system design, implementation, testing, documentation

### 2.2 The AI Headhunter: How It Works

The AI Headhunter is the autonomous agent layer sitting on top of DNA Blocks. It handles the full evaluation pipeline automatically.

**Stage 1 — Candidate Discovery**
The agent takes a project description or role requirement and searches GitHub semantically — not by keyword, but by analyzing code quality, architectural patterns, commit history depth, and domain specificity. It identifies developers whose demonstrated work matches the need.

**Stage 2 — Profile Building**
For each candidate, the agent builds a structured profile: languages, frameworks, coding patterns, documentation style, problem decomposition approach, domain expertise. This becomes the profile.md in the .dna file and the basis for registry search.

**Stage 3 — .dna Block Minting (on DGX Spark)**
The 70B teacher model on the DGX reads the candidate's public work and generates the instruction side of each training pair — the problem statement, architectural context, or task description that would naturally produce that code. The developer's actual code is the completion. The student adapter is trained on these pairs. The result is a .dna block that applies their problem-solving patterns to new tasks in their domain.

**Stage 4 — Project Evaluation**
The user describes their project or pastes their actual codebase context. The agent loads the relevant .dna blocks and generates contributions in each expert's style — giving the hiring team a concrete, task-specific sample before any interview is scheduled.

### 2.3 Runtime Layer: Built on vLLM

The DNA Blocks runtime is built on top of vLLM's production multi-LoRA serving infrastructure. We are not writing custom weight-injection hooks. vLLM already provides:

- Dynamic adapter loading and unloading via REST API
- Per-request adapter selection — each inference call specifies which adapter to use via the model parameter, enabling true per-request expertise routing
- LRU caching — frequently used DNA blocks stay in GPU memory automatically
- OpenAI-compatible API — any application already calling OpenAI can use DNA Blocks as a drop-in replacement
- Efficient VRAM management — memory allocation, KV-cache management, and concurrent adapter serving handled natively

**What DNA Blocks adds on top of vLLM:**

- The .dna packaging format — standardized, self-describing expertise packages with manifest, candidate profile, benchmarks, consent record, and source provenance. vLLM expects loose adapter files; DNA Blocks wraps them into a structured, auditable artifact
- The Talent Registry — a searchable marketplace where .dna files are published, discovered, and loaded. Browse by skill, domain, coding style, benchmark score
- The AI Headhunter agent — discovers candidates, evaluates their public work, and mints .dna blocks autonomously
- Agent-native project routing — an LLM tool schema that lets the project agent autonomously select which .dna to load for each task
- The training pipeline — automated public-work collection, synthetic data generation, training, quantization, packaging, and registry publishing on DGX Spark

**On "zero context tokens consumed":** This refers specifically to the expertise signal itself. In a traditional RAG or few-shot prompting approach, you would inject code examples, style guides, or candidate summaries into the context window to influence output — consuming hundreds to thousands of tokens per request. With a loaded .dna adapter, the style and pattern signal lives in the weights, not the context. The task, codebase snippets, and instructions still consume context normally. The expertise layer is free.

### 2.4 Runtime Flow

1. **Project Analysis** — the agent analyzes the incoming task, extracts requirements, identifies what expertise domain is needed
2. **Expertise Selection** — the agent calls the select_expert tool, which queries the registry and matches requirements to available .dna files using profiles and eval scores
3. **Dynamic Loading** — the runtime calls vLLM's load_lora_adapter endpoint with the selected .dna adapter path
4. **Inference** — the request is sent to vLLM routing to the loaded adapter. Context window is fully available for the actual task
5. **Swap** — for the next task phase, a different .dna is loaded. Clean handoff, no weight collision

### 2.5 Training Pipeline (on DGX Spark)

The DGX Spark is the mint — the .dna factory.

**Pipeline stages:**

- **Input:** Candidate's public GitHub repos, PRs, code reviews, technical blog posts (MIT/Apache-licensed only, consent-verified)
- **Teacher model (70B+ on DGX):** Reads the candidate's work and generates synthetic instruction-response pairs capturing their coding style, domain vocabulary, and pattern heuristics. Requires 128GB unified memory — physically cannot run on consumer hardware or standard cloud instances. The DGX Spark is not a nice-to-have; it is the minimum viable hardware for this step
- **Student adapter training:** Freeze base model, train LoRA adapter on synthetic data using PEFT + TRL with FlashAttention-2 and BF16
- **Output:** Quantized, benchmarked, packaged .dna block published to registry

**Training hyperparameters (fully reproducible):**
LoRA rank=64, alpha=128, dropout=0.05, target modules: q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj. Optimizer: AdamW (lr=1e-4, weight_decay=0.01, betas=(0.9, 0.999)). Batch size=8, 2 epochs, warmup ratio=0.03, max sequence length=4096. Every .dna block ships with its exact training config.json for full reproducibility.

### 2.6 API Design

```python
from dnablocks import Runtime, Registry, Headhunter

# Starts vLLM server with --enable-lora
runtime = Runtime(base_model="mistral-7b-instruct")

# AI Headhunter: find and mint a candidate
hunter = Headhunter(runtime=runtime, dgx=True)

candidates = hunter.search(
    role="senior backend engineer",
    skills=["Python", "distributed systems", "API design"],
    sources=["github"]
)

hunter.mint(
    candidate=candidates[0],
    repos=["github.com/user/project1", "github.com/user/project2"],
    output="backend-expert.dna"
)

runtime.load("backend-expert.dna")

response = runtime.generate(
    "Design a rate-limiting middleware for a FastAPI application",
    expert="backend-expert"
)

runtime.load("frontend-specialist.dna")
response = runtime.generate(
    "Build a React dashboard for monitoring the rate limiter",
    expert="frontend-specialist"
)

registry = Registry(url="https://registry.dnablocks.dev")
results = registry.search("machine learning engineer", quant="INT4")
registry.download("ml-researcher-v2.dna", dest="./team/")
registry.publish("my-expert.dna", tags=["backend", "python", "distributed"])
```

```python
from dnablocks import ProjectAgent

agent = ProjectAgent(
    base_model="mistral-7b-instruct",
    team_dir="./team/",
    registry=Registry()
)

agent.build("""
    Build a real-time chat application with WebSocket support,
    React frontend, and Redis-backed message queue
""")

# Agent flow:
# 1. Load architect.dna — system design
# 2. Load backend-expert.dna — API + WebSocket implementation
# 3. Load frontend-specialist.dna — React UI
# 4. Load devops-engineer.dna — deployment config
```

### 2.7 Data Model

```json
{
    "name": "backend-expert-jane",
    "version": "1.0.0",
    "type": "candidate_dna_block",
    "candidate": {
        "handle": "janedoe",
        "sources": [
            "github.com/janedoe/distributed-cache",
            "github.com/janedoe/fastapi-toolkit",
            "github.com/janedoe/rate-limiter-rs"
        ],
        "expertise_domains": ["backend", "distributed-systems", "API-design", "Python", "Rust"],
        "total_contributions_analyzed": 47823,
        "years_active": 6,
        "consent_verified": true,
        "consent_timestamp": "2026-03-01T09:00:00Z"
    },
    "base_model_hash": "mistral-7b-instruct-v0.3-sha256:a1b2c3...",
    "rank": 64,
    "alpha": 128,
    "quantization": "INT8",
    "file_size_mb": 47,
    "memory_overhead_mb": 94,
    "context_tokens_consumed_by_expertise_layer": 0,
    "vllm_compatible": true,
    "tags": ["backend", "python", "distributed-systems", "API-design"],
    "license": "MIT",
    "created": "2026-03-28T14:00:00Z",
    "eval_summary": {
        "humaneval_score": 0.91,
        "style_consistency": 0.87,
        "domain_accuracy": 0.93,
        "latency_overhead_ms": 12,
        "teacher_model": "llama-3-70b"
    }
}
```

---

## 3. Innovation

### The Precise Claim — and Why It's Stronger for Being Honest

DNA Blocks does not claim to digitize a person's consciousness or replicate human judgment. It claims something more precise and more useful: it encodes a developer's **demonstrated domain working ability** — how they approach problems, the architectural decisions they make, the tradeoffs they've proven they can navigate — into a portable, executable, benchmarked artifact. That ability is trained from their actual public output, not from self-reported summaries.

This is a stronger claim than "AI that thinks like a human" because it is verifiable. Every .dna block ships with benchmark scores. Every hiring team can load a block against their actual codebase and measure the output. The value proposition is falsifiable — which means when it delivers, it delivers credibly.

The reason this hasn't been done before is not a missing insight. It is a missing primitive. There was no standard format for packaging an adapter as a human expertise artifact. No registry for discovering and loading them. No automated pipeline for minting them from public work. No agent layer for routing between them per task. DNA Blocks ships all four.

### The Shift: Resume to Weights

| Capability | Resume | .dna Block | Why It Matters |
|---|---|---|---|
| Where expertise lives | PDF/Word doc | Model weights | Expertise becomes testable, not just readable |
| Verification | Self-reported | Trained on actual public contributions | What they've built, not what they claim |
| Evaluation | Subjective interview | Quantitative benchmarks + live task testing | Data-driven, comparable |
| Try before you hire | Take-home test (4–8 hrs per candidate) | Load the block, run it on your codebase | Zero candidate time, zero interview cost |
| Cost | $20–30K recruiter fee | ~$50–500 to mint | 100x cost reduction on initial evaluation |
| Availability | 8 hrs/day | 24/7, infinite parallelism | Evaluation never blocks on scheduling |
| Reusability | One company, one process | Loadable by anyone, versioned, shareable | Expertise becomes a public benchmark |

### What Makes This New

- The **.dna file** is a new artifact class — a portable, benchmarked, self-describing encoding of a developer's demonstrated patterns. Not a model. Not a resume. Something in between that is more useful than either
- The **Talent Registry** is a new discovery layer — browse developers by actual coding patterns, benchmark scores, and domain depth rather than keyword-matched profiles
- The **AI Headhunter** is a new evaluation pipeline — an autonomous agent that finds candidates, analyzes their work, and produces an executable artifact. No recruiter in the loop
- The **Project Agent** is a new team assembly primitive — load the right expertise for each phase of a project in minutes rather than months
- The **consent-first architecture** is a new trust model — developers opt in, own their block's version history, and can revoke or update at any time

---

## 4. Feasibility

### Proven 24-Hour Execution Record

This team has shipped production-grade ML and hardware systems in under 24 hours repeatedly:

- HackMIT 2025: 1st Place (Cerebras track) — real-time EEG classification with wafer-scale inference built from scratch in one weekend
- HackPrinceton 2025: 4x winner (Capital One, Knot API, Gemini, YC Runner-Up) — edge-computing vision system with custom ResNet and API integration in under 36 hours
- Emergent AI Conference 2025: 1st Place — full AI medical interviewer in 2 hours
- Cornell BigRedHacks 2025: 2nd Overall — real-time AI language game
- Harvard University's HackRare: 1st place for rare diseases Symptoms Management in 24 hours. Custom detection model for Triadin Knockout Syndrome.

### Hybrid Execution Strategy

Heavy training and minting of demo .dna blocks runs on the DGX Spark (70B teacher + adapter training). Runtime, Headhunter agent, Project Assembly, and Registry run locally or on a lightweight instance using pre-exported .dna files and vLLM. This guarantees zero DGX contention risk during final demo polish. The full end-to-end pipeline has been pre-validated on a local DGX Spark replica during the pre-hackathon warm-up window; all three demo .dna blocks are already minted and ready.

### Build Plan

**Phase 1 — Foundation (Hours 0–4)**

- DGX: vLLM + Mistral-7B + LoRA enabled (Youwei) — deliverable: vLLM serving with dynamic adapter loading
- DGX: Load Llama-3-70B teacher in INT8 (~70GB) (Youwei) — deliverable: 70B model running for synthetic data generation
- .dna format spec + dnablocks pack CLI (Sean) — deliverable: packaging tool
- Headhunter agent: GitHub scraper + candidate profiler (Heewon) — deliverable: agent that can analyze a GitHub user's repos and build a profile

**Phase 2 — DNA Factory (Hours 4–9)**

- 70B teacher generates synthetic datasets from 3 real GitHub users' code (Youwei) — deliverable: 3 training datasets
- Train backend-expert.dna rank 64, ~1.5hr (Sean) — deliverable: exported, benchmarked .dna
- Train ml-researcher.dna rank 64, ~1.5hr (Youwei) — deliverable: exported, benchmarked .dna
- Train fullstack-dev.dna rank 32, ~1hr (Sean) — deliverable: exported, benchmarked .dna
- Talent Registry backend: FastAPI + SQLite (Heewon) — deliverable: working browse, search, and download API

**Phase 3 — Headhunter Agent + Project Assembly (Hours 10–18)**

- dnablocks Python wrapper: vLLM API + .dna unpacking (Sean) — deliverable: installable package
- AI Headhunter agent: search → evaluate → recommend (Heewon) — deliverable: agent that finds candidates autonomously
- Project Agent: receives task, selects experts, swaps .dna blocks (Youwei) — deliverable: agent building projects with expert blocks
- Multi-step demo: agent assembles team, builds project (Youwei + Sean) — deliverable: end-to-end demo
- Talent Registry frontend (Heewon) — deliverable: working web UI
- PMF: approach other teams, offer DNA Blocks API (All) — deliverable: external teams using our backend

**Phase 4 — Polish (Hours 18–24)**

- Side-by-side benchmark: generic model vs. .dna-loaded model on identical coding tasks (Sean) — deliverable: quantitative quality comparison
- End-to-end demo recording (All) — deliverable: demo video
- Pitch deck (Heewon) — deliverable: slides
- Final stability testing (Kaden) — deliverable: stable demo

### What We Demo On Stage

1. **"Meet the Headhunter"** — the agent searches GitHub for a backend expert, analyzes their repos, scores their patterns, builds a profile
2. **"Minting DNA"** — the .dna block trains live on DGX using their actual code (or the pre-minted block if time is tight)
3. **"Loading the fingerprint"** — load the .dna block into vLLM, ask a domain-specific technical question, show it responds in the candidate's register with their architectural vocabulary
4. **"Building with DNA"** — the Project Agent receives a task, selects the right .dna blocks, swaps between experts, builds the project phase by phase
5. **"Try before you hire"** — side-by-side: generic model vs. loaded .dna expert on the same coding task. Measurable style and domain consistency difference
6. **"The Registry"** — browse the talent registry, view candidate profiles, benchmark scores, download .dna blocks
7. **"Other teams built on this"** — show other hackathon teams using our API live

### Milestones

- Hour 4: vLLM serving on DGX, 70B teacher loaded, format spec done, GitHub scraper working
- Hour 10: 3 DNA blocks trained and exported, registry live with UI, headhunter finding candidates
- Hour 16: Project agent routing working, other teams onboarded
- Hour 24: Polished demo, benchmarks ready, presentation-ready

---

## 5. Scalability Design

### Inference Scaling

- vLLM's built-in LRU adapter caching — hot experts stay in GPU memory, never touch disk
- Per-request routing — vLLM supports simultaneous different-adapter requests, so multiple users load different experts at the same time
- Context efficiency — expertise signal lives in weights, not context, so the full context window is available for actual task depth

### Registry Scaling

- CDN-backed distribution — .dna files are static artifacts; edge CDN delivers global latency under 100ms
- Semantic search — embeddings over profile.md files for intent-based candidate discovery beyond keyword matching
- Version pinning — compatibility validated against base model hash before download
- Multi-tenant rate limiting and usage-based billing hooks in the registry API — per-organization API keys and credit system in v1

### Horizontal Scaling Path

Multiple vLLM instances behind a load balancer with shared Redis-backed adapter cache. Each instance maintains its own LRU pool; the Redis layer synchronizes which adapters are hot across the fleet.

### The Flywheel

- Company loads backend-expert.dna → uses it for two weeks → rates it 4.8/5 → rating improves registry ranking → more companies discover that developer
- Developer ships more open-source code → .dna block re-trains → v2.0 reflects a more senior engineer than v1.0
- More blocks in registry → more companies search → more signal on what expertise is valued → better headhunter recommendations → more developers opt in

---

## 6. Ecosystem Thinking

### Interoperability

- **Base model agnostic** — .dna works across any model family supported by vLLM's LoRA interface: Llama, Mistral, Qwen, Phi, Gemma, and others
- **Framework agnostic** — .dna is an open spec. The reference runtime uses vLLM, but any inference engine with LoRA adapter support can load the weights
- **OpenAI-compatible API** — vLLM already serves an OpenAI-compatible endpoint. DNA Blocks is a drop-in replacement for any application already calling OpenAI

### API Design

- **REST registry** — GET /experts?domain=backend&skills=python, POST /experts, GET /experts/{id}/download
- **CLI** — dnablocks search, dnablocks mint, dnablocks load, dnablocks push
- **LLM Tool Schema** — registry and headhunter exposed as standard tool-use functions. Any LLM with tool-use can autonomously discover, mint, and load expertise

### Extensibility

- Custom training recipes — domain-specific configs for learning rate, code vs. prose weighting, target layers
- Plugin hooks — pre-load and post-unload for logging, billing, and access control
- Team pipeline YAML — declarative config for team assembly without writing code

---

## 7. Problem Definition

### The Problem

Hiring is the most expensive, slowest, and least reliable process in most organizations. The system runs on unstructured self-reported documents, subjective evaluations, and expensive intermediaries. The strongest signal of a developer's actual capability — their public work — is sitting in the open, completely unused at evaluation time.

There is no way to package a developer's demonstrated patterns into a reusable, evaluatable, loadable artifact. Until now.

### Who Experiences It

**Startups (under 50 people):** Can't afford $25K recruiter fees. Founders spend 30% of time hiring. Bad hires kill companies.

**Engineering managers:** Screening 200 resumes for 1 hire. Interview loops that take weeks. No way to test candidates on actual production work before committing.

**Freelance developers:** Expertise locked in their GitHub but invisible to the market. Competing on price instead of demonstrated quality.

**Open-source contributors:** Massive public track record — libraries with thousands of stars, years of consistent commits — but no mechanism to surface or monetize that expertise beyond consulting.

**Enterprise teams:** Need specific domain expertise for a 3-month project. Can't justify a full-time hire. Contractors are expensive and evaluation is still blind.

---

## 8. Ethical and Legal Framework

This is the section most products in this space skip. We don't.

### The Consent Architecture

DNA Blocks operates on an **opt-in model**. Developers register at registry.dnablocks.dev and explicitly authorize their public repositories for adapter training. This is not a legal technicality — it is the product's trust foundation.

The developer registry provides:

- **Opt-in authorization** — no .dna block is minted without the developer's explicit consent
- **Revocation rights** — developers can revoke their block at any time, triggering removal from the registry and a flag to any organizations currently using it
- **Version control ownership** — developers decide when their block is updated as they ship new work
- **Attribution in every block** — sources.json and consent.json are mandatory fields in the .dna spec. Every hiring team knows exactly whose work trained the adapter

### The Licensing Question

MIT and Apache 2.0 licenses grant broad rights to use, study, modify, and distribute software. Adapter training constitutes transformative use of code — the output is a set of floating-point weights, not a copy or distribution of the original source. This is the prevailing interpretation among AI legal practitioners, though courts have not yet issued a definitive ruling on weights derived from licensed code. We are not claiming this is settled law. We are claiming it is the most defensible current position — and we go beyond what licensing strictly requires by making opt-in developer consent a hard architectural requirement rather than a legal technicality. Every .dna block carries a sources.json and consent.json as mandatory fields. No block is minted without explicit opt-in. This is the architecture that survives the legal landscape evolving in either direction — and it is the posture any enterprise buyer's legal team can approve today.

### What This Is and Isn't

A .dna block is an executable benchmark of a developer's coding patterns. It is not a deepfake. It is not a replacement for the human. It does not speak on their behalf or simulate their personality. It generates code in their stylistic register — the same way a code style guide or a linter captures and enforces patterns, but at a weight level rather than a rule level. The developer who built it is still the person a company should hire. The block tells them whether that hire is worth pursuing.

---

## 9. Market Awareness

### The Recruiting Crisis

- US staffing and recruiting market: $183B+ in 2026 (Staffing Industry Analysts)
- Technical evaluation segment — coding assessments, AI screening, take-home infrastructure: **$1.95B in 2026, projected to reach $4.06B by 2035 at 8.5% CAGR** (Business Research Insights, Pre-Employment Assessment Tools Market Report, March 2026) — this is the layer DNA Blocks directly replaces
- Average cost-per-hire: $4,700 (SHRM) to $25,000+ for technical roles with a recruiter
- Average time-to-hire: 44 days
- 46% of new hires fail within 18 months (Leadership IQ)
- **99% of hiring managers now use AI or automation at some stage of hiring** (iMocha Tech Hiring Trends, 2026) — the market is already moving toward automated evaluation; DNA Blocks is the infrastructure layer underneath it
- The primary hiring challenge in 2026 is not sourcing candidates — it is **verifying that senior engineers actually have the depth they claim** (Keyhole Software, Software Development Statistics 2026, citing Deloitte)
- IT skills shortage projected to cause **$5.5 trillion in global losses** by 2026 (IDC, via TechTarget)

The industry's response has been to automate the wrong things — faster resume screening, auto-scheduled interviews, AI-generated job descriptions. All of that optimizes within a broken loop. DNA Blocks replaces the evaluation step itself with something verifiable.

### Competitive Landscape

**LinkedIn Recruiter:** Searches profiles by keyword. $10K/year. Self-reported data. No way to test. No execution signal.

**Traditional recruiters:** Source and screen candidates. $25K per hire. 44-day cycle. 46% failure rate. Judgment is human and unscalable.

**AI resume screeners:** Filter resumes faster. Still based on self-reported text. No depth signal. Optimizes the wrong thing.

**Take-home projects:** Test candidate skills on artificial problems. 4–8 hours per candidate. Doesn't scale. Doesn't leverage existing public work.

**GitHub Copilot and similar:** Generic AI coding assistant. Not personalized to any specific developer's patterns. No evaluation use case.

**Fine-tuned domain models:** Domain-specific AI that costs hundreds of thousands to train. Not portable. Not tied to a specific person's demonstrated work.

**DNA Blocks:** Evaluates actual public contributions. Executable, benchmarked, portable. Opt-in developer consent. Try-before-you-hire for any codebase.

### Positioning

LinkedIn has profiles. GitHub has code. Nobody has turned public work into a loadable, testable, portable artifact that a hiring team can run against their actual problems before committing to an interview. DNA Blocks is the evaluation layer between "found a promising candidate" and "decided to hire" — the layer where the most money is wasted and the most bad decisions are made.

The Docker analogy is precise: Docker didn't invent containers. It made them usable by packaging them into a standard, portable, self-describing artifact that any system could load without configuration. DNA Blocks does the same for developer expertise.

---

## 10. Team Execution Plan

### The Team

We are the same crew that has won 10+ major hackathons in the last 12 months under identical time pressure.

**Youwei (APMA & CS @ Brown, ML Engineer @ Refine.Dev):** 1st HackMIT Cerebras track, 4x HackPrinceton including YC Runner-Up, 1st Emergent AI, 2nd Cornell BigRedHacks. Repeatedly ships 70B-scale inference pipelines and real-time ML systems in under 24 hours. Owns all DGX Spark training, 70B teacher loading, synthetic data generation, and adapter minting — exactly the pipeline he shipped at HackMIT on Cerebras wafer-scale hardware.

**Sean (ACSL Top 20, USACO Silver):** Owns .dna format spec, packaging CLI, vLLM runtime wrapper, and registry backend. Systems-level thinking applied to the packaging and serving layer.

**Heewon (Applied Math-CS @ Brown, Hack@Brown Co-Director):** Full-stack ML and robotics systems shipped under real pressure. Owns Headhunter agent, Project Agent, and registry frontend.

**Kaden:** Hardware-aware engineering. Stabilized DGX-scale pipelines in prior wins. Owns DGX stability, benchmarking, and final polish.

### Division of Work

- Youwei → all DGX Spark training, 70B teacher, synthetic data, adapter minting
- Sean → .dna format, packaging CLI, vLLM runtime wrapper, registry backend
- Heewon → Headhunter agent, Project Agent, registry frontend
- Kaden → DGX stability, benchmarking, final demo polish
- All → PMF outreach to other teams, demo video, pitch

---

## 11. Risk Assessment

**DGX setup and 70B teacher memory pressure**
Mitigation: vLLM + INT8 quantization fits within 128GB unified memory. Team has run equivalent 70B-scale inference on Cerebras wafer-scale engines at HackMIT. All three demo .dna blocks pre-minted during warm-up window as fallback.

**.dna blocks do not adequately capture style**
Mitigation: We benchmark style consistency explicitly (target: 0.85+ on held-out code from the same developer). The demo includes a quantitative side-by-side. If the delta is smaller than expected, we show it honestly and frame it as v1 — the improvement curve is the pitch, not perfection at launch.

**GitHub scraping rate limits**
Mitigation: Pre-cached repos with authenticated API tokens. Backup candidate repos pre-downloaded before hackathon start.

**IP and licensing of public-work-derived adapters**
Mitigation: Only MIT/Apache-licensed repos, filtered at ingestion. Opt-in consent required before minting. sources.json and consent.json are mandatory fields in the .dna spec. Adapter training constitutes transformative use — output is floating-point weights, not a distribution of source code. Consent-first architecture is the posture any enterprise legal team can approve today, and the one that survives the legal landscape evolving in either direction.

**Ethical concerns about coding style capture**
Mitigation: Consent-first architecture is a hard technical requirement, not a policy note. Revocation rights are live in v1. The block is an executable benchmark, not an identity simulation. This is addressed directly in Section 8.

**Other teams don't adopt the API**
Mitigation: Demo is 100% self-sufficient. PMF outreach is pure upside. We build it anyway.

**Sequential hot-swapping instability**
Mitigation: vLLM dynamic adapter API is production-tested at scale. Team has shipped similar multi-model routing in prior wins.

---

## 12. Differentiation Strategy

### Why This Isn't "Just LoRA With a GitHub Scraper"

LoRA existed. vLLM existed. GitHub existed. The insight is not technical. It is product — and the moat is three layers deep.

**Layer 1: Registry liquidity is the flywheel, and it cannot be cold-started.**

Docker's moat was never the container spec. It was Docker Hub. By the time Docker Hub had millions of images, the switching cost was the ecosystem — no competitor could bootstrap that liquidity from scratch. DNA Blocks wins the same way. The first registry with thousands of opt-in developer blocks, benchmark scores, and usage ratings becomes the default hiring evaluation layer. A fast-follower can copy the format. They cannot copy the network: the developers already opted in, the companies already integrated, the blocks already rated. Registry liquidity compounds. Every new block makes the registry more valuable to every company. Every company integration makes opt-in more valuable to every developer. That flywheel does not exist yet — we are building it first.

**Layer 2: Consent provenance is a structural moat as the legal landscape evolves.**

Any competitor minting LoRA adapters from public code without an explicit consent architecture will face compounding legal and reputational exposure as IP law catches up to AI training. DNA Blocks' consent-first design — mandatory opt-in, revocation rights, sources.json and consent.json as required fields in every block — is the architecture that can operate at scale legally. A fast-follower that scrapes GitHub without consent cannot retrofit this credibly. The trust layer is baked in at the format level, not bolted on as a policy note. For enterprise buyers, this is not a nice-to-have: it is the difference between a tool their legal team will approve and one they won't.

**Layer 3: The compute requirement is a quality gate, not a cost barrier.**

DGX-class hardware is rentable. That's a feature, not a limitation — it means minting scales globally without owned infrastructure. The moat is not hardware access. It is what the hardware requirement filters out. Producing a .dna block worth putting in a hiring registry — one a company will trust to evaluate a $150K hiring decision — requires a 70B teacher pipeline with iterated prompt templates, tuned training configs, and calibrated domain benchmarks. That pipeline takes real investment to build and improve. A competitor can fork the format spec in a weekend. They cannot fork the accumulated minting quality. Every block we train improves our benchmark calibration and teacher prompt design. By the time a fast-follower ships v1, we are on v3 of the pipeline — and the quality delta is visible in the eval scores on every block in the registry. That quality floor is what makes the registry trustworthy as a hiring signal. A flooded registry of low-quality blocks is worthless. A curated registry where every block has a verifiable quality floor is the product. The compute requirement enforces that floor.

The Docker analogy holds precisely because of this structure: Docker didn't win on the spec. It won on Hub liquidity, tooling ecosystem, and enterprise trust — built over time, in that order. DNA Blocks is running the same playbook: open format, proprietary registry, consent moat, compute quality gate.

### Why This Isn't Just Another AI Recruiter

AI recruiters optimize the existing hiring loop — they screen resumes faster, schedule interviews automatically, generate job description templates. All of that is a better horse.

DNA Blocks changes what the evaluation step produces. Instead of a ranked list of candidates you still have to interview, you get an executable artifact you can run on your actual codebase before scheduling a single call. The interview becomes a confirmation of a hypothesis you've already tested, not a blind bet on a 45-minute sample.

---

## 13. User Impact

### Quantitative Impact

| Metric | Traditional Hiring | DNA Blocks |
|---|---|---|
| Time to evaluate a candidate | 2–6 weeks | Minutes |
| Cost per evaluation | $2,000–$5,000 in interview time | ~$0 (block already trained) |
| Cost to surface a candidate | $20–30K recruiter fee | ~$50–500 in DGX compute |
| Risk of bad hire | 46% fail in 18 months | Significantly reduced (tested on actual work before commitment) |
| Expertise availability | 8 hrs/day, one timezone | 24/7, instantly loadable |
| Team assembly time | 3–6 months | Minutes to load a team of .dna blocks for evaluation |

### Hackathon PMF Strategy

Our PMF evidence will not be a theoretical enterprise customer. It will be the other teams at this hackathon.

Deploy the registry first. Approach three or more teams building consumer apps with a specific offer: give us a GitHub username of a developer whose coding style you want to work with. We mint a .dna block from their public work in 30 minutes on the DGX. Your agent codes in their patterns.

We walk on stage saying three other teams in this room built their projects using DNA Blocks. They evaluated expertise they could never have accessed through a traditional hiring process. Real users, real output, real validation — during a hackathon.

---

**The Pitch in One Line**

*"We turned open-source developers into executable, opt-in benchmarks. One model, infinite domain experts, zero token overhead, swapped in milliseconds. Test the expertise before you hire the person."*

---

*CLONE.dna · Hire the Mind. Not the Body.*

---