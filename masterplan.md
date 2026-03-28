# CLONE.dna

Hire the Mind. Not the Body.

yconic New England Inter-Collegiate AI Hackathon — March 28–29, 2026 · Providence, RI Track: NVIDIA Supercomputer Hack (DGX Spark + $3,000)

1. Vision Clarity

North Star: The candidate is the dataset. The expertise is the adapter. The .dna file is the new hire.

Hiring is broken in the same way AI specialization is broken — it's expensive, slow, and locked behind gatekeepers. Companies spend $20,000–$30,000 per hire through recruiters. They wait 45–90 days to fill a role. They interview 10 people to find 1. And after all of that, 46% of new hires fail within 18 months.

Meanwhile, the best developers, designers, and domain experts in the world have their expertise scattered across GitHub repos, open-source contributions, blog posts, research papers, and project histories. That expertise is locked inside a human body that can only work 8 hours a day, at one company, in one timezone.

DNA Blocks ends the bottleneck of human bandwidth.

Think about how hiring works today versus how it should work:

* Today: You post a job → wait weeks → screen 200 resumes → interview 10 people → hire 1 → pray they're good → pay $150K+/year.

* DNA Blocks: You search for expertise → find the right person → train a .dna block on their public work → load it into your project → get their coding style, domain knowledge, and problem-solving patterns on demand. Then decide if you want to hire the actual human.

The model is the platform. The person's expertise is the skill. The .dna file is the new primitive.

A .dna file is a LoRA adapter trained on a person's open-source contributions, writing, code style, and domain output. It captures how they think, how they solve problems, and what they know — packaged as a portable, swappable, reusable block of human expertise.

* The base model is the brain — a general-purpose reasoning engine.

* A .dna file is the expertise — a specific person's knowledge and style, encoded as adapter weights.

* The Talent Registry is the marketplace — browse candidates, preview their .dna blocks, load them into your stack.

One lightweight base model. A library of human expertise blocks. Try before you buy. Or just buy the block.

The recruiter didn't make hiring faster. DNA Blocks makes recruiters obsolete.

2. Technical Depth

2.1 The .dna File Format

A .dna (DNA Block) file is a self-contained package of human expertise — not a full model, not a resume. It's a tensor-level encoding of a person's skills, style, and domain knowledge that integrates with a base model at the weight level, activating that person's expertise without retraining and without consuming a single token of context.

Anatomy of a .dna file:

Component Description manifest.json Metadata: candidate name/handle, expertise domains, base model compatibility hash, version, training source (GitHub repos, papers, etc.), benchmark scores, file size, quantization level profile.md Human-readable candidate profile — who this person is, what they're known for, what the block is optimized for. Used by the agent router for expertise selection and by recruiters for candidate discovery. Read once by the router — NOT injected into context weights/ The adapter weights in safetensors format (adapter_config.json + adapter_model.safetensors) — compatible with vLLM's LoRA loading interface config.yaml Integration config: target layer indices, quantization format (INT4/INT8/FP16), rank, alpha scaling factor, memory footprint estimate eval.json Benchmark results: coding benchmarks (HumanEval, MBPP), domain-specific evals, style consistency metrics, so companies know exactly what they're getting before loading sources.json Provenance: links to all public repos, papers, and contributions used for training data. Full transparency on what the block learned from

Key properties:

* Portable — a .dna file works on any compatible base model (compatibility verified via model hash in manifest). Train once, deploy anywhere.

* Quantizable — compress DNA blocks to INT4/INT8 for edge deployment. A 50MB .dna file instead of a $150K/year salary.

* Versionable — expertise evolves. Update senior-backend-eng-v3.dna as the person ships more work, without touching the base model or any other block.

* Hot-swappable — swap expertise at inference time in milliseconds via vLLM's dynamic adapter API. Need a frontend expert for this task and a backend expert for the next? Swap in milliseconds. No restart. No redeployment.

* Composable — build a dream team by sequentially loading different .dna blocks for different parts of a project. Load the architect for system design → swap to the implementer for code → swap to the technical writer for docs.

2.2 The AI Headhunter: How It Works

