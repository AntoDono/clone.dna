<script setup lang="ts">
/**
 * Full-screen overlay for live DNA cloning progress.
 * Connects to SSE stream at /teams/{teamId}/clone-dna/stream.
 * Tracks per-candidate state machine: waiting → collecting → generating → training → saving → done/error.
 * Displays live loss values, step progress, and pair counts during training.
 * Supports emergency calibration mode (no GPU required) via ?emergency_calibration=1.
 *
 * Props: teamId (number), slots (RoleSlot[]), emergencyCalibration (boolean)
 * Emits: done
 */
import type { RoleSlot, CandidateProfile } from '~/composables/useApi'

const props = defineProps<{
  teamId: number
  slots: RoleSlot[]
  emergencyCalibration?: boolean
}>()

const emit = defineEmits<{
  done: []
}>()

const config = useRuntimeConfig()

// ── State per candidate ───────────────────────────────────────────────────────

interface TrainingConfig {
  epochs: number
  batch_size: number
  gradient_accumulation_steps: number
  effective_batch_size: number
  learning_rate: number
  optimizer: string
  lora_rank: number
  lora_alpha: number
  max_seq_length: number
  total_pairs: number
  candidate_pairs: number
  base_instruct_pairs: number
  tool_use_pairs: number
  total_steps: number
  fp16: boolean
}

interface EvalMetrics {
  final_loss: number | null
  best_loss: number | null
  style_consistency: number | null
  style_metrics: Record<string, unknown> | null
  domain_accuracy: number | null
  humaneval_score: number | null
  latency_overhead_ms: number | null
}

interface CandidateState {
  candidate: CandidateProfile
  role: string
  phase: 'waiting' | 'collecting' | 'generating' | 'training' | 'saving' | 'eval' | 'done' | 'error' | 'skipped'
  message: string
  step: number
  totalSteps: number
  loss: number | null
  bestLoss: number | null
  learningRate: number | null
  epoch: number | null
  pairsCount: number
  path: string | null
  error: string | null
  trainingConfig: TrainingConfig | null
  evalMetrics: EvalMetrics | null
}

const states = ref<CandidateState[]>([])
const overallDone = ref(false)
const streamError = ref('')

// Build initial states from filled slots
const ROLE_BADGE: Record<string, string> = { pm: 'PM', swe: 'SWE', designer: 'Design' }
const ROLE_COLOR: Record<string, string> = {
  pm: 'amber',
  swe: 'blue',
  designer: 'purple',
}

function buildInitialStates() {
  states.value = props.slots
    .filter(s => s.filled && s.candidate)
    .map(s => ({
      candidate: s.candidate!,
      role: s.role,
      phase: 'waiting' as const,
      message: 'Queued...',
      step: 0,
      totalSteps: 0,
      loss: null,
      bestLoss: null,
      learningRate: null,
      epoch: null,
      pairsCount: 0,
      path: null,
      error: null,
      trainingConfig: null,
      evalMetrics: null,
    }))
}

function getState(handle: string): CandidateState | undefined {
  return states.value.find(s => s.candidate.github_handle === handle)
}

// ── SSE stream ────────────────────────────────────────────────────────────────

let es: EventSource | null = null

function startStream() {
  const token = import.meta.client ? (localStorage.getItem('auth_token') ?? '') : ''
  const params = new URLSearchParams({ token })
  if (props.emergencyCalibration) params.set('emergency_calibration', '1')
  const url = `${config.public.apiBase}/teams/${props.teamId}/clone-dna/stream?${params}`
  es = new EventSource(url)

  es.onmessage = (event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data as string)
      handleEvent(data)
    } catch { /* skip malformed */ }
  }

  es.onerror = () => {
    es?.close()
    es = null
    streamError.value = 'Connection lost. Refresh to retry.'
  }
}

