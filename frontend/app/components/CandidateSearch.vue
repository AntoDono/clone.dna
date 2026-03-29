<script setup lang="ts">
/**
 * Collapsible list of GitHub candidates from a headhunt or search result.
 * Clicking a candidate expands their full ProfilingTree profile.
 * "Select Candidate" button emits the candidate back to the parent for slot assignment.
 *
 * Props: candidates (CandidateProfile[]), teamId (number), slotId (number)
 * Emits: selected (CandidateProfile)
 */
import type { CandidateProfile } from '~/composables/useApi'

const props = defineProps<{
  candidates: CandidateProfile[]
  teamId: number
  slotId: number
}>()

const emit = defineEmits<{
  selected: [candidate: CandidateProfile]
}>()

const expandedHandle = ref<string | null>(null)
const selecting = ref<string | null>(null)

function toggle(handle: string) {
  expandedHandle.value = expandedHandle.value === handle ? null : handle
}

function select(candidate: CandidateProfile) {
  selecting.value = candidate.github_handle
  emit('selected', candidate)
}
</script>

<template>
  <div class="space-y-3">
    <div
      v-for="candidate in candidates"
      :key="candidate.github_handle"
      class="bg-slate-900/60 border transition-colors"
      :class="expandedHandle === candidate.github_handle
        ? 'border-blue-500'
        : 'border-slate-800 hover:border-slate-600'"
    >
      <!-- Header row — always visible -->
      <button
        class="w-full flex items-start gap-4 p-4 text-left"
        @click="toggle(candidate.github_handle)"
      >
        <ProfilingTree :candidate="candidate" :expanded="false" class="flex-1" />
        <span class="text-slate-500 mt-1 flex-shrink-0">{{ expandedHandle === candidate.github_handle ? '▲' : '▼' }}</span>
      </button>

      <!-- Expanded profile -->
      <div v-if="expandedHandle === candidate.github_handle" class="px-4 pb-4 border-t border-slate-800 pt-4">
        <ProfilingTree :candidate="candidate" :expanded="true" />

        <div class="flex items-center justify-between mt-5 pt-4 border-t border-slate-800">
          <a
            v-if="candidate.profile_url"
            :href="candidate.profile_url"
            target="_blank"
            rel="noopener"
            class="text-xs text-slate-500 hover:text-blue-400 transition-colors"
          >
            ↗ View profile
          </a>
          <div v-else class="flex-1"></div>
          <button
            class="border border-blue-500 text-blue-400 text-sm font-medium px-5 py-2 hover:bg-blue-600 hover:text-white transition-colors disabled:opacity-40"
            :disabled="!!selecting"
            @click="select(candidate)"
          >
            {{ selecting === candidate.github_handle ? 'Selecting...' : 'Select Candidate' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