The AI Headhunter is the autonomous agent layer that sits on top of DNA Blocks. It handles the entire hiring pipeline:

```

┌─────────────────────────────────────────────────────────────────┐

│                     AI HEADHUNTER AGENT                         │

│                                                                 │

│  1. SEARCH ──► 2. EVALUATE ──► 3. MINT ──► 4. BUILD            │

│                                                                 │

│  ┌──────────────┐ ┌──────────────┐ ┌────────────┐ ┌──────────┐ │

│  │ Candidate    │ │ Profile      │ │ .dna Block │ │ Project  │ │

│  │ Discovery    │ │ Builder      │ │ Factory    │ │ Assembly │ │

│  │              │ │              │ │ (DGX Spark)│ │          │ │

│  │ Search GitHub│ │ Analyze repos│ │ 70B teacher│ │ Load .dna│ │

│  │ Find experts │ │ Score skills │ │ Synth data │ │ blocks   │ │

│  │ Match to role│ │ Build profile│ │ Train LoRA │ │ Execute  │ │

│  │              │ │              │ │ Package    │ │ tasks    │ │

│  └──────────────┘ └──────────────┘ └────────────┘ └──────────┘ │

│                                                                 │

└─────────────────────────────────────────────────────────────────┘

```

Step 1: Candidate Discovery The headhunter agent takes a project description or role requirement. It searches GitHub, analyzes open-source contributions, identifies developers whose work matches the need. Not keyword matching — semantic understanding of code quality, architectural patterns, and domain depth.

Step 2: Profile Building For each candidate, the agent builds a structured profile: languages, frameworks, coding patterns, documentation style, problem-solving approach, domain expertise. This becomes the profile.md in the .dna file.

Step 3: .dna Block Minting (on DGX Spark) The 70B teacher model on the DGX generates high-quality synthetic training data from the candidate's public work — instruction-response pairs that capture their coding style, domain reasoning, and problem-solving patterns. The student adapter is trained on this data. The result is a .dna block that thinks like them.

Step 4: Project Assembly The user describes their project. The agent selects the right .dna blocks, loads them sequentially via vLLM, and builds the project using each expert's strengths. System design with the architect's block. Implementation with the coder's block. Testing with the QA expert's block.

2.3 Runtime Layer: Built on vLLM

We are not writing custom PyTorch weight-injection hooks from scratch. The DNA Blocks runtime is built on top of vLLM's multi-LoRA serving infrastructure, which already provides:

* Dynamic adapter loading/unloading via REST API (POST /v1/load_lora_adapter, DELETE /v1/unload_lora_adapter)

* Per-request adapter selection — each inference call can specify which adapter to use via the model parameter, enabling true per-request expertise routing

* LRU caching — vLLM maintains an LRU cache (max_cpu_loras) so frequently used DNA blocks stay in memory

* OpenAI-compatible API — any application that calls OpenAI's API can use the DNA Blocks endpoint as a drop-in replacement

* Efficient VRAM management — vLLM handles memory allocation, KV-cache management, and concurrent adapter serving

What DNA Blocks adds on top of vLLM:

1. The .dna packaging format — standardized, self-describing expertise packages with manifest, candidate profile, benchmarks, and source provenance. vLLM expects loose adapter files; DNA Blocks wraps them into a human-expertise artifact.

2. The Talent Registry — a searchable marketplace where .dna files are published, discovered, and loaded. Browse candidates by skill, domain, coding style.

3. The AI Headhunter agent — an autonomous agent that discovers candidates, evaluates their work, and mints .dna blocks. The hiring pipeline is fully automated.

4. Agent-native project routing — an LLM tool schema that lets the project agent autonomously select which .dna to load for each task. The right expert for each step.

5. The training pipeline — automated public-work collection → synthetic data generation → training → quantization → packaging → publishing on DGX Spark.

2.4 Runtime Flow

1. Project Analysis — the agent analyzes the incoming project/task, extracts requirements, identifies what expertise is needed.

2. Expertise Selection — the agent calls the select_expert tool (standard LLM tool-use), which queries the registry and matches requirements to available .dna files using profiles and eval scores.

3. Dynamic Loading — the runtime calls vLLM's /v1/load_lora_adapter endpoint with the selected .dna adapter path.

