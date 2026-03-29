<script setup lang="ts">
/**
 * Candidate profile card with collapsed and expanded views.
 * Collapsed: name, avatar, GitHub handle, follower count, top 2 skills.
 * Expanded: bio, soft skill badges, technical skill badges,
 * top 4 repositories with star counts, programming language bar charts.
 *
 * Props: candidate (CandidateProfile), expanded (boolean)
 */
import type { CandidateProfile } from '~/composables/useApi'

const props = defineProps<{
  candidate: CandidateProfile
  expanded: boolean
}>()

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
  <div class="pt-container">

    <!-- Identity row (always visible) -->
    <div class="pt-identity">
      <img
        v-if="candidate.avatar_url"
        :src="candidate.avatar_url"
        :alt="candidate.name"
        class="pt-avatar"
      />
      <div v-else class="pt-avatar pt-avatar--fallback">
        {{ (candidate.name ?? '?')[0]?.toUpperCase() }}
      </div>
      <div class="pt-identity-text">
        <p class="pt-name">{{ candidate.name }}</p>
        <p class="pt-handle font-mono">
          @{{ candidate.github_handle }}<span v-if="candidate.location"> · {{ candidate.location }}</span>
        </p>
      </div>
    </div>

    <!-- Expanded details -->
    <div v-if="expanded" class="pt-details">

      <p v-if="candidate.description" class="pt-role-desc">{{ candidate.description }}</p>
      <p v-if="candidate.bio" class="pt-bio">"{{ candidate.bio }}"</p>
      <p class="pt-stats">{{ fmt(candidate.followers) }} followers · {{ candidate.public_repos }} public repos</p>

      <!-- Soft skills -->
      <div v-if="candidate.soft_skills?.length" class="pt-section">
        <p class="pt-section-label">Soft Skills</p>
        <div class="pt-pills">
          <span
            v-for="skill in candidate.soft_skills"
            :key="skill"
            class="pt-pill"
            style="border-color:#FDE68A; background:#FFFBEB; color:#92400E;"
          >{{ skill }}</span>
        </div>
      </div>

      <!-- Technical skills -->
      <div v-if="candidate.skills?.length" class="pt-section">
        <p class="pt-section-label">Skills</p>
        <div class="pt-pills">
          <span
            v-for="skill in candidate.skills"
            :key="skill"
            class="pt-pill"
            style="border-color:#BFDBFE; background:#EFF6FF; color:#1E40AF;"
          >{{ skill }}</span>
        </div>
      </div>

      <!-- Top repos -->
      <div v-if="candidate.top_repos?.length" class="pt-section">
        <p class="pt-section-label">Repositories</p>
        <div class="pt-repos">
          <a
            v-for="repo in candidate.top_repos.slice(0, 4)"
            :key="repo.name"
            :href="repo.url"
            target="_blank"
            rel="noopener"
            class="pt-repo"
          >
            <div class="pt-repo-left">
              <span class="pt-repo-name">{{ repo.name }}</span>
              <span v-if="repo.language" class="pt-repo-lang font-mono">{{ repo.language }}</span>
            </div>
            <span class="pt-repo-stars">★ {{ fmt(repo.stars) }}</span>
          </a>
        </div>
      </div>

      <!-- Languages -->
      <div v-if="topLangs.length" class="pt-section">
        <p class="pt-section-label">Languages</p>
        <div class="pt-langs">
          <div v-for="([lang, pct]) in topLangs" :key="lang" class="pt-lang-row">
            <span class="pt-lang-name">{{ lang }}</span>
            <div class="pt-lang-track">
              <div class="pt-lang-bar" :style="{ width: pct + '%' }"></div>
            </div>
            <span class="pt-lang-pct font-mono">{{ pct }}%</span>
          </div>
        </div>
      </div>

      <!-- Semantic code analysis -->
      <div
        v-if="candidate.architectural_patterns?.length || candidate.code_quality_signals?.length || candidate.domain_expertise?.length"
        class="pt-analysis"
      >
        <p class="pt-section-label" style="margin-bottom:12px;">Code Analysis</p>

        <div v-if="candidate.domain_expertise?.length" class="pt-section">
          <p class="pt-subsection-label">Domains</p>
          <div class="pt-pills">
            <span
              v-for="d in candidate.domain_expertise"
              :key="d"
              class="pt-pill"
              style="border-color:#DDD6FE; background:#F5F3FF; color:#5B21B6;"
            >{{ d }}</span>
          </div>
        </div>

        <div v-if="candidate.architectural_patterns?.length" class="pt-section">
          <p class="pt-subsection-label">Architecture</p>
          <div class="pt-pills">
            <span
              v-for="p in candidate.architectural_patterns"
              :key="p"
              class="pt-pill"
              style="border-color:#A7F3D0; background:#ECFDF5; color:#065F46;"
            >{{ p }}</span>
          </div>
        </div>

        <div v-if="candidate.code_quality_signals?.length" class="pt-section">
          <p class="pt-subsection-label">Quality Signals</p>
          <div class="pt-pills">
            <span
              v-for="s in candidate.code_quality_signals"
              :key="s"
              class="pt-pill"
            >{{ s }}</span>
          </div>
        </div>
      </div>

    </div>

    <!-- Collapsed summary -->
    <p v-else class="pt-summary font-mono">
      {{ fmt(candidate.followers) }} followers
      <template v-if="candidate.soft_skills?.length"> · {{ candidate.soft_skills.slice(0, 2).join(' · ') }}</template>
      <template v-else-if="candidate.skills?.length"> · {{ candidate.skills.slice(0, 2).join(' · ') }}</template>
    </p>

  </div>
