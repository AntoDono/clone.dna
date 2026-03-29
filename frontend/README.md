# Clone.dna — Frontend

The Clone.dna frontend is a Nuxt 4 / Vue 3 application providing the hiring team's full UI: discovering candidates, cloning their DNA, chatting with clones, running PM orchestration, and browsing the talent registry.

## Stack

- **Nuxt 4** with Vue 3 Composition API
- **Tailwind CSS** for styling
- **Bun** as the package manager and dev server
- Backend API at `http://localhost:8000` (configurable via `NUXT_PUBLIC_API_BASE`)

## Setup

```bash
bun install
bun run dev      # http://localhost:3000
bun run build    # production build
bun run preview  # preview production build locally
```

The backend must be running at `http://localhost:8000` before starting the frontend. See the root [README](../README.md) for full-stack setup.

---

## Pages

| Route | File | Description |
|---|---|---|
| `/` | `pages/index.vue` | Team list — create and browse teams |
| `/registry` | `pages/registry.vue` | Browse, search, and download minted `.dna` blocks |
| `/teams/[id]` | `pages/teams/[id]/index.vue` | Team board — manage role slots, headhunt candidates, trigger DNA cloning |
| `/teams/[id]/build` | `pages/teams/[id]/build.vue` | Build workspace — chat with cloned candidates or run PM orchestration |

### `pages/index.vue`
- Lists all teams with slot fill status (0–4 filled indicator)
- Modal for creating a new team by name
- On creation, redirects to `/teams/{id}?headhunt=true` to auto-open the headhunt overlay

### `pages/registry.vue`
- Fetches all `.dna` blocks from `GET /registry`
- Client-side search filtering by handle, name, skills, and tags (case-insensitive substring)
- Block cards show: handle, role, expertise domains, eval summary scores (style consistency, domain accuracy, loss)
- Click to expand: shows base model, latency overhead, teacher model, full tags list, download link
- Download link: `GET /registry/{team_id}/{handle}/download` — returns the `.dna` block as a `.zip`

### `pages/teams/[id]/index.vue`
- Shows 4 role slot cards (1 PM, 2 SWE, 1 Designer)
- **HeadHuntOverlay** for AI-powered candidate discovery and selection
- **CloneDnaOverlay** for streaming the live DNA minting pipeline
- `dnaComplete` computed: true if at least one candidate has `dna_cloned = true`
- "Go to Build" button appears when cloning is complete

### `pages/teams/[id]/build.vue`
- Left sidebar: lists all cloned candidates with role badges
- Main panel: **ChatPanel** for direct DM or orchestration
- Loads full message history for all threads on mount
- Defaults to the first cloned candidate as the active thread

---

## Components

### `components/TeamCard.vue`
- Props: `team` (Team object)
- Displays team name, creation date, slot fill badges
- Links to `/teams/{id}`

### `components/RoleSlot.vue`
- Props: `slot` (RoleSlot), `meta` (label/badge/desc), `isActive`, `isScanning`, `teamId`
- Emits: `scan`, `remove`, `extracted`, `error`
- **Filled state:** candidate avatar, name, description, skill badges, remove button
- **Empty state:** three input methods:
  1. "Scan GitHub" — emits `scan` to trigger headhunt overlay
  2. "Website URL" — inline URL input, calls `POST .../extract-website`
  3. "Paste Resume" — inline textarea, calls `POST .../extract-resume`
- Badge colors: PM (amber), SWE (blue), Designer (purple)

### `components/HeadHuntOverlay.vue`
- Props: `teamId`, `slots[]`
- Emits: `done`
- Three phases: `hunting` → `selecting` → `confirming`
- **Hunting:** Streams `GET /teams/{teamId}/headhunt/stream` (SSE), shows skeleton loaders per column, fetches 5 candidates per role (PM / SWE / Designer) in parallel
- **Selecting:** Click to select candidates (1 PM, 2 SWE, 1 Designer max); selected cards highlighted with checkmark; refetch clears cache
- **Confirming:** POSTs 4 `select` calls to assign candidates; spinner overlay during save