4. Inference — the request is sent to vLLM with "model": "expert-name" to route to the loaded adapter. The entire context window is free for the actual project work.

5. Swap — for the next task phase, a different .dna is loaded. The architect hands off to the implementer. Clean, stable, no weight collision.

2.5 Training Pipeline (on DGX Spark)

The DGX Spark is the mint — the .dna factory.

```

┌──────────────────┐  ┌─────────────────┐  ┌──────────────┐  ┌────────────┐

│  Candidate's     │  │ 70B+ Teacher    │  │ Targeted     │  │ Package +  │

│  Public Work     │─►│ Model on DGX    │─►│ Training     │─►│ Export .dna│

│                  │  │                 │  │              │  │            │

│  GitHub repos    │  │ Generates synth │  │ Freeze base, │  │ Quantize,  │

│  Blog posts      │  │ data capturing  │  │ train adapter│  │ benchmark, │

│  Papers          │  │ style + domain  │  │ on synthetic │  │ publish to │

│  Open source     │  │ expertise       │  │ data         │  │ registry   │

│                  │  │                 │  │              │  │            │

│                  │  │ REQUIRES 128GB  │  │              │  │            │

│                  │  │ unified memory  │  │              │  │            │

└──────────────────┘  └─────────────────┘  └──────────────┘  └────────────┘

```

Why DGX is non-negotiable for the training pipeline:

The core of the .dna factory is a 70B+ parameter teacher model (Llama-3-70B or equivalent) that reads a candidate's public work and generates high-quality synthetic training data that captures their expertise patterns. This teacher model requires 140GB in FP16 (70GB quantized INT8) — it physically cannot run on a consumer GPU, a MacBook Pro, or a standard cloud instance. The DGX Spark's 128GB unified memory is the minimum hardware.

The teacher model:

* Reads a candidate's GitHub repos, PRs, code reviews, blog posts

* Generates instruction-response pairs that capture their coding style and domain reasoning

* Creates chain-of-thought examples that mirror their problem-solving approach

* Evaluates quality of the student model's outputs against the candidate's actual style

* Runs in parallel with the student training loop for real-time data quality feedback

2.6 API Design

```python

# Core Runtime API (wraps vLLM)

from dnablocks import Runtime, Registry, Headhunter

# Starts vLLM server with --enable-lora under the hood

runtime = Runtime(base_model="mistral-7b-instruct")

# AI Headhunter: find and mint a candidate

hunter = Headhunter(runtime=runtime, dgx=True)

# Search for a backend expert

candidates = hunter.search(

    role="senior backend engineer",

    skills=["Python", "distributed systems", "API design"],

    sources=["github"]

)

# Mint a .dna block from their public work

hunter.mint(

    candidate=candidates[0],

    repos=["github.com/user/project1", "github.com/user/project2"],

    output="backend-expert.dna"

)

# Load the expertise — zero context tokens consumed

runtime.load("backend-expert.dna")

# Inference — this response reflects the candidate's style and knowledge

response = runtime.generate(

    "Design a rate-limiting middleware for a FastAPI application",

    expert="backend-expert"

)

# Swap to another expert for a different task

runtime.load("frontend-specialist.dna")

response = runtime.generate(

    "Build a React dashboard for monitoring the rate limiter",

    expert="frontend-specialist"

)

# Registry: browse and share DNA blocks

registry = Registry(url="https://registry.dnablocks.dev")

results = registry.search("machine learning engineer", quant="INT4")

registry.download("ml-researcher-v2.dna", dest="./team/")

registry.publish("my-expert.dna", tags=["backend", "python", "distributed"])

```

```python

# Project Assembly: agent auto-selects experts per task phase

from dnablocks import ProjectAgent

agent = ProjectAgent(

    base_model="mistral-7b-instruct",

    team_dir="./team/",  # directory of .dna files

    registry=Registry()

)

# Agent auto-selects and sequentially swaps experts based on task phase

agent.build("Build a real-time chat application with WebSocket support, 

             React frontend, and Redis-backed message queue")

# Agent flow:

# 1. Load architect.dna → system design

# 2. Load backend-expert.dna → API + WebSocket implementation

# 3. Load frontend-specialist.dna → React UI

# 4. Load devops-engineer.dna → deployment config

```

