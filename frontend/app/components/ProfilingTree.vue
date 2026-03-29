<script setup lang="ts">
/**
 * Candidate profile card with collapsed and expanded views.
 * Collapsed: name, avatar, GitHub handle, follower count, top 2 skills.
 * Expanded: bio, soft skill badges (amber), technical skill badges (blue),
 * top 4 repositories with star counts, programming language bar charts.
 *
 * Props: candidate (CandidateProfile), expanded (boolean)
 */
import type { CandidateProfile } from '~/composables/useApi'

const props = defineProps<{
  candidate: CandidateProfile
  expanded: boolean
}>()

// Abbreviate large numbers (e.g. 12400 → "12.4k")
function fmt(n: number) {
  return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n)
}

const topLangs = computed(() =>
  Object.entries(props.candidate.languages ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 4)
)
</script>

<template>
  <div class="text-sm">

    <!-- Identity row (always visible) -->
    <div class="flex items-center gap-3">
      <img
        v-if="candidate.avatar_url"
        :src="candidate.avatar_url"
        :alt="candidate.name"
        class="w-9 h-9 border border-slate-700 object-cover flex-shrink-0"
      />
      <div
        v-else
        class="w-9 h-9 border border-slate-700 bg-slate-800 flex items-center justify-center font-semibold text-slate-400 flex-shrink-0"
      >
        {{ (candidate.name ?? '?')[0]?.toUpperCase() }}
      </div>
      <div>
        <p class="font-semibold text-white">{{ candidate.name }}</p>
        <p class="text-xs text-slate-500">
          @{{ candidate.github_handle }}
          <span v-if="candidate.location"> · {{ candidate.location }}</span>
        </p>
      </div>
    </div>

    <!-- Expanded details -->
    <div v-if="expanded" class="mt-4 space-y-4">

      <!-- Role description -->
      <p v-if="candidate.description" class="text-sm text-blue-400 font-medium">
        {{ candidate.description }}
      </p>

      <!-- Bio -->
      <p v-if="candidate.bio" class="text-sm text-slate-400 italic">"{{ candidate.bio }}"</p>

      <!-- Stats -->
      <p class="text-xs text-slate-500">
        {{ fmt(candidate.followers) }} followers · {{ candidate.public_repos }} public repos
      </p>

      <!-- Soft skills -->
      <div v-if="candidate.soft_skills?.length">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1.5">Soft Skills</p>
        <div class="flex flex-wrap gap-1.5">
          <span
            v-for="skill in candidate.soft_skills"
            :key="skill"
            class="text-xs border border-amber-700 text-amber-400 bg-amber-950/40 px-2 py-0.5"
          >{{ skill }}</span>
        </div>
      </div>

      <!-- Technical skills -->
      <div v-if="candidate.skills?.length">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1.5">Skills</p>
        <div class="flex flex-wrap gap-1.5">
          <span
            v-for="skill in candidate.skills"
            :key="skill"
            class="text-xs border border-blue-700 text-blue-400 bg-blue-950/40 px-2 py-0.5"
          >{{ skill }}</span>
        </div>
      </div>

      <!-- Top repos -->
      <div v-if="candidate.top_repos?.length">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1.5">Repositories</p>
        <div class="space-y-1.5">
          <a
            v-for="repo in candidate.top_repos.slice(0, 4)"
            :key="repo.name"
            :href="repo.url"
            target="_blank"
            rel="noopener"
            class="flex items-center justify-between border border-slate-800 bg-slate-900/60 px-3 py-2 hover:border-blue-600 transition-colors group"
          >
            <div class="min-w-0">
              <span class="text-sm text-blue-400 group-hover:text-blue-300 font-medium">{{ repo.name }}</span>
              <span v-if="repo.language" class="ml-2 text-xs text-slate-500">[{{ repo.language }}]</span>
            </div>
            <span class="text-xs text-slate-500 ml-3 flex-shrink-0">★ {{ fmt(repo.stars) }}</span>
          </a>
        </div>
      </div>

      <!-- Languages -->
      <div v-if="topLangs.length">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Languages</p>
        <div class="space-y-2">
          <div v-for="([lang, pct]) in topLangs" :key="lang" class="flex items-center gap-3">
            <span class="text-xs text-slate-400 w-24 truncate">{{ lang }}</span>
            <div class="flex-1 h-1.5 bg-slate-800 overflow-hidden">
              <div
                class="h-full bg-blue-500 transition-all duration-500"
                :style="{ width: pct + '%' }"
              ></div>
            </div>
            <span class="text-xs text-slate-500 w-8 text-right">{{ pct }}%</span>
          </div>
        </div>
      </div>

      <!-- Semantic code analysis (Grok-derived) -->
      <div v-if="candidate.architectural_patterns?.length || candidate.code_quality_signals?.length || candidate.domain_expertise?.length"
           class="border-t border-slate-800 pt-4 space-y-3">
        <p class="text-xs font-medium text-slate-500 uppercase tracking-wide">Code Analysis</p>

        <div v-if="candidate.domain_expertise?.length">
          <p class="text-xs text-slate-600 mb-1">Domains</p>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="d in candidate.domain_expertise"
              :key="d"
              class="text-xs border border-violet-700 text-violet-400 bg-violet-950/40 px-2 py-0.5"
            >{{ d }}</span>
          </div>
        </div>

        <div v-if="candidate.architectural_patterns?.length">
          <p class="text-xs text-slate-600 mb-1">Architecture</p>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="p in candidate.architectural_patterns"
              :key="p"
              class="text-xs border border-emerald-700 text-emerald-400 bg-emerald-950/40 px-2 py-0.5"
            >{{ p }}</span>
          </div>
        </div>

        <div v-if="candidate.code_quality_signals?.length">
          <p class="text-xs text-slate-600 mb-1">Quality Signals</p>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="s in candidate.code_quality_signals"
              :key="s"
              class="text-xs border border-slate-600 text-slate-400 bg-slate-800/60 px-2 py-0.5"
            >{{ s }}</span>
          </div>
        </div>
      </div>

    </div>

    <!-- Collapsed summary -->
    <p v-else class="text-xs text-slate-500 mt-1">
      {{ fmt(candidate.followers) }} followers
      <template v-if="candidate.soft_skills?.length"> · {{ candidate.soft_skills.slice(0, 2).join(' · ') }}</template>
      <template v-else-if="candidate.skills?.length"> · {{ candidate.skills.slice(0, 2).join(' · ') }}</template>
    </p>
  </div>
</template>
