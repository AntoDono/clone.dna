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

async function scanSlot(slotId: number) {
  activeSlotId.value = slotId
  isSearching.value = true
  searchResults.value = null
  searchError.value = ''
  try {
    searchResults.value = await api.searchCandidates(teamId, slotId)
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

onMounted(fetchTeam)
</script>

<template>
  <div class="min-h-screen bg-slate-950">

    <!-- Header -->
    <header class="bg-slate-900/80 border-b border-slate-800 px-6 py-4 flex items-center justify-between backdrop-blur">
      <NuxtLink to="/" class="flex items-center gap-3 text-blue-400 hover:text-blue-300 transition-colors">
        <span class="text-xl font-bold tracking-tight text-white">Clone.dna</span>
        <span class="text-sm text-slate-500">← Teams</span>
      </NuxtLink>
      <div class="flex items-center gap-4">
        <span class="text-sm text-slate-500">{{ slotsFilled() }}/4 filled</span>
        <Transition name="fade-btn">
          <div v-if="team && allFilled" class="flex items-center gap-3">
            <NuxtLink
              v-if="dnaComplete"
              :to="`/teams/${teamId}/build`"
              class="text-sm font-semibold px-4 py-2 border border-green-600 text-green-400 hover:bg-green-950/40 transition-colors"
            >
              Build with Team →
            </NuxtLink>
            <button
              class="text-sm font-semibold px-4 py-2 border transition-colors"
              :class="dnaComplete
                ? 'border-slate-700 text-slate-400 hover:bg-slate-800/40'
                : 'border-blue-600 text-blue-400 hover:bg-blue-950/40'"
              @click="showCloneDna = true"
            >
              {{ dnaComplete ? '↺ Re-clone DNA' : 'Clone DNA →' }}
            </button>
          </div>
        </Transition>
      </div>
    </header>

    <!-- Loading / Error -->
    <div v-if="loading" class="max-w-4xl mx-auto px-6 py-10 text-slate-500 text-sm">Loading...</div>
    <div v-else-if="pageError" class="max-w-4xl mx-auto px-6 py-10 text-red-400 text-sm">{{ pageError }}</div>

    <!-- Content -->
    <main v-else-if="team" class="max-w-4xl mx-auto px-6 py-10">

      <!-- Title -->
      <div class="mb-8">
        <p class="text-xs text-slate-500 uppercase tracking-wide mb-1">Team #{{ team.id }}</p>
        <h1 class="text-2xl font-semibold text-white">{{ team.name }}</h1>
      </div>

      <!-- Role slots grid -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
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
      <div
        v-if="extractionError"
        class="mb-4 border border-red-800 bg-red-950/50 px-4 py-3 flex items-center justify-between text-sm"
      >
        <span class="text-red-400">{{ extractionError }}</span>
        <button class="text-red-500 hover:text-red-300 ml-4" @click="extractionError = ''">✕</button>
      </div>

      <!-- Search results panel -->
      <div v-if="isSearching || searchResults || searchError">

        <!-- Searching -->
        <div v-if="isSearching" class="bg-slate-900/60 border border-slate-700 p-8 text-center">
          <p class="text-blue-400 font-medium">Scanning GitHub...</p>
          <p class="text-slate-500 text-sm mt-1">
            Finding candidates for
            {{ ROLE_META[team.slots.find(s => s.id === activeSlotId)?.role ?? 'swe']?.label }}
          </p>
        </div>

        <!-- Error -->
        <div v-else-if="searchError" class="border border-red-800 bg-red-950/50 px-4 py-3 text-sm text-red-400">
          {{ searchError }}
        </div>

        <!-- Results -->
        <div v-else-if="searchResults">
          <div class="flex items-center justify-between mb-4">
            <h2 class="font-semibold text-white">
              {{ searchResults.candidates.length }} candidates found
              <span class="font-normal text-slate-500 text-sm ml-1">
                for {{ ROLE_META[searchResults.role]?.label }}
              </span>
            </h2>
            <button
              class="text-sm text-slate-500 hover:text-slate-300 border border-slate-700 px-3 py-1 transition-colors"
              @click="searchResults = null; activeSlotId = null"
            >
              Close
            </button>
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
    <!-- Headhunt overlay (shown when ?headhunt=true on first load) -->
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
.fade-btn-enter-active,
.fade-btn-leave-active {
  transition: opacity 0.3s, transform 0.3s;
}
.fade-btn-enter-from,
.fade-btn-leave-to {
  opacity: 0;
  transform: translateX(8px);
}
</style>