2.7 Data Model

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

        "years_active": 6

    },

    "base_model_hash": "mistral-7b-instruct-v0.3-sha256:a1b2c3...",

    "rank": 64,

    "alpha": 128,

    "quantization": "INT8",

    "file_size_mb": 47,

    "memory_overhead_mb": 94,

    "context_tokens_consumed": 0,

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

3. Innovation

The Hiring Problem Nobody Is Solving

Every company today is optimizing inside the same broken loop: post job → screen resumes → interview → hire → hope. Recruiters charge $20K–$30K per placement. The average time-to-hire is 44 days. 46% of hires fail within 18 months. And the entire process is based on self-reported, unstructured text documents — resumes.

Meanwhile, the best signal about a developer's ability is sitting in plain sight: their public work. GitHub contributions, open-source projects, technical blog posts, research papers. This work is structured, verifiable, and demonstrates actual capability — not claimed capability.

DNA Blocks doesn't optimize hiring. It replaces it.

The Shift: Resume → Weights

Capability Resume (Document Layer) .dna (Weight Layer) Why It Matters Where expertise lives PDF/Word doc Model weights (parameters) Expertise becomes executable, not just readable Verification Self-reported, unverifiable Trained on actual public work What they've built, not what they claim Evaluation Subjective interview Quantitative benchmarks (HumanEval, domain evals) Data-driven hiring decisions Try before you buy Maybe a take-home project Load the .dna, test it on your actual codebase Zero-risk evaluation Cost $20K–$30K recruiter fee + $150K+ salary ~$50–500 to mint a .dna block 100x cost reduction for initial evaluation Availability 8 hours/day, 1 timezone 24/7, infinite parallelism The expertise never sleeps Reusability One company at a time Loadable by anyone, shareable, versioned Expertise becomes a public good Team assembly Months of hiring Minutes of loading .dna blocks Build your dream team in an afternoon

Everything a resume can tell you, a .dna file can show you — by actually performing the work.

And everything a .dna file can do, a resume fundamentally cannot: execute code in the candidate's style, answer technical questions with their domain knowledge, demonstrate their architectural thinking on your actual problems, and let you swap between experts in milliseconds.

What Makes This New

* The .dna file is the new hire — a portable, benchmarked encoding of human expertise.

* The Talent Registry is the new recruiting platform — browse, evaluate, and load experts instead of reading resumes.

* The AI Headhunter is the new recruiter — an autonomous agent that finds talent, evaluates their work, and mints .dna blocks.

* The Project Agent assembling a team of .dna blocks is the new CTO — it picks the right expert for each phase and builds your project.

This is the shift from hiring people to loading expertise — talent that exists independently of any single human's availability, traded and shared like packages on npm.

The Economics

* Average recruiter fee: $20,000–$30,000 per hire

* Average time-to-hire: 44 days

* Average cost of a bad hire: $17,000 (SHRM)

* Total US recruiting market: $150B+/year

DNA Blocks:

* Cost to mint a .dna block: ~$50–500 in DGX compute time

* Time to mint: 1–3 hours

* Cost to load and evaluate: $0 (already trained)

* Risk of bad hire: Near-zero (you tested the block on your actual work first)

4. Feasibility

Hybrid Execution Strategy (API + Local)

To guarantee 24-hour delivery we're using a hybrid approach:

* Training of demo DNA blocks happens on the DGX Spark (70B teacher model + adapter training). This is where the DGX earns its keep.

* The runtime demo, headhunter agent, and project assembly run locally or on a lightweight instance using the exported .dna files and vLLM.

This eliminates any risk of DGX contention during final polishing while still proving the full end-to-end pipeline that only the NVIDIA Supercomputer track enables.

Build Plan

Phase 1: Foundation — Hours 0–4

Task Owner Deliverable DGX: vLLM + Mistral-7B + LoRA enabled Youwei vLLM serving with dynamic adapter loading DGX: Load Llama-3-70B teacher (INT8, ~70GB) Youwei 70B model running for synth data .dna format spec + dnablocks pack CLI Sean Packaging tool Headhunter agent: GitHub scraper + candidate profiler Engineering Lead Can analyze a GitHub user's repos

