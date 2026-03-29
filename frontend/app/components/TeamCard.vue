<script setup lang="ts">
/**
 * Summary card for a team on the home page.
 * Shows team name, creation date, and slot fill status badges.
 * Links to /teams/{id}.
 *
 * Props: team (Team)
 */
import type { Team } from '~/composables/useApi'

defineProps<{ team: Team }>()

const ROLE_LABEL: Record<string, string> = { pm: 'PM', swe: 'SWE', designer: 'Design' }
</script>

<template>
  <NuxtLink
    :to="`/teams/${team.id}`"
    class="block bg-slate-900/60 border border-slate-800 hover:border-slate-600 transition-colors p-5 group"
  >
    <div class="flex items-start justify-between mb-3">
      <div>
        <p class="text-xs text-slate-500 mb-0.5">Team #{{ team.id }}</p>
        <h2 class="font-semibold text-white group-hover:text-blue-400 transition-colors">
          {{ team.name }}
        </h2>
      </div>
      <span
        class="text-xs font-medium border px-2 py-0.5"
        :class="team.slots.filter(s => s.filled).length === 4
          ? 'border-green-600 text-green-400 bg-green-950/50'
          : 'border-slate-700 text-slate-500'"
      >
        {{ team.slots.filter(s => s.filled).length }}/4
      </span>
    </div>

    <div class="flex flex-wrap gap-1.5">
      <span
        v-for="slot in team.slots"
        :key="slot.id"
        class="text-xs border px-2 py-0.5"
        :class="slot.filled
          ? 'border-green-600 text-green-400 bg-green-950/50'
          : 'border-slate-700 text-slate-600'"
      >
        {{ ROLE_LABEL[slot.role] }}{{ slot.slot_index > 0 ? ` #${slot.slot_index + 1}` : '' }}
      </span>
    </div>

    <p class="text-xs text-slate-500 mt-3">
      {{ new Date(team.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }}
    </p>
  </NuxtLink>
</template>
