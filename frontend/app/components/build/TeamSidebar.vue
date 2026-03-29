<script setup lang="ts">
import type { CandidateProfile, ChatMessage } from '~/composables/useApi'
import type { ActiveThread } from '~/composables/useTeamChat'

const props = defineProps<{
  candidates: CandidateProfile[]
  activeThread: ActiveThread | null
  threads: Record<string, ChatMessage[]>
  roleOf: (handle: string) => string
  teamId: number
}>()

const config = useRuntimeConfig()

const emit = defineEmits<{
  setThread: [thread: ActiveThread]
}>()

const ROLE_BADGE: Record<string, string> = { pm: 'PM', swe: 'SWE', designer: 'Design' }
const ROLE_COLOR_CLASS: Record<string, string> = {
  pm: 'border-amber-600 text-amber-800',
  swe: 'border-blue-600 text-blue-800',
  designer: 'border-purple-600 text-purple-800',
}
</script>

<template>
  <aside class="flex-shrink-0 w-64 border-r border-[var(--border)] bg-[var(--bg-subtle)] flex flex-col">

    <!-- Orchestrate button -->
    <div class="p-3 border-b border-[var(--border)] bg-[var(--bg-card)]">
      <button
        type="button"
        class="w-full text-left px-3 py-2.5 border transition-colors text-sm font-medium rounded"
        :class="activeThread === 'orchestrate'
          ? 'border-[var(--accent)] text-[var(--accent-text)] bg-[var(--accent-light)] shadow-sm'
          : 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent-text)] bg-[var(--bg-card)]'"
        @click="emit('setThread', 'orchestrate')"
      >
        <div class="flex items-center gap-2">
          <span class="text-base">⚡</span>
          <div>
            <p class="font-semibold text-[var(--text-primary)]">Orchestrate</p>
            <p class="text-xs text-[var(--text-muted)] font-normal">PM coordinates full team</p>
          </div>
        </div>
      </button>
    </div>

    <!-- Candidate list -->
    <div class="flex-1 overflow-y-auto p-2 space-y-1">
      <p class="text-xs text-[var(--text-muted)] uppercase tracking-wide px-2 py-1 mt-1">Direct Messages</p>
      <button
        v-for="candidate in candidates"
        :key="candidate.github_handle"
        type="button"
        class="w-full text-left p-2.5 border transition-colors rounded"
        :class="activeThread !== 'orchestrate' && (activeThread as CandidateProfile)?.github_handle === candidate.github_handle
          ? 'border-[var(--accent)] bg-[var(--accent-light)] shadow-sm'
          : 'border-transparent hover:border-[var(--border-mid)] hover:bg-[var(--bg-hover)]'"
        @click="candidate.dna_cloned && emit('setThread', candidate)"
      >
        <div class="flex items-center gap-2.5">
          <div class="relative flex-shrink-0">
            <img
              v-if="candidate.avatar_url"
              :src="candidate.avatar_url"
              :alt="candidate.name"
              class="w-8 h-8 object-cover border border-[var(--border)]"
              :class="candidate.dna_cloned ? '' : 'grayscale opacity-40'"
            />
            <div
              v-else
              class="w-8 h-8 bg-[var(--bg-card)] border border-[var(--border)] flex items-center justify-center text-xs font-bold text-[var(--text-muted)]"
            >{{ (candidate.name ?? '?')[0]?.toUpperCase() }}</div>
            <span
              v-if="candidate.dna_cloned"
              class="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-[var(--accent)] rounded-full border-2 border-[var(--bg-card)]"
            ></span>
          </div>
          <div class="flex-1 min-w-0">
            <p
              class="text-xs font-medium truncate"
              :class="candidate.dna_cloned ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)]'"
            >{{ candidate.name || candidate.github_handle }}</p>
            <div class="flex items-center gap-1 mt-0.5">
              <span
                class="text-xs border px-1 py-px rounded bg-[var(--bg-card)]"
                :class="candidate.dna_cloned ? ROLE_COLOR_CLASS[roleOf(candidate.github_handle)] : 'border-[var(--border)] text-[var(--text-muted)]'"
              >{{ ROLE_BADGE[roleOf(candidate.github_handle)] }}</span>
              <span v-if="!candidate.dna_cloned" class="text-xs text-[var(--text-muted)]">no DNA</span>
            </div>
          </div>
          <div class="flex-shrink-0 flex items-center gap-1.5">
            <span
              v-if="(threads[candidate.github_handle]?.length ?? 0) > 0"
              class="text-xs text-[var(--text-muted)] tabular-nums"
            >{{ threads[candidate.github_handle]?.length }}</span>
            <a
              v-if="candidate.dna_cloned"
              :href="`${config.public.apiBase}/registry/${teamId}/${candidate.github_handle}/download`"
              download
              class="text-xs text-[var(--accent-text)] hover:text-[var(--accent)] transition-colors"
              title="Download .dna block"
              @click.stop
            >↓</a>
          </div>
        </div>
      </button>
    </div>
  </aside>
</template>