Phase 2: DNA Factory — Hours 4–10

Task Owner Deliverable 70B teacher → synthetic datasets from real GitHub users' code Youwei 3 datasets from 3 different developers Train backend-expert.dna (rank 64, ~1.5hr) Sean Exported + benchmarked .dna Train ml-researcher.dna (rank 64, ~1.5hr) Youwei Exported + benchmarked .dna Train fullstack-dev.dna (rank 32, ~1hr) Sean Exported + benchmarked .dna Talent Registry backend (FastAPI + SQLite) Engineering Lead Working browse/search/download API

Phase 3: Headhunter Agent + Project Assembly — Hours 10–18

Task Owner Deliverable dnablocks Python wrapper (vLLM API + .dna unpacking) Sean Installable package AI Headhunter agent: search → evaluate → recommend Engineering Lead Agent that finds candidates autonomously Project Agent: receives task, selects experts, swaps .dna blocks Youwei Agent building projects with expert blocks Multi-step demo: agent assembles team, builds project Youwei + Sean End-to-end demo Talent Registry frontend Engineering Lead Working web UI PMF: approach other teams, offer DNA Blocks API All External teams using our backend

Phase 4: Polish — Hours 18–24

Task Owner Deliverable Side-by-side benchmark: generic model vs .dna-loaded model on coding tasks Sean Quantitative quality comparison End-to-end demo recording All Demo video Pitch deck Engineering Lead Slides Final testing All Stable demo

What we demo on stage:

1. "Meet the Headhunter" — show the agent searching GitHub for a backend expert, analyzing their repos, scoring their skills

2. "Minting DNA" — show the .dna block being trained live on DGX using their actual code (or show the one we trained earlier)

3. "Loading expertise" — load the .dna block into vLLM, ask it a technical question, show it responds with the candidate's style and depth

4. "Building with DNA" — the Project Agent receives a task, selects the right .dna blocks, swaps between experts, builds the project

5. "Try before you buy" — side-by-side: generic model vs. loaded .dna expert on the same coding task. Show the quality difference

6. "The Registry" — browse the talent registry, view candidate profiles, download .dna blocks

7. Other hackathon teams using our API as their backend (PMF evidence)

Milestones

* Hour 4: vLLM serving on DGX, 70B teacher loaded, format spec done, GitHub scraper working

* Hour 10: 3 DNA blocks trained + exported, registry live with UI, headhunter finding candidates

* Hour 16: Project agent routing working, other teams onboarded

* Hour 24: Polished demo, benchmarks, PMF evidence, presentation-ready

5. Scalability Design

Inference Scaling

* vLLM's built-in LRU adapter caching — frequently loaded .dna adapters stay in GPU memory. Hot experts never touch disk.

* Per-request routing — vLLM supports per-request adapter selection, so different users can use different experts simultaneously.

* Context window efficiency — zero context tokens consumed means the model handles longer tasks, deeper reasoning, and more complex projects without hitting limits.

Registry Scaling

* CDN-backed distribution — .dna files are static artifacts. Edge CDN, global latency under 100ms.

* Semantic search — embeddings over profile.md files for intent-based candidate discovery.

* Version pinning — compatibility validated before download.

The Flywheel

Every hire outcome improves the system:

* Company loads backend-expert.dna → uses it for 2 weeks → rates it 4.8/5 → rating improves registry ranking

* Candidate ships more open-source code → .dna block gets re-trained → v2.0 is better than v1.0

* More .dna blocks in registry → more companies search → more data on what expertise is valued → better headhunter recommendations

6. Ecosystem Thinking

Interoperability

* Base model agnostic — .dna works across any model family supported by vLLM's LoRA interface (Llama, Mistral, Qwen, Phi, Gemma, etc.).

* Framework agnostic — .dna is an open spec. Reference runtime uses vLLM, but any engine with adapter support can load the weights.

* OpenAI-compatible API — vLLM already serves an OpenAI-compatible endpoint. Drop-in replacement.

API Design

