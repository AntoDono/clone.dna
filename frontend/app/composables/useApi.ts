export interface Repo {
  name: string
  description: string
  stars: number
  language: string
  url: string
  topics: string[]
}

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
  dna_cloned?: boolean
  dna_path?: string | null
  dna_cloned_at?: string | null
}

export interface ChatMessage {
  id: number
  thread: string
  sender: string
  content: string
  created_at: string
}

export interface RoleSlot {
  id: number
  role: 'pm' | 'swe' | 'designer'
  slot_index: number
  filled: boolean
  candidate: CandidateProfile | null
}

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

export const useApi = () => {
  const config = useRuntimeConfig()
  const base = config.public.apiBase

  return {
    getTeams: (): Promise<Team[]> =>
      $fetch(`${base}/teams`),

    createTeam: (name: string): Promise<Team> =>
      $fetch(`${base}/teams`, { method: 'POST', body: { name } }),

    getTeam: (id: number): Promise<Team> =>
      $fetch(`${base}/teams/${id}`),

    deleteTeam: (id: number): Promise<void> =>
      $fetch(`${base}/teams/${id}`, { method: 'DELETE' }),

    searchCandidates: (teamId: number, slotId: number, force = false): Promise<SearchResult> =>
      $fetch(`${base}/teams/${teamId}/roles/${slotId}/search${force ? '?force=true' : ''}`),

    selectCandidate: (teamId: number, slotId: number, github_handle: string): Promise<CandidateProfile> =>
      $fetch(`${base}/teams/${teamId}/roles/${slotId}/select`, {
        method: 'POST',
        body: { github_handle },
      }),

    extractFromWebsite: (teamId: number, slotId: number, url: string): Promise<CandidateProfile> =>
      $fetch(`${base}/teams/${teamId}/roles/${slotId}/extract-website`, {
        method: 'POST',
        body: { url },
      }),

    extractFromResume: (teamId: number, slotId: number, text: string): Promise<CandidateProfile> =>
      $fetch(`${base}/teams/${teamId}/roles/${slotId}/extract-resume`, {
        method: 'POST',
        body: { text },
      }),

    removeCandidate: (teamId: number, slotId: number): Promise<void> =>
      $fetch(`${base}/teams/${teamId}/roles/${slotId}/candidate`, { method: 'DELETE' }),

    clearHeadhuntCache: (teamId: number): Promise<void> =>
      $fetch(`${base}/teams/${teamId}/headhunt/cache`, { method: 'DELETE' }),

    getBuildMessages: (teamId: number, thread: string): Promise<ChatMessage[]> =>
      $fetch(`${base}/teams/${teamId}/build/messages?thread=${encodeURIComponent(thread)}`),
  }
}