</template>

<style scoped>
.pt-container { font-size: 13px; color: #1C1811; }

/* Identity */
.pt-identity { display: flex; align-items: center; gap: 12px; }
.pt-avatar {
  width: 36px; height: 36px;
  border: 1px solid #E2DDD6;
  border-radius: 2px;
  object-fit: cover;
  flex-shrink: 0;
}
.pt-avatar--fallback {
  background: #F3F0EB;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #6B6050;
  border-radius: 2px;
}
.pt-identity-text { min-width: 0; }
.pt-name { font-size: 14px; font-weight: 600; color: #1C1811; }
.pt-handle { font-size: 11px; color: #A8A098; }

/* Collapsed */
.pt-summary { font-size: 11px; color: #A8A098; margin-top: 4px; }

/* Expanded */
.pt-details { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }

.pt-role-desc { font-size: 13px; font-weight: 600; color: #166534; }
.pt-bio { font-size: 13px; color: #6B6050; font-style: italic; }
.pt-stats { font-size: 12px; color: #A8A098; }

.pt-section { display: flex; flex-direction: column; gap: 6px; }
.pt-section-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #A8A098;
}
.pt-subsection-label {
  font-size: 11px;
  font-weight: 600;
  color: #6B6050;
  margin-bottom: 4px;
}
.pt-pills { display: flex; flex-wrap: wrap; gap: 4px; }
.pt-pill {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 2px;
  border: 1px solid #E2DDD6;
  background: #F3F0EB;
  color: #6B6050;
  font-family: 'IBM Plex Mono', monospace;
}

/* Repos */
.pt-repos { display: flex; flex-direction: column; gap: 4px; }
.pt-repo {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 10px;
  border: 1px solid #E2DDD6;
  border-radius: 2px;
  text-decoration: none;
  background: #FAFAF8;
  transition: border-color 0.12s, background 0.12s;
}
.pt-repo:hover { border-color: #86EFAC; background: #F0FDF4; }
.pt-repo-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.pt-repo-name { font-size: 13px; font-weight: 500; color: #1C1811; }
.pt-repo:hover .pt-repo-name { color: #166534; }
.pt-repo-lang { font-size: 11px; color: #A8A098; }
.pt-repo-stars { font-size: 11px; color: #A8A098; flex-shrink: 0; }

/* Languages */
.pt-langs { display: flex; flex-direction: column; gap: 6px; }
.pt-lang-row { display: flex; align-items: center; gap: 10px; }
.pt-lang-name { font-size: 12px; color: #6B6050; width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pt-lang-track { flex: 1; height: 4px; background: #E2DDD6; border-radius: 2px; overflow: hidden; }
.pt-lang-bar { height: 100%; background: #166534; border-radius: 2px; transition: width 0.5s; }
.pt-lang-pct { font-size: 11px; color: #A8A098; width: 32px; text-align: right; }

/* Code analysis */
.pt-analysis {
  padding-top: 12px;
  border-top: 1px solid #E2DDD6;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