* REST registry — GET /experts?domain=backend&skills=python, POST /experts, GET /experts/{id}/download.

* CLI — dnablocks search, dnablocks mint, dnablocks load, dnablocks push.

* LLM Tool Schema — registry + headhunter as standard tools. Any LLM with tool-use can autonomously discover, mint, and load expertise.

Extensibility

* Custom training recipes — domain-specific configs for learning rate, code vs. prose weighting, target layers.

* Plugin hooks — pre-load/post-unload for logging, billing, access control.

* Team pipeline YAML — declarative config for team assembly without code.

7. Problem Definition

The Problem

Hiring is the most expensive, slowest, and least reliable process in every organization. The entire system runs on unstructured self-reported documents (resumes), subjective evaluations (interviews), and expensive intermediaries (recruiters). Meanwhile, the strongest signal of a person's actual capability — their public work — is sitting in the open, unstructured and unused at scale.

There is no way to package a person's demonstrated expertise into a reusable, evaluatable, loadable artifact — until now.

Who Experiences It

Persona Pain Point Startups (< 50 people) Can't afford $25K recruiter fees. Founders spend 30% of time hiring. Bad hires kill companies Engineering managers Screening 200 resumes for 1 hire. Interview loops that take weeks. No way to test candidates on actual work Freelance developers Expertise locked in their GitHub but invisible to the market. Competing on price instead of quality Open-source contributors Massive public track record but no way to monetize expertise beyond consulting Enterprise teams Need domain expertise for a 3-month project. Can't justify a full-time hire. Contractors are expensive and unreliable

8. User Impact

Quantitative Impact

Metric Current (Traditional Hiring) With DNA Blocks Time to evaluate a candidate 2–6 weeks (interviews) Minutes (load .dna, test) Cost per evaluation $2,000–$5,000 (interview time) ~$0 (block already trained) Cost to mint expertise $20K–$30K (recruiter) ~$50–500 (DGX compute) Risk of bad hire 46% fail in 18 months Near-zero (tested on actual work) Expertise availability 8 hrs/day, 1 timezone 24/7, instant Team assembly time 3–6 months Minutes

Hackathon PMF Strategy

Our PMF evidence won't be a theoretical enterprise customer. Our PMF will be the other teams at this hackathon.

Build the API and deploy the registry first. Go to 3+ other teams building consumer apps: "Give us a GitHub username of someone whose coding style you admire — we'll mint a .dna block of their expertise in 30 minutes on the DGX, and your agent codes with their patterns."

Walk on stage saying "Three other teams in this room are building their projects on DNA Blocks. They're coding with the expertise of engineers they've never met." Real users, real traction, real validation — during a hackathon.

9. Market Awareness

The Recruiting Crisis

* US recruiting market: $150B+/year

* Average cost-per-hire: $4,700 (SHRM) to $25,000+ (technical roles with recruiter)

* Average time-to-hire: 44 days

* 46% of new hires fail within 18 months

* 73% of employers report difficulty finding skilled candidates

The industry's solution is more tools for the same broken process — better ATS systems, AI resume screening, automated interview scheduling. All of these optimize within the hiring loop. DNA Blocks replaces the loop entirely.

Competitive Landscape

Solution What It Does What It Lacks LinkedIn Recruiter Search profiles by keywords $10K/year. Self-reported data. No way to test Traditional recruiters Source and screen candidates $25K per hire. 44-day cycle. 46% failure rate AI resume screeners Filter resumes by keywords Still based on self-reported text. No depth Take-home projects Test candidate skills Takes 4–8 hours per candidate. Doesn't scale GitHub Copilot AI code assistant Generic. No specific human expertise Fine-tuned models Domain-specific AI Expensive to train. Not portable. Not a person's expertise

Positioning

LinkedIn has profiles. GitHub has code. Nobody has turned public work into a loadable, testable, portable artifact of human expertise. DNA Blocks is the layer that connects demonstrated capability to instant evaluation — the same way Docker connected infrastructure to instant deployment.

10. Team Execution Plan

The Team

