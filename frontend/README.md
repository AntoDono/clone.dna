# Clone.dna — Frontend

The Clone.dna frontend is a Nuxt 3 / Vue 3 application that provides the hiring team's UI for discovering candidates, cloning their DNA, and interacting with the resulting AI clones.

## Stack

- **Nuxt 3** with Vue 3 Composition API
- **Tailwind CSS** for styling
- **Bun** as the package manager and dev server
- Backend: FastAPI at `http://localhost:8000` (configured in `nuxt.config.ts`)

## Setup

```bash
bun install
bun run dev      # http://localhost:3000
bun run build    # production build
bun run preview  # preview production build locally
```

Ensure the backend is running at `http://localhost:8000` before starting the frontend. See the root [README](../README.md) for full-stack setup instructions.

## Pages

| Route | Description |
|---|---|
| `/` | Team list — create and browse teams |
| `/teams/[id]` | Team board — manage role slots, search/headhunt candidates, trigger DNA cloning |
| `/teams/[id]/build` | Build workspace — chat with individual cloned candidates or run PM orchestration across the full team |

## Key Components

| Component | Description |
|---|---|
| `TeamCard.vue` | Team summary card on the home page |
| `RoleSlot.vue` | Individual role slot on the team board (PM / SWE / Designer) |
| `CandidateSearch.vue` | GitHub username search with profile preview |
| `HeadHuntOverlay.vue` | Full-screen overlay for AI-powered candidate discovery and selection |
| `CloneDnaOverlay.vue` | Full-screen overlay that streams the live DNA cloning pipeline (collect → generate → train → save) |
| `ProfilingTree.vue` | Animated candidate profiling visualization |
| `build/ChatPanel.vue` | SSE-streaming chat panel for messaging cloned candidates |
| `build/TeamSidebar.vue` | Sidebar listing team members and switching active chat threads |

## Composables

| Composable | Description |
|---|---|
| `useApi.ts` | Typed API client for all backend REST endpoints |
| `useTeamChat.ts` | SSE streaming state management for direct messages and PM orchestration |

## Environment

The API base URL is set in `nuxt.config.ts`:

```ts
runtimeConfig: {
  public: {
    apiBase: 'http://localhost:8000'
  }
}
```

Override at build time with `NUXT_PUBLIC_API_BASE=https://your-backend.example.com`.
