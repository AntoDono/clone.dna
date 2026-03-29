<script setup lang="ts">
/**
 * Team board page — manage role slots, headhunt candidates, and trigger DNA cloning.
 * Shows 4 role slot cards (1 PM, 2 SWE, 1 Designer).
 * HeadHuntOverlay: AI-powered candidate discovery and selection.
 * CloneDnaOverlay: streaming .dna minting pipeline with live progress.
 */
import type { Team, CandidateProfile, SearchResult } from '~/composables/useApi'

const route = useRoute()
const router = useRouter()
const api = useApi()
const teamId = Number(route.params.id)

// ── Headhunt overlay ──────────────────────────────────────────────────────────
const showHeadhunt = ref(route.query.headhunt === 'true')

async function onHeadhuntDone() {
  showHeadhunt.value = false
  await router.replace({ query: {} })
  await fetchTeam()
}

// ── Clone DNA overlay ─────────────────────────────────────────────────────────
const showCloneDna = ref(false)
const emergencyCalibration = useState('emergencyCalibration', () => false)

// Derived from API data — true when at least one candidate has dna_cloned=true
const dnaComplete = computed(() =>
  team.value?.slots.some(s => s.candidate?.dna_cloned) ?? false
)

async function onCloneDnaDone() {
  showCloneDna.value = false
  await fetchTeam()  // refresh so dnaComplete reflects new DB state
}

const team = ref<Team | null>(null)
const loading = ref(true)
const pageError = ref('')

const activeSlotId = ref<number | null>(null)
const isSearching = ref(false)
const searchResults = ref<SearchResult | null>(null)
const searchError = ref('')
const extractionError = ref('')

type RoleMeta = { label: string; badge: string; desc: string }
const ROLE_META: Record<string, RoleMeta> = {
  pm:       { label: 'Product Manager',    badge: 'PM',     desc: 'Strategy · Roadmap · Users' },
  swe:      { label: 'Software Engineer',  badge: 'SWE',    desc: 'Build · Ship · Scale' },
  designer: { label: 'Designer',           badge: 'Design', desc: 'Interface · Systems · UX' },
}

async function fetchTeam() {
  loading.value = true
  pageError.value = ''
  try { team.value = await api.getTeam(teamId) }
  catch { pageError.value = 'Team not found.' }
  finally { loading.value = false }
}

async function scanSlot(slotId: number, force = false) {
  activeSlotId.value = slotId
  isSearching.value = true
  searchResults.value = null
  searchError.value = ''
  try {
    searchResults.value = await api.searchCandidates(teamId, slotId, force)
  } catch {
    searchError.value = 'GitHub scan failed. Check GITHUB_TOKEN and backend.'
  } finally {
    isSearching.value = false
  }
}

async function onCandidateSelected(candidate: CandidateProfile) {
  if (!activeSlotId.value) return
  try {
    await api.selectCandidate(teamId, activeSlotId.value, candidate.github_handle)
    await fetchTeam()
    searchResults.value = null
    activeSlotId.value = null
  } catch {
    searchError.value = 'Failed to select candidate.'
  }
}

async function onRemoveCandidate(slotId: number) {
  try {
    await api.removeCandidate(teamId, slotId)
    await fetchTeam()
    if (activeSlotId.value === slotId) { searchResults.value = null; activeSlotId.value = null }
  } catch { /* silent */ }
}

async function onExtracted() {
  extractionError.value = ''
  await fetchTeam()
}

function onExtractionError(msg: string) {
  extractionError.value = msg
  setTimeout(() => { extractionError.value = '' }, 6000)
}

function slotsFilled() {
  return team.value?.slots.filter(s => s.filled).length ?? 0
}

const allFilled = computed(() => {
  if (!team.value) return false
  return team.value.slots.length > 0 && team.value.slots.every(s => s.filled)
})

const codeCopied = ref(false)
async function copyPairCode() {
  if (!team.value?.discord_pair_code) return
  await navigator.clipboard.writeText(team.value.discord_pair_code)
  codeCopied.value = true
  setTimeout(() => { codeCopied.value = false }, 2000)
}

onMounted(fetchTeam)
</script>

