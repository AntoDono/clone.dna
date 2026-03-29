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
    class="group block bg-card border border-border rounded shadow-soft hover:border-mid hover:shadow-card hover:-translate-y-px transition-all duration-150 p-5 no-underline"
  >
    <div class="flex items-start justify-between mb-3 gap-2">
      <div class="min-w-0">
        <p class="font-mono text-[11px] text-muted mb-1">#{{ team.id }}</p>
        <h2 class="text-[15px] font-semibold text-ink group-hover:text-forest transition-colors leading-snug truncate">
          {{ team.name }}
        </h2>
      </div>
      <span
        class="shrink-0 font-mono text-[11px] px-2 py-0.5 rounded-[2px] border"
        :style="team.slots.filter(s => s.filled).length === 4
          ? 'background:#DCFCE7; border-color:#86EFAC; color:#14532D;'
          : 'background:#F3F0EB; border-color:#E2DDD6; color:#A8A098;'"
      >
        {{ team.slots.filter(s => s.filled).length }}/4
      </span>
    </div>

    <div class="flex flex-wrap gap-1.5 mb-3">
      <span
        v-for="slot in team.slots"
        :key="slot.id"
        class="font-mono text-[11px] px-2 py-0.5 rounded-[2px] border"
        :style="slot.filled
          ? 'background:#DCFCE7; border-color:#86EFAC; color:#14532D;'
          : 'background:#F3F0EB; border-color:#E2DDD6; color:#A8A098;'"
      >
        {{ ROLE_LABEL[slot.role] }}{{ slot.slot_index > 0 ? ` #${slot.slot_index + 1}` : '' }}
      </span>
    </div>

    <div class="flex items-center justify-between pt-3 border-t border-border">
      <p class="text-[12px] text-muted">
        {{ new Date(team.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }}
      </p>
      <span class="text-[12px] text-muted group-hover:text-forest transition-colors">Open →</span>
    </div>
  </NuxtLink>
</template>
