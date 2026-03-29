<script setup lang="ts">
/**
 * Full-screen overlay for AI-powered candidate discovery and team assembly.
 * Three phases: hunting (SSE streams candidates from GitHub) → selecting
 * (user picks 1 PM, 2 SWE, 1 Designer) → confirming (saves selections to DB).
 *
 * Props: teamId (number), slots (RoleSlot[])
 * Emits: done
 */
import type { CandidateProfile, RoleSlot, CandidateFitScore } from '~/composables/useApi'

const props = defineProps<{
  teamId: number
  slots: RoleSlot[]
}>()

const emit = defineEmits<{
  done: []
}>()

const config = useRuntimeConfig()
const api = useApi()

type Phase = 'hunting' | 'selecting' | 'confirming'
const phase = ref<Phase>('hunting')

const pool = ref<Record<string, CandidateProfile[]>>({ pm: [], swe: [], designer: [] })

const selectedPm = ref<string | null>(null)
const selectedSwe = ref<string[]>([])
const selectedDesigner = ref<string | null>(null)
const confirmError = ref('')
const streamError = ref('')
const fromCache = ref(false)
const isRefetching = ref(false)

// ── Fit scoring ───────────────────────────────────────────────────────────────
const showScorePanel = ref(false)
const jdInput = ref('')
const scoring = ref(false)
const scoreError = ref('')
const fitScores = ref<Record<string, CandidateFitScore>>({})

function fitScore(handle: string) {
  return fitScores.value[handle] ?? null
}

async function runFitScore() {
  const jd = jdInput.value.trim()
  if (jd.length < 20) { scoreError.value = 'Add more detail to the job description'; return }
  scoring.value = true
  scoreError.value = ''
  try {
    const res = await api.scoreHeadhuntCandidates(props.teamId, jd, 'swe')
    const map: Record<string, CandidateFitScore> = {}
    for (const s of res.ranked) map[s.handle] = s
    fitScores.value = map
    showScorePanel.value = false
  } catch (e: any) {
    scoreError.value = e?.data?.detail ?? 'Scoring failed — check backend'
  } finally {
    scoring.value = false
  }
}

const ROLES = [
  { key: 'pm',       label: 'Product Manager',  badge: 'PM',     need: 1 },
  { key: 'swe',      label: 'Software Engineer', badge: 'SWE',    need: 2 },
  { key: 'designer', label: 'Designer',          badge: 'Design', need: 1 },
]

// ── Slot lookup ───────────────────────────────────────────────────────────────

function getSlot(role: string, index: number): RoleSlot | undefined {
  return props.slots.find(s => s.role === role && s.slot_index === index)
}

// ── Selection helpers ─────────────────────────────────────────────────────────

// Toggle candidate selection for a role (max 1 PM, 2 SWE, 1 Designer)
function toggle(role: string, handle: string) {
  if (phase.value !== 'selecting') return
  if (role === 'pm') {
    selectedPm.value = selectedPm.value === handle ? null : handle
  } else if (role === 'designer') {
    selectedDesigner.value = selectedDesigner.value === handle ? null : handle
  } else if (role === 'swe') {
    const already = selectedSwe.value.includes(handle)
    if (already) {
      selectedSwe.value = selectedSwe.value.filter(h => h !== handle)
    } else if (selectedSwe.value.length < 2) {
      selectedSwe.value = [...selectedSwe.value, handle]
    }
  }
}

function isSelected(role: string, handle: string): boolean {
  if (role === 'pm') return selectedPm.value === handle
  if (role === 'designer') return selectedDesigner.value === handle
  if (role === 'swe') return selectedSwe.value.includes(handle)
  return false
}

function selectedCount(role: string): number {
  if (role === 'pm') return selectedPm.value ? 1 : 0
  if (role === 'designer') return selectedDesigner.value ? 1 : 0
  if (role === 'swe') return selectedSwe.value.length
  return 0
}

const canConfirm = computed(
  () => selectedPm.value !== null && selectedSwe.value.length === 2 && selectedDesigner.value !== null
)

// ── SSE stream ────────────────────────────────────────────────────────────────

let es: EventSource | null = null

// Open SSE stream to /headhunt/stream, populate pool as candidates arrive
function startStream(force = false) {
  const base = `${config.public.apiBase}/teams/${props.teamId}/headhunt/stream`
  const url = force ? `${base}?force=true` : base
  es = new EventSource(url)

  es.onmessage = (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data as string)
      if (data.cached === true && !data.done) {
        fromCache.value = true
        return
      }
      if (data.done) {
        es?.close()
        es = null
        isRefetching.value = false
        phase.value = 'selecting'
        return
      }
      if (data.error) {
        streamError.value = data.error as string
        return
      }
      if (data.role && data.candidate) {
        pool.value[data.role] = [...(pool.value[data.role] ?? []), data.candidate as CandidateProfile]
      }
    } catch { /* skip malformed events */ }
  }

  es.onerror = () => {
    es?.close()
    es = null
    isRefetching.value = false
    phase.value = 'selecting'
  }
}