function handleEvent(data: Record<string, unknown>) {
  const phase = data.phase as string
  const handle = data.candidate as string | undefined

  // Ignore keepalive heartbeats
  if (phase === 'heartbeat') return

  if (phase === 'start') {
    // All candidates launch in parallel — mark them all as active immediately
    for (const st of states.value) {
      st.phase = 'collecting'
      st.message = 'Starting...'
    }
    return
  }

  if (phase === 'done') {
    es?.close()
    es = null
    overallDone.value = true
    return
  }

  if (!handle) return
  const st = getState(handle)
  if (!st) return

  if (phase === 'collecting') {
    st.phase = 'collecting'
    st.message = (data.message as string) || 'Collecting code...'
  } else if (phase === 'generating') {
    st.phase = 'generating'
    if (data.count !== undefined) st.pairsCount = data.count as number
    st.message = (data.message as string) || `Generating training pairs...`
  } else if (phase === 'training') {
    st.phase = 'training'
    if (data.training_config) {
      st.trainingConfig = data.training_config as TrainingConfig
    }
    if (data.total_steps) st.totalSteps = data.total_steps as number
    if (data.step !== undefined) st.step = data.step as number
    if (data.loss !== undefined) {
      const l = data.loss as number
      st.loss = l
      if (st.bestLoss === null || l < st.bestLoss) st.bestLoss = l
    }
    if (data.learning_rate !== undefined) st.learningRate = data.learning_rate as number
    if (data.epoch !== undefined) st.epoch = data.epoch as number
    st.message = (data.message as string) || `Step ${st.step}/${st.totalSteps}`
  } else if (phase === 'eval') {
    st.phase = 'eval'
    if (data.metrics) st.evalMetrics = data.metrics as EvalMetrics
    st.message = 'Evaluating model quality...'
  } else if (phase === 'saving') {
    st.phase = 'saving'
    st.message = (data.message as string) || 'Saving LoRA adapter...'
    if (data.path) st.path = data.path as string
  } else if (phase === 'candidate_done') {
    st.phase = (data.skipped ? 'skipped' : 'done')
    st.message = data.skipped ? 'Skipped (no training data)' : 'DNA cloned successfully'
    if (data.path) st.path = data.path as string
  } else if (phase === 'error') {
    st.phase = 'error'
    st.error = (data.message as string) || 'Unknown error'
    st.message = st.error
  }
}

const allCandidatesDone = computed(() =>
  states.value.length > 0 &&
  states.value.every(s => ['done', 'error', 'skipped'].includes(s.phase))
)

// ── Helpers ───────────────────────────────────────────────────────────────────

function phaseLabel(phase: CandidateState['phase']): string {
  const map: Record<string, string> = {
    waiting:    'Queued',
    collecting: 'Collecting code',
    generating: 'Generating pairs',
    training:   'Training LoRA',
    eval:       'Evaluating',
    saving:     'Saving adapter',
    done:       'DNA Cloned',
    error:      'Error',
    skipped:    'Skipped',
  }
  return map[phase] ?? phase
}

function progressPct(st: CandidateState): number {
  if (st.totalSteps === 0) return 0
  return Math.min(100, Math.round((st.step / st.totalSteps) * 100))
}

function roleColor(role: string): string {
  return ROLE_COLOR[role] ?? 'slate'
}

onMounted(() => {
  buildInitialStates()
  startStream()
})
onUnmounted(() => es?.close())
</script>