Youwei Zhen — APMA & CS @ Brown University. ML Engineer @ Refine.Dev. 1st Place HackMIT (built real-time EEG classification model from scratch + Cerebras inference for AI music therapy). 2nd Place Overall Cornell BigRedHacks. 4x Winner HackPrinceton (1st Capital One, 1st Knot API, YC Runner-Up, Best Google Gemini). 1st Place Emergent AI Conference (built AI medical interviewer in 2 hours). USACO Plat. Ships end-to-end ML systems under pressure.

Sean — ACSL Top 20 nationally, USACO Silver. Deep algorithmic foundation and systems-level thinking. Fast, precise implementation under time pressure.

Kaden — Flown out to London for a chemical industry hackathon. Ships in technical, domain-specific environments under international-stage pressure. Hardware-aware engineering critical for DGX optimization.

Heewon - Applied Math-CS & Computational Neuroscience @ Brown University. Co-Director of Hack@Brown. Researcher @ Serre Lab and Brown Intelligent Robot Lab. Software Engineer @ Brown Data Science Institute. Former SWE Intern @ SimCare AI (YC S24). 1st Place Harvard HackRare 2026 (built continuous cardiac monitoring platform with on-device CNN arrhythmia classifier). Jihoon Rim Foundation Scholar. Ships full-stack systems under pressure across ML, robotics, and healthcare domains.

11. Risk Assessment

Risk Mitigation DGX setup time vLLM is pip install + one CLI command. Team has shipped on Cerebras (HackMIT), GPUs at Princeton/Cornell 70B teacher doesn't fit Using INT8 quantized (~70GB), fits comfortably in 128GB unified memory .dna blocks show no style difference from base model Use high-signal domains (code style is highly distinctive). Compare outputs side-by-side with the candidate's actual code GitHub scraping rate limits Pre-cache target repos. Use GitHub API with auth tokens. Have backup candidates pre-downloaded Ethical concerns about "cloning" people We only use public, open-source work. The .dna block captures expertise patterns, not personal identity. Think of it as a very good code-completion model, not a deepfake Other teams don't adopt API Demo is self-sufficient without it. PMF play is upside, not dependency Composability questions Sequential hot-swapping is stable and proven on vLLM. Simultaneous stacking is clearly scoped as future research

This team has won HackMIT, placed at Cornell and Princeton, shipped at international hackathons, and ranks nationally in competitive programming. Execution risk is low.

12. Differentiation Strategy

Why This Isn't "Just LoRA With a GitHub Scraper"

LoRA existed. vLLM existed. GitHub existed.

Docker didn't invent containers — it made them usable.

DNA Blocks doesn't invent adapters — it makes them usable as a hiring and expertise layer for real teams.

We are not shipping another training script. We are shipping the missing layer that turns isolated adapter files into a living marketplace of human expertise. The differentiation is in the product, not the underlying math:

1. AI Headhunter — an autonomous agent that discovers, evaluates, and recommends candidates by analyzing their actual work. Not keyword matching. Not resume screening. Code analysis.

2. Zero-context expertise loading — a person's knowledge no longer competes with the task for the model's working memory. Full context window for the actual project.

3. Try-before-you-buy hiring — load a candidate's .dna block, test it on your actual codebase, evaluate quality before committing to a hire. Zero-risk.

4. Portable expertise primitive — .dna files are self-describing, benchmarked, versioned, and base-model compatible. A person's expertise becomes portable and reusable.

5. Talent Registry — discovery + download + load is one tool call. The npm for human expertise.

6. DGX-powered minting — high-quality DNA blocks are minted on-demand using 70B teacher models that consumer hardware can't run.

Why This Isn't Just Another AI Recruiter

AI recruiters optimize the existing hiring loop — they screen resumes faster, schedule interviews automatically, generate JD templates.

DNA Blocks replaces the loop entirely. You don't screen a resume — you load their expertise and test it. You don't interview — you let their .dna block work on your actual problems. You don't hope the hire works out — you already know, because you've been using their block for a week.

This is the difference between "faster horses" and the automobile.

The Pitch In One Line

"We turned open-source developers into downloadable AI expertise. One model, infinite experts, zero token overhead, swapped in milliseconds. Try before you hire."

_CLONE.dna · Hire the Mind. Not the Body._