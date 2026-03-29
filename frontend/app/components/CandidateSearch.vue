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
  <div class="cs-list">
    <div
      v-for="candidate in candidates"
      :key="candidate.github_handle"
      class="cs-item border border-[var(--border)] bg-[var(--bg-card)] rounded shadow-sm transition-all hover:border-[var(--border-mid)] hover:shadow-md"
      :class="{ 'cs-item--open': expandedHandle === candidate.github_handle }"
    >
      <!-- Header row -->
      <button
        class="cs-header"
        @click="toggle(candidate.github_handle)"
      >
        <ProfilingTree :candidate="candidate" :expanded="false" class="cs-tree" inherit-surface />
        <span class="cs-chevron">{{ expandedHandle === candidate.github_handle ? '▲' : '▼' }}</span>
      </button>

      <!-- Expanded profile -->
      <div v-if="expandedHandle === candidate.github_handle" class="cs-expanded">
        <hr class="cs-divider" />
        <ProfilingTree :candidate="candidate" :expanded="true" inherit-surface />

        <div class="cs-footer">
          <a
            v-if="candidate.profile_url"
            :href="candidate.profile_url"
            target="_blank"
            rel="noopener"
            class="cs-profile-link font-mono"
          >
            ↗ View profile
          </a>
          <div v-else class="flex-1"></div>
          <button
            class="btn btn-primary"
            style="font-size:13px;"
            :disabled="!!selecting"
            @click="select(candidate)"
          >
            <span v-if="selecting === candidate.github_handle" class="streaming-dot" style="background:#fff;"></span>
            {{ selecting === candidate.github_handle ? 'Selecting…' : 'Select Candidate' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background-color: var(--bg);
}

.cs-item {
  overflow: hidden;
}
.cs-item--open {
  border-color: #60a5fa !important;
  box-shadow: var(--shadow-md);
}

.cs-header {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  text-align: left;
  background-color: transparent;
  border: none;
  cursor: pointer;
  transition: background-color 0.12s;
}
.cs-header:hover {
  background-color: var(--bg-hover);
}

.cs-tree { flex: 1; }
.cs-chevron { font-size: 10px; color: #A8A098; margin-top: 2px; flex-shrink: 0; }

.cs-expanded {
  padding: 0 16px 16px;
  background-color: var(--bg-card);
}
.cs-divider {
  border: none;
  border-top: 1px solid #E2DDD6;
  margin: 0 0 16px;
}

.cs-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #E2DDD6;
  gap: 12px;
}
.cs-profile-link {
  font-size: 11px;
  color: #A8A098;
  text-decoration: none;
  transition: color 0.12s;
}
.cs-profile-link:hover { color: #166534; }
</style>