// Clear server-side cache and restart the headhunt stream
async function refetchCandidates() {
  isRefetching.value = true
  fromCache.value = false
  streamError.value = ''
  phase.value = 'hunting'
  pool.value = { pm: [], swe: [], designer: [] }
  selectedPm.value = null
  selectedSwe.value = []
  selectedDesigner.value = null

  es?.close()
  es = null

  try {
    await api.clearHeadhuntCache(props.teamId)
  } catch { /* cache clear is best-effort */ }

  startStream(true)
}

// ── Confirm selections ────────────────────────────────────────────────────────

// POST all selections to assign candidates to their slots
async function confirmSelections() {
  if (!canConfirm.value) return
  confirmError.value = ''
  phase.value = 'confirming'
  try {
    const pmSlot = getSlot('pm', 0)
    if (pmSlot && selectedPm.value)
      await api.selectCandidate(props.teamId, pmSlot.id, selectedPm.value)

    const sweSlot0 = getSlot('swe', 0)
    if (sweSlot0 && selectedSwe.value[0])
      await api.selectCandidate(props.teamId, sweSlot0.id, selectedSwe.value[0])

    const sweSlot1 = getSlot('swe', 1)
    if (sweSlot1 && selectedSwe.value[1])
      await api.selectCandidate(props.teamId, sweSlot1.id, selectedSwe.value[1])

    const designerSlot = getSlot('designer', 0)
    if (designerSlot && selectedDesigner.value)
      await api.selectCandidate(props.teamId, designerSlot.id, selectedDesigner.value)

    emit('done')
  } catch (e: any) {
    confirmError.value = e?.data?.detail ?? e?.message ?? 'Failed to save selections.'
    phase.value = 'selecting'
  }
}

function skipOverlay() {
  es?.close()
  emit('done')
}

onMounted(() => startStream())
onUnmounted(() => es?.close())
</script>