<template>
  <div style="min-height:100vh; background:var(--bg);">

    <!-- Header -->
    <header class="page-header">
      <div class="t-header-left">
        <NuxtLink to="/" class="logo font-display">Clone.dna</NuxtLink>
        <span class="header-sep">/</span>
        <span class="header-page" style="max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          {{ team?.name ?? '…' }}
        </span>
      </div>
      <div class="t-header-right">
        <span class="slots-badge font-mono">{{ slotsFilled() }}/4 filled</span>
        <Transition name="fade-btn">
          <div v-if="team && allFilled" class="flex items-center gap-2">
            <NuxtLink
              v-if="dnaComplete"
              :to="`/teams/${teamId}/build`"
              class="btn btn-primary"
              style="font-size:13px;"
            >
              Build with Team →
            </NuxtLink>
            <button
              class="btn"
              :class="dnaComplete ? 'btn-secondary' : 'btn-primary'"
              style="font-size:13px;"
              @click="showCloneDna = true"
            >
              {{ dnaComplete ? '↺ Re-clone DNA' : 'Clone DNA →' }}
            </button>
          </div>
        </Transition>
      </div>
    </header>

    <!-- Loading / Error -->
    <div v-if="loading" class="t-state">
      <span class="streaming-dot"></span>
      <span style="color:var(--text-muted); font-size:14px;">Loading team…</span>
    </div>
    <div v-else-if="pageError" class="error-callout" style="margin:32px auto; max-width:600px;">{{ pageError }}</div>

    <!-- Content -->
    <main v-else-if="team" class="t-main">

      <!-- Title row -->
      <div class="t-title-row animate-in">
        <div>
          <p class="t-team-num font-mono">Team #{{ team.id }}</p>
          <h1 class="t-team-name font-display">{{ team.name }}</h1>
        </div>
        <div v-if="team.discord_pair_code" class="discord-code">
          <span class="discord-label">Discord pair code</span>
          <code class="discord-val font-mono">{{ team.discord_pair_code }}</code>
          <button
            class="btn btn-ghost"
            style="font-size:12px; padding:4px 10px;"
            :style="codeCopied ? 'color:var(--accent)' : ''"
            @click="copyPairCode"
          >
            {{ codeCopied ? '✓ Copied' : 'Copy' }}
          </button>
        </div>
      </div>

      <!-- Role slots grid -->
      <div class="slots-grid stagger">
        <RoleSlot
          v-for="slot in team.slots"
          :key="slot.id"
          :slot="slot"
          :meta="(ROLE_META[slot.role] as RoleMeta)"
          :is-active="activeSlotId === slot.id"
          :is-scanning="activeSlotId === slot.id && isSearching"
          :team-id="teamId"
          @scan="scanSlot(slot.id)"
          @remove="onRemoveCandidate(slot.id)"
          @extracted="onExtracted"
          @error="onExtractionError"
        />
      </div>

      <!-- Extraction error -->
      <div v-if="extractionError" class="error-callout" style="margin-bottom:16px; display:flex; justify-content:space-between; align-items:center;">
        <span>{{ extractionError }}</span>
        <button class="btn btn-ghost" style="color:var(--red);" @click="extractionError = ''">✕</button>
      </div>

      <!-- Search results panel -->
      <div v-if="isSearching || searchResults || searchError" class="search-panel animate-in">

        <!-- Searching -->
        <div v-if="isSearching" class="card search-loading">
          <span class="streaming-dot"></span>
          <div>
            <p style="font-weight:600; color:var(--text-primary); font-size:14px;">Scanning GitHub…</p>
            <p style="color:var(--text-muted); font-size:13px; margin-top:2px;">
              Finding candidates for {{ ROLE_META[team.slots.find(s => s.id === activeSlotId)?.role ?? 'swe']?.label }}
            </p>
          </div>
        </div>

        <!-- Error -->
        <div v-else-if="searchError" class="error-callout">{{ searchError }}</div>

        <!-- Results -->
        <div v-else-if="searchResults">
          <div class="search-results-header">
            <h2 class="search-results-title">
              {{ searchResults.candidates.length }} candidates
              <span class="search-results-role">for {{ ROLE_META[searchResults.role]?.label }}</span>
            </h2>
            <div class="flex gap-2">
              <button class="btn btn-secondary" style="font-size:12px;" @click="scanSlot(activeSlotId!, true)">↺ Refresh</button>
              <button class="btn btn-ghost" @click="searchResults = null; activeSlotId = null">Close</button>
            </div>
          </div>
          <CandidateSearch
            :candidates="searchResults.candidates"
            :team-id="teamId"
            :slot-id="searchResults.slot_id"
            @selected="onCandidateSelected"
          />
        </div>

      </div>
    </main>

    <!-- Headhunt overlay -->
    <Teleport to="body">
      <HeadHuntOverlay
        v-if="showHeadhunt && team"
        :team-id="teamId"
        :slots="team.slots"
        @done="onHeadhuntDone"
      />
    </Teleport>

    <!-- Clone DNA overlay -->
    <Teleport to="body">
      <CloneDnaOverlay
        v-if="showCloneDna && team"
        :team-id="teamId"
        :slots="team.slots"
        :emergency-calibration="emergencyCalibration"
        @done="onCloneDnaDone"
      />
    </Teleport>
  </div>
</template>

<style scoped>
.logo { font-size: 18px; font-weight: 400; color: var(--text-primary); letter-spacing: -0.02em; text-decoration: none; }
.header-sep { color: var(--border-mid); margin: 0 10px; }
.header-page { font-size: 13px; color: var(--text-muted); }
.t-header-left { display: flex; align-items: center; }
.t-header-right { display: flex; align-items: center; gap: 10px; }
.slots-badge {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  padding: 3px 10px;
  border-radius: 20px;
}

.t-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 48px 32px;
  max-width: 800px;
  margin: 0 auto;
}
.error-callout {
  font-size: 13px;
  color: var(--red);
  background: var(--red-light);
  border: 1px solid #FECACA;
  border-radius: var(--radius);
  padding: 10px 14px;
}

.t-main { max-width: 860px; margin: 0 auto; padding: 36px 32px 80px; }

.t-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 28px;
  flex-wrap: wrap;
}
.t-team-num { font-size: 11px; color: var(--text-muted); letter-spacing: 0.05em; margin-bottom: 4px; }
.t-team-name { font-size: 28px; font-weight: 400; letter-spacing: -0.02em; color: var(--text-primary); }

.discord-code {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 12px;
}
.discord-label { font-size: 11px; color: var(--text-muted); }
.discord-val { font-size: 13px; color: var(--text-primary); user-select: all; }

.slots-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  margin-bottom: 24px;
}

.search-panel { margin-top: 8px; }
.search-loading {
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 14px;
}
.search-results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  gap: 12px;
}
.search-results-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.search-results-role { font-size: 13px; font-weight: 400; color: var(--text-muted); margin-left: 6px; }

.fade-btn-enter-active, .fade-btn-leave-active { transition: opacity 0.25s, transform 0.25s; }
.fade-btn-enter-from, .fade-btn-leave-to { opacity: 0; transform: translateX(8px); }

@media (max-width: 640px) { .slots-grid { grid-template-columns: 1fr; } }
</style>
