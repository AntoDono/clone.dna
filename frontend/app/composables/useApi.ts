/** GitHub repository metadata from public profile data */
export interface Repo {
  name: string
  description: string
  stars: number
  language: string
  url: string
  topics: string[]
}

/** Structured candidate profile built from GitHub data and Grok extraction */
export interface CandidateProfile {
  github_handle: string
  name: string
  avatar_url: string
  bio: string
  location: string
  followers: number
  public_repos: number
  top_repos: Repo[]
  languages: Record<string, number>
  skills: string[]
  soft_skills: string[]
  description: string
  profile_url: string
  id?: number
  selected_at?: string
  /** Whether the candidate's .dna block has been successfully minted */
  dna_cloned?: boolean
  /** Filesystem path to the minted .dna block directory */
  dna_path?: string | null
  /** ISO timestamp of when DNA cloning completed */
  dna_cloned_at?: string | null
  /** Architectural patterns inferred by Grok semantic code analysis */
  architectural_patterns?: string[]
  /** Code quality signals inferred by Grok semantic code analysis */
  code_quality_signals?: string[]
  /** Problem domains inferred by Grok semantic code analysis */
  domain_expertise?: string[]
}

/** A single message in a build workspace thread */
export interface ChatMessage {
  id: number
  thread: string
  sender: string
  content: string
  created_at: string
}

/** A role slot (pm/swe/designer) within a team, tracking fill status and candidate assignment */
export interface RoleSlot {
  id: number
  role: 'pm' | 'swe' | 'designer'
  slot_index: number
  filled: boolean
  candidate: CandidateProfile | null
}

/** A hiring team with a fixed 4-slot layout (1 PM, 2 SWE, 1 Designer) */
export interface Team {
  id: number
  name: string
  discord_pair_code: string | null
  created_at: string
  slots: RoleSlot[]
}

export interface SearchResult {
  role: string
  slot_id: number
  candidates: CandidateProfile[]
}

export interface CandidateFitScore {
  handle: string
  overall_score: number
  technical_fit: number
  domain_fit: number
  seniority_match: number
  reasoning: string
  strengths: string[]
  gaps: string[]
  candidate: CandidateProfile | null
}

export interface FitScoreResponse {
  job_description: string
  role: string
  total_scored: number
  ranked: CandidateFitScore[]
}

/** A minted .dna block record as returned by the developer self-service endpoint */
export interface DnaBlock {
  team_id: string
  handle: string
  version: string
  base_model: string | null
  created: string | null
  consent_status: string
  consent_verified: boolean
  revocable: boolean
  revoked: boolean
  revoked_at: string | null
  source_urls: string[]
  revocation_endpoint: string
}

/** Read the stored JWT — returns null if not available (SSR or not logged in). */
function getAuthHeaders(): Record<string, string> {
  if (!import.meta.client) return {}
  const token = localStorage.getItem('auth_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** Typed API client for all Clone.dna backend REST endpoints. Use within Nuxt component context. */
export const useApi = () => {
  const config = useRuntimeConfig()
  const base = config.public.apiBase

  const h = () => getAuthHeaders()

  return {
    /** Remove token and username from storage (call before redirecting to /login). */
    logout: () => {
      if (import.meta.client) {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('auth_username')
      }
    },

    /** Currently logged-in username, or null. */
    getUsername: (): string | null =>
      import.meta.client ? localStorage.getItem('auth_username') : null,

    getTeams: (): Promise<Team[]> =>
      $fetch(`${base}/teams`, { headers: h() }),

    createTeam: (name: string): Promise<Team> =>
      $fetch(`${base}/teams`, { method: 'POST', body: { name }, headers: h() }),

    getTeam: (id: number): Promise<Team> =>
      $fetch(`${base}/teams/${id}`, { headers: h() }),

    deleteTeam: (id: number): Promise<void> =>
      $fetch(`${base}/teams/${id}`, { method: 'DELETE', headers: h() }),

    searchCandidates: (teamId: number, slotId: number, force = false): Promise<SearchResult> =>
      $fetch(`${base}/teams/${teamId}/roles/${slotId}/search${force ? '?force=true' : ''}`, { headers: h() }),

    selectCandidate: (teamId: number, slotId: number, github_handle: string): Promise<CandidateProfile> =>
      $fetch(`${base}/teams/${teamId}/roles/${slotId}/select`, {
        method: 'POST',
        body: { github_handle },
        headers: h(),
      }),

    extractFromWebsite: (teamId: number, slotId: number, url: string): Promise<CandidateProfile> =>
      $fetch(`${base}/teams/${teamId}/roles/${slotId}/extract-website`, {
        method: 'POST',
        body: { url },
        headers: h(),
      }),

    extractFromResume: (teamId: number, slotId: number, text: string): Promise<CandidateProfile> =>
      $fetch(`${base}/teams/${teamId}/roles/${slotId}/extract-resume`, {
        method: 'POST',
        body: { text },
        headers: h(),
      }),

    removeCandidate: (teamId: number, slotId: number): Promise<void> =>
      $fetch(`${base}/teams/${teamId}/roles/${slotId}/candidate`, { method: 'DELETE', headers: h() }),

    clearHeadhuntCache: (teamId: number): Promise<void> =>
      $fetch(`${base}/teams/${teamId}/headhunt/cache`, { method: 'DELETE', headers: h() }),

    scoreHeadhuntCandidates: (teamId: number, jobDescription: string, role: string): Promise<FitScoreResponse> =>
      $fetch(`${base}/teams/${teamId}/headhunt/score`, {
        method: 'POST',
        body: { job_description: jobDescription, role },
        headers: h(),
      }),

    revokeBlock: (teamId: string, handle: string): Promise<{ status: string }> =>
      $fetch(`${base}/registry/${teamId}/${handle}`, { method: 'DELETE', headers: h() }),

    importBlock: (file: File, teamId: string): Promise<{ status: string; team_id: string; handle: string; files: number; manifest: Record<string, unknown> }> => {
      const form = new FormData()
      form.append('file', file)
      form.append('team_id', teamId)
      return $fetch(`${base}/registry/import`, { method: 'POST', body: form, headers: h() })
    },
    developerLookup: (handle: string): Promise<{ handle: string; total: number; blocks: DnaBlock[]; message: string }> =>
      $fetch(`${base}/registry/developer/${encodeURIComponent(handle)}`),

    getBuildMessages: (teamId: number, thread: string): Promise<ChatMessage[]> =>
      $fetch(`${base}/teams/${teamId}/build/messages?thread=${encodeURIComponent(thread)}`, { headers: h() }),
  }
}