### `components/CloneDnaOverlay.vue`
- Props: `teamId`, `slots[]`, `emergencyCalibration` (bool)
- Emits: `done`
- Connects to `GET /teams/{teamId}/clone-dna/stream` (SSE); appends `?emergency_calibration=1` when enabled
- Per-candidate state machine: `waiting` → `collecting` → `generating` → `training` → `saving` → `done` / `error` / `skipped`
- Shows: phase label, progress bar (step/totalSteps), live loss and best-loss values, pair count, output path
- Footer: count of done / failed / skipped candidates
- 90s heartbeat timeout before showing a stale-stream warning

### `components/CandidateSearch.vue`
- Props: `candidates[]`, `teamId`, `slotId`
- Emits: `selected`
- Collapsible list; clicking a candidate expands their full profile
- "Select Candidate" button emits `selected` with the candidate data

### `components/ProfilingTree.vue`
- Props: `candidate`, `expanded` (bool)
- **Collapsed:** name, avatar, handle, location, follower count, 2 top skills
- **Expanded:** role-fit description, bio, soft skill badges (amber), technical skill badges (blue), top 4 repos with star counts and links, language bar charts with percentages

### `components/build/ChatPanel.vue`
- Props: `teamId`, `thread` (handle or `"orchestrate"`), `messages[]`, `streaming`, `streamingHandle`, `isThinking`
- Emits: `send`, `stop`
- Renders messages with avatars and role badges
- Message content is parsed for `[[TOOL_CALL:...]]` and `[[TOOL_RESULT:...]]` markers and rendered as formatted blocks with icons
- Text segments are rendered as markdown via `marked`
- Blinking cursor shown on the last token of a streaming message
- Textarea input: Enter sends, Shift+Enter inserts newline
- "Stop" button cancels the in-flight SSE stream via `AbortController`

---

## Composables

### `useApi.ts`

Typed API client for all REST endpoints.

```typescript
const api = useApi()

// Teams
await api.getTeams()
await api.createTeam(name)
await api.getTeam(id)
await api.deleteTeam(id)

// Candidates
await api.searchCandidates(teamId, slotId, query)
await api.selectCandidate(teamId, slotId, githubHandle)
await api.extractFromWebsite(teamId, slotId, url)
await api.extractFromResume(teamId, slotId, text)
await api.removeCandidate(teamId, slotId)
await api.clearHeadhuntCache(teamId)

// Build
await api.getBuildMessages(teamId)
```

### `useTeamChat.ts`

SSE streaming state management for direct messages and PM orchestration.

**State:**
- `activeThread` — current handle or `"orchestrate"`
- `threads` — `Record<string, ChatMessage[]>` — message history per thread
- `streaming` — whether a stream is active
- `streamingHandle` — which handle is currently generating
- `isThinking` — whether a `<think>` block is being suppressed

**Key methods:**

`setThread(handle)` — switch the active chat thread and scroll to bottom

`loadHistory(teamId)` — fetch full message history from `GET /teams/{teamId}/build/messages`, populate all threads

`sendMessage(teamId, text)` — routes to `sendDm` or `sendOrchestrate` depending on `activeThread`

**SSE event types consumed:**

| Event | Payload | Effect |
|---|---|---|
| `token` | `{token: string, handle: string}` | Appends to current assistant message |
| `thinking` | `{on: boolean}` | Toggles `isThinking` indicator |
| `tool_call` | `{name: string, arguments: object}` | Appends `[[TOOL_CALL:...]]` marker to message |
| `tool_result` | `{name: string, output: string, success: boolean}` | Appends `[[TOOL_RESULT:...]]` marker |
| `done` | `{}` | Marks stream complete |
| `speaker` | `{handle: string}` | (Orchestration) switches active speaker, creates new message bubble |

Stream cancellation: `sendDm` and `sendOrchestrate` create an `AbortController`; calling `stopStreaming()` aborts the fetch, closing the SSE connection.

---

## Emergency Calibration

A global debug mode for demos without a GPU.

**Toggle:** Press `Shift` anywhere in the app — an orange dot appears in the top-right corner when active.

**Effect:** When `CloneDnaOverlay` is opened with emergency calibration active, it appends `?emergency_calibration=1` to the clone-dna stream URL. The backend returns a realistic simulated training stream (randomized loss curves and phase delays) without running real training. The UI is indistinguishable from a real run.

---

## Environment

```ts
// nuxt.config.ts
runtimeConfig: {
  public: {
    apiBase: 'http://localhost:8000'
  }
}
```

Override at build or runtime:

```bash
NUXT_PUBLIC_API_BASE=https://your-backend.example.com bun run build
```