<template>
  <div class="fixed inset-0 z-50 flex flex-col bg-slate-950 overflow-hidden">

    <!-- ── Header ─────────────────────────────────────────────────────────── -->
    <div class="flex-shrink-0 flex items-center justify-between px-8 py-5 border-b border-slate-800">
      <div class="flex items-center gap-4">
        <span class="text-lg font-bold text-white tracking-tight">Clone.dna</span>
        <span class="text-slate-600">|</span>
        <span v-if="!overallDone && !allCandidatesDone" class="text-slate-300 text-sm font-medium flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
          Cloning DNA<span class="dots-anim"></span>
        </span>
        <span v-else class="text-green-400 text-sm font-semibold flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-green-400"></span>
          DNA Cloned
        </span>
      </div>

      <div class="flex items-center gap-4">
        <span v-if="streamError" class="text-xs text-red-400">{{ streamError }}</span>
        <span class="text-xs text-slate-600">
          {{ states.filter(s => s.phase === 'done').length }}/{{ states.length }} complete
        </span>
      </div>
    </div>

    <!-- ── Candidate cards grid ───────────────────────────────────────────── -->
    <div class="flex-1 overflow-y-auto p-6">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-5xl mx-auto">
        <div
          v-for="st in states"
          :key="st.candidate.github_handle"
          class="border bg-slate-900/60 p-5 flex flex-col gap-4 transition-colors"
          :class="{
            'border-green-700/60': st.phase === 'done',
            'border-red-700/60': st.phase === 'error',
            'border-slate-700/40': st.phase === 'waiting' || st.phase === 'skipped',
            'border-blue-700/60': st.phase === 'training',
            'border-cyan-700/60': st.phase === 'eval',
            'border-amber-700/40': st.phase === 'collecting' || st.phase === 'generating',
            'border-purple-700/40': st.phase === 'saving',
          }"
        >
          <!-- Candidate identity -->
          <div class="flex items-center gap-3">
            <img
              v-if="st.candidate.avatar_url"
              :src="st.candidate.avatar_url"
              :alt="st.candidate.name"
              class="w-10 h-10 object-cover flex-shrink-0 border border-slate-700"
              :class="st.phase === 'done' ? 'grayscale-0' : 'grayscale'"
            />
            <div
              v-else
              class="w-10 h-10 flex-shrink-0 bg-slate-800 border border-slate-700 flex items-center justify-center text-sm font-bold text-slate-400"
            >
              {{ (st.candidate.name ?? '?')[0]?.toUpperCase() }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <p class="text-sm font-semibold text-white truncate">
                  {{ st.candidate.name || st.candidate.github_handle }}
                </p>
                <span
                  class="text-xs font-bold px-1.5 py-0.5 border flex-shrink-0"
                  :class="{
                    'border-amber-700 text-amber-400': st.role === 'pm',
                    'border-blue-700 text-blue-400': st.role === 'swe',
                    'border-purple-700 text-purple-400': st.role === 'designer',
                  }"
                >{{ ROLE_BADGE[st.role] ?? st.role.toUpperCase() }}</span>
              </div>
              <p class="text-xs text-slate-500 truncate">@{{ st.candidate.github_handle }}</p>
            </div>
            <!-- Phase badge -->
            <span
              class="text-xs font-medium px-2 py-1 border flex-shrink-0"
              :class="{
                'border-green-700 text-green-400 bg-green-950/30': st.phase === 'done',
                'border-red-700 text-red-400 bg-red-950/30': st.phase === 'error',
                'border-slate-700 text-slate-500': st.phase === 'waiting',
                'border-blue-700 text-blue-400 bg-blue-950/30 animate-pulse': st.phase === 'training',
                'border-cyan-700 text-cyan-400 bg-cyan-950/30': st.phase === 'eval',
                'border-amber-700/60 text-amber-400/80': st.phase === 'collecting' || st.phase === 'generating',
                'border-purple-700/60 text-purple-400/80': st.phase === 'saving',
                'border-slate-700 text-slate-600': st.phase === 'skipped',
              }"
            >{{ phaseLabel(st.phase) }}</span>
          </div>



          <!-- Status message -->
          <p class="text-xs text-slate-500 font-mono leading-relaxed min-h-[1.2rem]">
            {{ st.message }}
          </p>

          <!-- Training config panel -->
          <div v-if="st.trainingConfig" class="bg-slate-950/60 border border-slate-800 px-3 py-2">
            <div class="grid grid-cols-4 gap-x-4 gap-y-1 text-xs font-mono">
              <div><span class="text-slate-600">Epochs:</span> <span class="text-slate-300">{{ st.trainingConfig.epochs }}</span></div>
              <div><span class="text-slate-600">LR:</span> <span class="text-slate-300">{{ st.trainingConfig.learning_rate }}</span></div>
              <div><span class="text-slate-600">Batch:</span> <span class="text-slate-300">{{ st.trainingConfig.batch_size }}×{{ st.trainingConfig.gradient_accumulation_steps }}</span></div>
              <div><span class="text-slate-600">LoRA:</span> <span class="text-slate-300">r{{ st.trainingConfig.lora_rank }}/a{{ st.trainingConfig.lora_alpha }}</span></div>
            </div>
            <div class="text-xs font-mono text-slate-500 mt-1">
              Pairs: {{ st.trainingConfig.candidate_pairs }} candidate + {{ st.trainingConfig.base_instruct_pairs }} base + {{ st.trainingConfig.tool_use_pairs }} tool = {{ st.trainingConfig.total_pairs }} total
            </div>
          </div>

          <!-- Training progress -->
          <div v-if="st.phase === 'training' || st.phase === 'eval' || (st.phase !== 'waiting' && st.totalSteps > 0)">
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-xs text-slate-600">
                <template v-if="st.epoch !== null">Epoch {{ st.epoch }}/{{ st.trainingConfig?.epochs ?? 2 }} · </template>
                Step {{ st.step }}/{{ st.totalSteps }}
              </span>
              <div class="flex items-center gap-3">
                <span v-if="st.learningRate !== null" class="text-xs font-mono text-slate-500">
                  lr {{ st.learningRate.toExponential(1) }}
                </span>
                <span v-if="st.loss !== null" class="text-xs font-mono text-blue-400">
                  loss {{ st.loss.toFixed(4) }}
                </span>
                <span v-if="st.bestLoss !== null && st.loss !== st.bestLoss" class="text-xs font-mono text-green-400">
                  best {{ st.bestLoss.toFixed(4) }}
                </span>
              </div>
            </div>
            <div class="h-1 bg-slate-800 overflow-hidden">
              <div
                class="h-full transition-all duration-300 ease-out"
                :class="{
                  'bg-blue-500': st.phase === 'training',
                  'bg-green-500': st.phase === 'done',
                  'bg-red-500': st.phase === 'error',
                  'bg-cyan-500': st.phase === 'eval',
                  'bg-slate-600': st.phase === 'saving',
                }"
                :style="{ width: `${['done', 'eval', 'saving'].includes(st.phase) ? 100 : progressPct(st)}%` }"
              ></div>
            </div>
          </div>

          <!-- Collecting / generating progress placeholder -->
          <div v-else-if="['collecting', 'generating'].includes(st.phase)">
            <div class="h-1 bg-slate-800 overflow-hidden">
              <div class="h-full bg-amber-500/60 animate-indeterminate"></div>
            </div>
          </div>

          <!-- Eval metrics panel -->
          <div v-if="st.evalMetrics" class="bg-slate-950/60 border border-slate-800 px-3 py-2">
            <p class="text-xs text-slate-500 mb-1.5 font-medium">Evaluation Metrics</p>
            <div class="grid grid-cols-4 gap-x-4 gap-y-1.5 text-xs font-mono">
              <div class="flex flex-col">
                <span class="text-slate-600">Style</span>
                <div class="flex items-center gap-1.5">
                  <div class="flex-1 h-1 bg-slate-800 overflow-hidden">
                    <div class="h-full bg-cyan-500" :style="{ width: `${(st.evalMetrics.style_consistency ?? 0) * 100}%` }"></div>
                  </div>
                  <span class="text-cyan-400 w-8 text-right">{{ ((st.evalMetrics.style_consistency ?? 0) * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="flex flex-col">
                <span class="text-slate-600">Domain</span>
                <div class="flex items-center gap-1.5">
                  <div class="flex-1 h-1 bg-slate-800 overflow-hidden">
                    <div class="h-full bg-green-500" :style="{ width: `${(st.evalMetrics.domain_accuracy ?? 0) * 100}%` }"></div>
                  </div>
                  <span class="text-green-400 w-8 text-right">{{ ((st.evalMetrics.domain_accuracy ?? 0) * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="flex flex-col">
                <span class="text-slate-600">HumanEval</span>
                <div class="flex items-center gap-1.5">
                  <div class="flex-1 h-1 bg-slate-800 overflow-hidden">
                    <div class="h-full bg-amber-500" :style="{ width: `${(st.evalMetrics.humaneval_score ?? 0) * 100}%` }"></div>
                  </div>
                  <span class="text-amber-400 w-8 text-right">{{ ((st.evalMetrics.humaneval_score ?? 0) * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="flex flex-col">
                <span class="text-slate-600">Latency</span>
                <span class="text-slate-300">+{{ st.evalMetrics.latency_overhead_ms }}ms</span>
              </div>
            </div>
          </div>

          <!-- Pairs count (only if no training config panel) -->
          <div v-if="st.pairsCount > 0 && !st.trainingConfig" class="flex items-center gap-2">
            <span class="text-xs text-slate-600">Training pairs:</span>
            <span class="text-xs font-mono text-amber-400">{{ st.pairsCount }}</span>
          </div>

          <!-- Final path -->
          <div v-if="st.path" class="mt-1">
            <p class="text-xs text-slate-600 mb-1">Saved to:</p>
            <code class="text-xs text-green-400 font-mono bg-slate-950/60 border border-slate-800 px-2 py-1 block truncate">
              {{ st.path }}
            </code>
          </div>

          <!-- Error detail -->
          <div v-if="st.error" class="text-xs text-red-400 font-mono bg-red-950/20 border border-red-800/40 px-2 py-1">
            {{ st.error }}
          </div>
        </div>
      </div>
    </div>

    <!-- ── Footer ─────────────────────────────────────────────────────────── -->
    <Transition name="fade">
      <div
        v-if="allCandidatesDone || overallDone"
        class="flex-shrink-0 border-t border-slate-800 bg-slate-900/80 px-8 py-4 flex items-center justify-between"
      >
        <div class="text-sm">
          <span class="text-green-400 font-medium">
            {{ states.filter(s => s.phase === 'done').length }} DNA blocks saved
          </span>
          <span v-if="states.some(s => s.phase === 'error')" class="text-red-400 ml-3 text-xs">
            · {{ states.filter(s => s.phase === 'error').length }} failed
          </span>
          <span v-if="states.some(s => s.phase === 'skipped')" class="text-slate-500 ml-3 text-xs">
            · {{ states.filter(s => s.phase === 'skipped').length }} skipped
          </span>
        </div>
        <button
          class="px-6 py-2 text-sm font-semibold bg-green-700 text-white hover:bg-green-600 transition-colors"
          @click="emit('done')"
        >
          View Team →
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
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

@keyframes indeterminate {
  0%   { transform: translateX(-100%); width: 40%; }
  50%  { width: 60%; }
  100% { transform: translateX(250%); width: 40%; }
}
.animate-indeterminate {
  animation: indeterminate 1.5s ease-in-out infinite;
}
</style>
