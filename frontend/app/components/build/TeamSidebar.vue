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
  pm: 'border-amber-700 text-amber-400',
  swe: 'border-blue-700 text-blue-400',
  designer: 'border-purple-700 text-purple-400',
}
</script>

<template>
  <aside class="flex-shrink-0 w-64 border-r border-slate-800 bg-slate-900/40 flex flex-col">

    <!-- Orchestrate button -->
    <div class="p-3 border-b border-slate-800">
      <button
        class="w-full text-left px-3 py-2.5 border transition-colors text-sm font-medium"
        :class="activeThread === 'orchestrate'
          ? 'border-green-600 text-green-400 bg-green-950/30'
          : 'border-slate-700 text-slate-400 hover:border-green-700 hover:text-green-400'"
        @click="emit('setThread', 'orchestrate')"
      >
        <div class="flex items-center gap-2">
          <span class="text-base">⚡</span>
          <div>
            <p class="font-semibold">Orchestrate</p>
            <p class="text-xs text-slate-500 font-normal">PM coordinates full team</p>
          </div>
        </div>
      </button>
    </div>

    <!-- Candidate list -->
    <div class="flex-1 overflow-y-auto p-2 space-y-1">
      <p class="text-xs text-slate-600 uppercase tracking-wide px-2 py-1 mt-1">Direct Messages</p>
      <button
        v-for="candidate in candidates"
        :key="candidate.github_handle"
        class="w-full text-left p-2.5 border transition-colors"
        :class="activeThread !== 'orchestrate' && (activeThread as CandidateProfile)?.github_handle === candidate.github_handle
          ? 'border-blue-700/60 bg-blue-950/20'
          : 'border-transparent hover:border-slate-700 hover:bg-slate-900/60'"
        @click="candidate.dna_cloned && emit('setThread', candidate)"
      >
        <div class="flex items-center gap-2.5">
          <div class="relative flex-shrink-0">
            <img
              v-if="candidate.avatar_url"
              :src="candidate.avatar_url"
              :alt="candidate.name"
              class="w-8 h-8 object-cover"
              :class="candidate.dna_cloned ? '' : 'grayscale opacity-40'"
            />
            <div
              v-else
              class="w-8 h-8 bg-slate-800 flex items-center justify-center text-xs font-bold text-slate-400"
            >{{ (candidate.name ?? '?')[0]?.toUpperCase() }}</div>
            <span
              v-if="candidate.dna_cloned"
              class="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-green-500 rounded-full border border-slate-900"
            ></span>
          </div>
          <div class="flex-1 min-w-0">
            <p
              class="text-xs font-medium truncate"
              :class="candidate.dna_cloned ? 'text-slate-300' : 'text-slate-600'"
            >{{ candidate.name || candidate.github_handle }}</p>
            <div class="flex items-center gap-1 mt-0.5">
              <span
                class="text-xs border px-1 py-px"
                :class="candidate.dna_cloned ? ROLE_COLOR_CLASS[roleOf(candidate.github_handle)] : 'border-slate-800 text-slate-700'"
              >{{ ROLE_BADGE[roleOf(candidate.github_handle)] }}</span>
              <span v-if="!candidate.dna_cloned" class="text-xs text-slate-700">no DNA</span>
            </div>
          </div>
          <div class="flex-shrink-0 flex items-center gap-1.5">
            <span
              v-if="(threads[candidate.github_handle]?.length ?? 0) > 0"
              class="text-xs text-slate-600 tabular-nums"
            >{{ threads[candidate.github_handle]?.length }}</span>
            <a
              v-if="candidate.dna_cloned"
              :href="`${config.public.apiBase}/registry/${teamId}/${candidate.github_handle}/download`"
              download
              class="text-xs text-green-600 hover:text-green-400 transition-colors"
              title="Download .dna block"
              @click.stop
            >↓</a>
          </div>
        </div>
      </button>
    </div>
  </aside>
</template>