<template>
  <div class="fixed inset-0 z-50 flex flex-col bg-slate-950 overflow-hidden">

    <!-- ── Header ─────────────────────────────────────────────────────────── -->
    <div class="flex-shrink-0 flex items-center justify-between px-8 py-5 border-b border-slate-800">
      <div class="flex items-center gap-4">
        <span class="text-lg font-bold text-white tracking-tight">Clone.dna</span>
        <span class="text-slate-600">|</span>
        <span v-if="phase === 'hunting'" class="text-slate-300 text-sm font-medium flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></span>
          Head Hunting Candidates<span class="dots-anim"></span>
        </span>
        <span v-else-if="phase === 'selecting'" class="text-white text-sm font-semibold">
          Build Your Team
        </span>
        <span v-else class="text-slate-300 text-sm font-medium flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
          Saving selections<span class="dots-anim"></span>
        </span>
      </div>

      <div class="flex items-center gap-3">
        <!-- Per-role slot fill status -->
        <template v-if="phase === 'selecting'">
          <span
            v-for="role in ROLES"
            :key="role.key"
            class="text-xs font-medium px-2 py-1 border transition-colors"
            :class="selectedCount(role.key) === role.need
              ? 'border-green-600 text-green-400 bg-green-950/50'
              : 'border-slate-700 text-slate-500'"
          >
            {{ role.badge }} {{ selectedCount(role.key) }}/{{ role.need }}
          </span>
        </template>
        <!-- Cache indicator + refetch -->
        <template v-if="phase === 'selecting'">
          <span v-if="fromCache" class="text-xs text-slate-600 border border-slate-800 px-2 py-1">
            cached
          </span>
          <button
            class="text-xs border px-3 py-1 transition-colors disabled:opacity-40"
            :class="isRefetching
              ? 'border-slate-700 text-slate-600 cursor-not-allowed'
              : 'border-slate-700 text-slate-400 hover:border-blue-600 hover:text-blue-400'"
            :disabled="isRefetching"
            @click="refetchCandidates"
          >
            {{ isRefetching ? 'Fetching...' : '↺ Refetch' }}
          </button>
        </template>
        <!-- Score for fit button (only when candidates are loaded) -->
        <template v-if="phase === 'selecting'">
          <button
            class="text-xs border px-3 py-1 transition-colors"
            :class="Object.keys(fitScores).length
              ? 'border-green-600 text-green-400'
              : 'border-slate-700 text-slate-400 hover:border-violet-500 hover:text-violet-400'"
            @click="showScorePanel = true"
          >
            {{ Object.keys(fitScores).length ? '✓ Scored' : '◈ Score for Fit' }}
          </button>
        </template>
        <span v-if="streamError" class="text-xs text-red-400 max-w-sm truncate" :title="streamError">
          ⚠ {{ streamError }}
        </span>
        <button
          class="text-xs text-slate-600 hover:text-slate-300 transition-colors ml-2"
          @click="skipOverlay"
        >
          Skip →
        </button>
      </div>
    </div>

    <!-- ── Three columns ──────────────────────────────────────────────────── -->
    <div class="flex-1 grid grid-cols-3 divide-x divide-slate-800 min-h-0">
      <div
        v-for="role in ROLES"
        :key="role.key"
        class="flex flex-col min-h-0"
      >
        <!-- Column header -->
        <div class="flex-shrink-0 px-6 py-4 border-b border-slate-800">
          <div class="flex items-center justify-between mb-3">
            <div>
              <p
                class="text-xs font-bold uppercase tracking-widest"
                :class="{
                  'text-amber-400': role.key === 'pm',
                  'text-blue-400': role.key === 'swe',
                  'text-purple-400': role.key === 'designer',
                }"
              >{{ role.badge }}</p>
              <p class="text-slate-500 text-xs mt-0.5">{{ role.label }}</p>
            </div>
            <span class="text-xs tabular-nums text-slate-600">
              {{ (pool[role.key] ?? []).length }}<span class="text-slate-700">/5</span>
            </span>
          </div>
          <!-- Progress bar -->
          <div class="h-px bg-slate-800 overflow-hidden">
            <div
              class="h-full transition-all duration-500 ease-out"
              :class="{
                'bg-amber-500': role.key === 'pm',
                'bg-blue-500': role.key === 'swe',
                'bg-purple-500': role.key === 'designer',
              }"
              :style="{ width: `${(pool[role.key] ?? []).length * 20}%` }"
            ></div>
          </div>
        </div>

        <!-- Candidate list -->
        <div class="flex-1 overflow-y-auto p-3">
          <TransitionGroup name="slide-up" tag="div" class="space-y-2">
            <component
              :is="phase === 'selecting' ? 'button' : 'div'"
              v-for="candidate in pool[role.key]"
              :key="candidate.github_handle"
              class="w-full text-left p-3 border transition-colors"
              :class="isSelected(role.key, candidate.github_handle)
                ? {
                    'border-amber-500 bg-amber-950/40': role.key === 'pm',
                    'border-blue-500 bg-blue-950/40': role.key === 'swe',
                    'border-purple-500 bg-purple-950/40': role.key === 'designer',
                  }
                : phase === 'selecting'
                  ? 'border-slate-800 bg-slate-900/60 hover:border-slate-600 cursor-pointer'
                  : 'border-slate-800 bg-slate-900/60'"
              @click="toggle(role.key, candidate.github_handle)"
            >
              <div class="flex items-center gap-2.5">
                <img
                  v-if="candidate.avatar_url"
                  :src="candidate.avatar_url"
                  :alt="candidate.name"
                  class="w-7 h-7 flex-shrink-0 object-cover grayscale"
                  :class="isSelected(role.key, candidate.github_handle) ? 'grayscale-0' : ''"
                />
                <div
                  v-else
                  class="w-7 h-7 flex-shrink-0 bg-slate-800 flex items-center justify-center text-xs font-bold text-slate-400"
                >
                  {{ (candidate.name ?? '?')[0]?.toUpperCase() }}
                </div>
                <div class="min-w-0 flex-1">
                  <p
                    class="text-sm font-medium truncate transition-colors"
                    :class="isSelected(role.key, candidate.github_handle) ? 'text-white' : 'text-slate-400'"
                  >{{ candidate.name || candidate.github_handle }}</p>
                  <p class="text-xs text-slate-600 truncate">{{ candidate.location || `@${candidate.github_handle}` }}</p>
                </div>
                <span
                  v-if="isSelected(role.key, candidate.github_handle)"
                  class="flex-shrink-0 text-xs font-bold"
                  :class="{
                    'text-amber-400': role.key === 'pm',
                    'text-blue-400': role.key === 'swe',
                    'text-purple-400': role.key === 'designer',
                  }"
                >✓</span>
              </div>

              <!-- Skills shown in selecting phase -->
              <div v-if="phase === 'selecting' && candidate.skills?.length" class="mt-2 flex flex-wrap gap-1">
                <span
                  v-for="skill in candidate.skills.slice(0, 3)"
                  :key="skill"
                  class="text-xs border border-slate-700 text-slate-600 px-1.5 py-0.5"
                >{{ skill }}</span>
              </div>

              <!-- Fit score badge -->
              <div v-if="fitScore(candidate.github_handle)" class="mt-2 flex items-center gap-2">
                <span
                  class="text-xs font-bold px-2 py-0.5 border"
                  :class="fitScore(candidate.github_handle)!.overall_score >= 80
                    ? 'border-green-600 text-green-400 bg-green-950/40'
                    : fitScore(candidate.github_handle)!.overall_score >= 60
                      ? 'border-amber-600 text-amber-400 bg-amber-950/40'
                      : 'border-slate-600 text-slate-400'"
                >
                  {{ fitScore(candidate.github_handle)!.overall_score }}/100
                </span>
                <span class="text-xs text-slate-600 truncate">{{ fitScore(candidate.github_handle)!.reasoning }}</span>
              </div>
            </component>
          </TransitionGroup>

          <!-- Skeleton placeholders while hunting -->
          <div v-if="phase === 'hunting'" class="space-y-2 mt-2">
            <div
              v-for="i in Math.max(0, 5 - (pool[role.key] ?? []).length)"
              :key="`sk-${i}`"
              class="h-11 border border-slate-800/40 bg-slate-900/20 animate-pulse"
            ></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Footer (selecting / confirming) ───────────────────────────────── -->
    <Transition name="fade">
      <div
        v-if="phase !== 'hunting'"
        class="flex-shrink-0 border-t border-slate-800 bg-slate-900/80 px-8 py-4 flex items-center justify-between"
      >
        <div class="text-sm">
          <span v-if="!canConfirm" class="text-slate-500">
            Select 1 PM · 2 SWE · 1 Designer to confirm
          </span>
          <span v-else class="text-green-400 font-medium">All slots ready</span>
          <p v-if="confirmError" class="text-red-400 text-xs mt-0.5">{{ confirmError }}</p>
        </div>
        <div class="flex items-center gap-4">
          <button
            class="text-sm text-slate-500 hover:text-slate-300 transition-colors"
            :disabled="phase === 'confirming'"
            @click="skipOverlay"
          >
            Fill manually later
          </button>
          <button
            class="px-6 py-2 text-sm font-semibold transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            :class="canConfirm
              ? 'bg-blue-600 text-white hover:bg-blue-500'
              : 'bg-slate-800 text-slate-500'"
            :disabled="!canConfirm || phase === 'confirming'"
            @click="confirmSelections"
          >
            {{ phase === 'confirming' ? 'Saving...' : 'Confirm Team →' }}
          </button>
        </div>
      </div>
    </Transition>

    <!-- ── Fit score panel ────────────────────────────────────────────────── -->
    <Transition name="fade">
      <div
        v-if="showScorePanel"
        class="absolute inset-0 bg-slate-950/80 flex items-center justify-center z-10"
        @click.self="showScorePanel = false"
      >
        <div class="bg-slate-900 border border-slate-700 w-full max-w-lg p-6 space-y-4">
          <div class="flex items-center justify-between">
            <p class="text-white font-semibold">Score Candidates for Fit</p>
            <button class="text-slate-500 hover:text-white" @click="showScorePanel = false">✕</button>
          </div>
          <p class="text-slate-500 text-xs">Paste a job description — Grok will score all candidates across technical fit, domain expertise, and seniority.</p>
          <textarea
            v-model="jdInput"
            placeholder="We're hiring a senior backend engineer who lives in distributed systems, has built event-driven microservices, and has a strong open source presence..."
            class="w-full h-36 bg-slate-950 border border-slate-700 focus:border-violet-500 text-sm text-slate-300 placeholder-slate-600 p-3 outline-none resize-none"
          />
          <p v-if="scoreError" class="text-red-400 text-xs">{{ scoreError }}</p>
          <div class="flex justify-end gap-3">
            <button class="text-sm text-slate-500 hover:text-white transition-colors" @click="showScorePanel = false">Cancel</button>
            <button
              class="px-5 py-2 text-sm font-semibold transition-colors disabled:opacity-40"
              :class="scoring ? 'bg-slate-700 text-slate-400' : 'bg-violet-600 text-white hover:bg-violet-500'"
              :disabled="scoring"
              @click="runFitScore"
            >
              {{ scoring ? 'Scoring with Grok...' : 'Score All Candidates →' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── Confirming overlay spinner ─────────────────────────────────────── -->
    <Transition name="fade">
      <div
        v-if="phase === 'confirming'"
        class="absolute inset-0 bg-slate-950/70 flex items-center justify-center"
      >
        <div class="text-center space-y-3">
          <div class="w-10 h-10 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p class="text-white font-semibold">Building your team</p>
          <p class="text-slate-500 text-sm">Fetching full profiles<span class="dots-anim"></span></p>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.slide-up-enter-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.slide-up-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.dots-anim::after {
  content: '';
  animation: dots 1.4s steps(4, end) infinite;
}
@keyframes dots {
  0%   { content: ''; }
  25%  { content: '.'; }
  50%  { content: '..'; }
  75%  { content: '...'; }
  100% { content: ''; }
}
</style>
