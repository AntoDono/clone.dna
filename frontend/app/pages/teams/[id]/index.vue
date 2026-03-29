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
  <div class="bg-parchment min-h-screen">

    <!-- Loading / Error -->
    <div v-if="loading" class="flex items-center gap-3 py-12 px-8 max-w-[860px] mx-auto text-muted text-[14px]">
      <span class="streaming-dot"></span>
      Loading team…
    </div>
    <div v-else-if="pageError" class="max-w-[860px] mx-auto px-8 mt-8">
      <p class="text-[13px] text-danger bg-danger-light border border-[#FECACA] rounded px-4 py-3">{{ pageError }}</p>
    </div>

    <!-- Content -->
    <main v-else-if="team" class="max-w-[860px] mx-auto px-8 py-9 pb-20">

      <!-- Title row -->
      <div class="flex items-start justify-between gap-4 mb-7 flex-wrap animate-in">
        <div>
          <p class="font-mono text-[11px] text-muted tracking-widest uppercase mb-1">Team #{{ team.id }}</p>
          <h1 class="font-display text-[28px] font-normal leading-tight tracking-tighter text-ink">{{ team.name }}</h1>
        </div>

        <div class="flex items-center gap-3 shrink-0 flex-wrap">
          <span class="font-mono text-[11px] text-muted bg-subtle border border-border rounded-full px-3 py-1">
            {{ slotsFilled() }}/4 filled
          </span>
          <Transition name="fade-btn">
            <div v-if="allFilled" class="flex items-center gap-2">
              <NuxtLink
                v-if="dnaComplete"
                :to="`/teams/${teamId}/build`"
                class="btn btn-primary text-[13px]"
              >
                Build with Team →
              </NuxtLink>
              <button
                class="btn text-[13px]"
                :class="dnaComplete ? 'btn-secondary' : 'btn-primary'"
                @click="showCloneDna = true"
              >
                {{ dnaComplete ? '↺ Re-clone DNA' : 'Clone DNA →' }}
              </button>
            </div>
          </Transition>
        </div>

        <div v-if="team.discord_pair_code" class="flex items-center gap-2 bg-subtle border border-border rounded px-3 py-1.5 w-full sm:w-auto">
          <span class="text-[11px] text-muted">Discord pair code</span>
          <code class="font-mono text-[13px] text-ink select-all">{{ team.discord_pair_code }}</code>
          <button
            class="btn btn-ghost text-[12px] px-2.5 py-1"
            :class="codeCopied ? 'text-forest' : ''"
            @click="copyPairCode"
          >
            {{ codeCopied ? '✓ Copied' : 'Copy' }}
          </button>
        </div>
      </div>

      <!-- Role slots grid -->
      <div class="bg-subtle border border-border rounded p-3 shadow-soft mb-6">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3.5 stagger">
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
      </div>

      <!-- Extraction error -->
      <div v-if="extractionError" class="flex justify-between items-center text-[13px] text-danger bg-danger-light border border-[#FECACA] rounded px-4 py-2.5 mb-4">
        <span>{{ extractionError }}</span>
        <button class="btn btn-ghost text-[13px]" style="color:inherit;" @click="extractionError = ''">✕</button>
      </div>

      <!-- Search results panel -->
      <div v-if="isSearching || searchResults || searchError" class="animate-in">

        <!-- Searching -->
        <div v-if="isSearching" class="flex items-center gap-4 bg-card border border-border rounded shadow-soft px-6 py-5">
          <span class="streaming-dot"></span>
          <div>
            <p class="text-[14px] font-semibold text-ink">Scanning GitHub…</p>
            <p class="text-[13px] text-muted mt-0.5">
              Finding candidates for {{ ROLE_META[team.slots.find(s => s.id === activeSlotId)?.role ?? 'swe']?.label }}
            </p>
          </div>
        </div>

        <!-- Error -->
        <div v-else-if="searchError" class="text-[13px] text-danger bg-danger-light border border-[#FECACA] rounded px-4 py-3">
          {{ searchError }}
        </div>

        <!-- Results -->
        <div v-else-if="searchResults">
          <div class="flex items-center justify-between gap-3 mb-4">
            <h2 class="text-[15px] font-semibold text-ink">
              {{ searchResults.candidates.length }} candidates
              <span class="text-[13px] font-normal text-muted ml-1.5">for {{ ROLE_META[searchResults.role]?.label }}</span>
            </h2>
            <div class="flex gap-2">
              <button class="btn btn-secondary text-[12px]" @click="scanSlot(activeSlotId!, true)">↺ Refresh</button>
              <button class="btn btn-ghost text-[13px]" @click="searchResults = null; activeSlotId = null">Close</button>
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
.fade-btn-enter-active, .fade-btn-leave-active { transition: opacity 0.25s, transform 0.25s; }
.fade-btn-enter-from, .fade-btn-leave-to { opacity: 0; transform: translateX(8px); }
</style>
