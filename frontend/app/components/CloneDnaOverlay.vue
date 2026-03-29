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
  <Teleport to="body">
  <div class="fixed inset-0 z-[200] flex flex-col bg-parchment overflow-hidden">

    <!-- ── Header ─────────────────────────────────────────────────────────── -->
    <div class="flex-shrink-0 flex items-center justify-between px-8 py-5 border-b border-border bg-card">
      <div class="flex items-center gap-4">
        <span class="text-[17px] font-bold text-ink tracking-tight">Clone.dna</span>
        <span class="text-mid">|</span>
        <span v-if="!overallDone && !allCandidatesDone" class="text-stone text-sm font-medium flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-forest-mid animate-pulse"></span>
          Cloning DNA<span class="dots-anim"></span>
        </span>
        <span v-else class="text-forest text-sm font-semibold flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-forest"></span>
          DNA Cloned
        </span>
      </div>

      <div class="flex items-center gap-4">
        <span v-if="streamError" class="text-xs text-danger">{{ streamError }}</span>
        <span class="font-mono text-xs text-muted">
          {{ states.filter(s => s.phase === 'done').length }}/{{ states.length }} complete
        </span>
      </div>
    </div>

    <!-- ── Candidate cards grid ───────────────────────────────────────────── -->
    <div class="flex-1 overflow-y-auto p-6 bg-parchment">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-5xl mx-auto">
        <div
          v-for="st in states"
          :key="st.candidate.github_handle"
          class="border bg-card p-5 flex flex-col gap-4 rounded transition-colors shadow-soft"
          :class="{
            'border-forest/50': st.phase === 'done',
            'border-danger/50': st.phase === 'error',
            'border-border': st.phase === 'waiting' || st.phase === 'skipped',
            'border-blue-400/60': st.phase === 'training',
            'border-cyan-400/60': st.phase === 'eval',
            'border-amber-warm/40': st.phase === 'collecting' || st.phase === 'generating',
            'border-mid': st.phase === 'saving',
          }"
        >
          <!-- Candidate identity -->
          <div class="flex items-center gap-3">
            <img
              v-if="st.candidate.avatar_url"
              :src="st.candidate.avatar_url"
              :alt="st.candidate.name"
              class="w-10 h-10 object-cover flex-shrink-0 border border-border rounded"
              :class="st.phase === 'done' ? '' : 'grayscale opacity-60'"
            />
            <div
              v-else
              class="w-10 h-10 flex-shrink-0 bg-subtle border border-border rounded flex items-center justify-center text-sm font-bold text-muted"
            >
              {{ (st.candidate.name ?? '?')[0]?.toUpperCase() }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <p class="text-sm font-semibold text-ink truncate">
                  {{ st.candidate.name || st.candidate.github_handle }}
                </p>
                <span
                  class="font-mono text-[10px] font-bold px-1.5 py-0.5 border rounded flex-shrink-0"
                  :class="{
                    'border-amber-warm/60 text-amber-warm bg-amber-light': st.role === 'pm',
                    'border-blue-400 text-blue-700 bg-blue-50': st.role === 'swe',
                    'border-purple-400 text-purple-700 bg-purple-50': st.role === 'designer',
                  }"
                >{{ ROLE_BADGE[st.role] ?? st.role.toUpperCase() }}</span>
              </div>
              <p class="font-mono text-xs text-muted truncate">@{{ st.candidate.github_handle }}</p>
            </div>
            <!-- Phase badge -->
            <span
              class="font-mono text-[10px] font-medium px-2 py-1 border rounded flex-shrink-0"
              :class="{
                'border-forest/50 text-forest-text bg-forest-light': st.phase === 'done',
                'border-danger/50 text-danger bg-danger-light': st.phase === 'error',
                'border-border text-muted bg-subtle': st.phase === 'waiting',
                'border-blue-400/60 text-blue-700 bg-blue-50 animate-pulse': st.phase === 'training',
                'border-cyan-400/60 text-cyan-700 bg-cyan-50': st.phase === 'eval',
                'border-amber-warm/40 text-amber-warm bg-amber-light': st.phase === 'collecting' || st.phase === 'generating',
                'border-mid text-stone bg-subtle': st.phase === 'saving',
                'border-border text-muted': st.phase === 'skipped',
              }"
            >{{ phaseLabel(st.phase) }}</span>
          </div>

          <!-- Status message -->
          <p class="text-xs text-muted font-mono leading-relaxed min-h-[1.2rem]">
            {{ st.message }}
          </p>

          <!-- Training config panel -->
          <div v-if="st.trainingConfig" class="bg-subtle border border-border rounded px-3 py-2">
            <div class="grid grid-cols-4 gap-x-4 gap-y-1 text-xs font-mono">
              <div><span class="text-muted">Epochs:</span> <span class="text-ink">{{ st.trainingConfig.epochs }}</span></div>
              <div><span class="text-muted">LR:</span> <span class="text-ink">{{ st.trainingConfig.learning_rate }}</span></div>
              <div><span class="text-muted">Batch:</span> <span class="text-ink">{{ st.trainingConfig.batch_size }}×{{ st.trainingConfig.gradient_accumulation_steps }}</span></div>
              <div><span class="text-muted">LoRA:</span> <span class="text-ink">r{{ st.trainingConfig.lora_rank }}/a{{ st.trainingConfig.lora_alpha }}</span></div>
            </div>
            <div class="text-xs font-mono text-muted mt-1">
              Pairs: {{ st.trainingConfig.candidate_pairs }} candidate + {{ st.trainingConfig.base_instruct_pairs }} base + {{ st.trainingConfig.tool_use_pairs }} tool = {{ st.trainingConfig.total_pairs }} total
            </div>
          </div>

          <!-- Training progress -->
          <div v-if="st.phase === 'training' || st.phase === 'eval' || (st.phase !== 'waiting' && st.totalSteps > 0)">
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-xs text-muted font-mono">
                <template v-if="st.epoch !== null">Epoch {{ st.epoch }}/{{ st.trainingConfig?.epochs ?? 2 }} · </template>
                Step {{ st.step }}/{{ st.totalSteps }}
              </span>
              <div class="flex items-center gap-3">
                <span v-if="st.learningRate !== null" class="text-xs font-mono text-muted">
                  lr {{ st.learningRate.toExponential(1) }}
                </span>
                <span v-if="st.loss !== null" class="text-xs font-mono text-blue-600">
                  loss {{ st.loss.toFixed(4) }}
                </span>
                <span v-if="st.bestLoss !== null && st.loss !== st.bestLoss" class="text-xs font-mono text-forest">
                  best {{ st.bestLoss.toFixed(4) }}
                </span>
              </div>
            </div>
            <div class="h-1 bg-subtle rounded-full overflow-hidden">
              <div
                class="h-full transition-all duration-300 ease-out rounded-full"
                :class="{
                  'bg-blue-500': st.phase === 'training',
                  'bg-forest': st.phase === 'done',
                  'bg-danger': st.phase === 'error',
                  'bg-cyan-500': st.phase === 'eval',
                  'bg-mid': st.phase === 'saving',
                }"
                :style="{ width: `${['done', 'eval', 'saving'].includes(st.phase) ? 100 : progressPct(st)}%` }"
              ></div>
            </div>
          </div>

          <!-- Collecting / generating progress placeholder -->
          <div v-else-if="['collecting', 'generating'].includes(st.phase)">
            <div class="h-1 bg-subtle rounded-full overflow-hidden">
              <div class="h-full bg-amber-warm/50 rounded-full animate-indeterminate"></div>
            </div>
          </div>

          <!-- Eval metrics panel -->
          <div v-if="st.evalMetrics" class="bg-subtle border border-border rounded px-3 py-2">
            <p class="text-xs text-muted mb-1.5 font-semibold uppercase tracking-wider">Evaluation Metrics</p>
            <div class="grid grid-cols-4 gap-x-4 gap-y-1.5 text-xs font-mono">
              <div class="flex flex-col">
                <span class="text-muted">Style</span>
                <div class="flex items-center gap-1.5">
                  <div class="flex-1 h-1 bg-hover rounded-full overflow-hidden">
                    <div class="h-full bg-cyan-500 rounded-full" :style="{ width: `${(st.evalMetrics.style_consistency ?? 0) * 100}%` }"></div>
                  </div>
                  <span class="text-cyan-700 w-8 text-right">{{ ((st.evalMetrics.style_consistency ?? 0) * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="flex flex-col">
                <span class="text-muted">Domain</span>
                <div class="flex items-center gap-1.5">
                  <div class="flex-1 h-1 bg-hover rounded-full overflow-hidden">
                    <div class="h-full bg-forest rounded-full" :style="{ width: `${(st.evalMetrics.domain_accuracy ?? 0) * 100}%` }"></div>
                  </div>
                  <span class="text-forest w-8 text-right">{{ ((st.evalMetrics.domain_accuracy ?? 0) * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="flex flex-col">
                <span class="text-muted">HumanEval</span>
                <div class="flex items-center gap-1.5">
                  <div class="flex-1 h-1 bg-hover rounded-full overflow-hidden">
                    <div class="h-full bg-amber-warm/70 rounded-full" :style="{ width: `${(st.evalMetrics.humaneval_score ?? 0) * 100}%` }"></div>
                  </div>
                  <span class="text-amber-warm w-8 text-right">{{ ((st.evalMetrics.humaneval_score ?? 0) * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="flex flex-col">
                <span class="text-muted">Latency</span>
                <span class="text-ink">+{{ st.evalMetrics.latency_overhead_ms }}ms</span>
              </div>
            </div>
          </div>

          <!-- Pairs count (only if no training config panel) -->
          <div v-if="st.pairsCount > 0 && !st.trainingConfig" class="flex items-center gap-2">
            <span class="text-xs text-muted">Training pairs:</span>
            <span class="text-xs font-mono text-amber-warm">{{ st.pairsCount }}</span>
          </div>

          <!-- Final path -->
          <div v-if="st.path" class="mt-1">
            <p class="text-xs text-muted mb-1">Saved to:</p>
            <code class="text-xs text-forest-text font-mono bg-forest-light border border-forest/20 px-2 py-1 block truncate rounded">
              {{ st.path }}
            </code>
          </div>

          <!-- Error detail -->
          <div v-if="st.error" class="text-xs text-danger font-mono bg-danger-light border border-danger/30 px-2 py-1 rounded">
            {{ st.error }}
          </div>
        </div>
      </div>
    </div>

    <!-- ── Footer ─────────────────────────────────────────────────────────── -->
    <Transition name="fade">
      <div
        v-if="allCandidatesDone || overallDone"
        class="flex-shrink-0 border-t border-border bg-card px-8 py-4 flex items-center justify-between"
      >
        <div class="text-sm">
          <span class="text-forest font-medium">
            {{ states.filter(s => s.phase === 'done').length }} DNA blocks saved
          </span>
          <span v-if="states.some(s => s.phase === 'error')" class="text-danger ml-3 text-xs">
            · {{ states.filter(s => s.phase === 'error').length }} failed
          </span>
          <span v-if="states.some(s => s.phase === 'skipped')" class="text-muted ml-3 text-xs">
            · {{ states.filter(s => s.phase === 'skipped').length }} skipped
          </span>
        </div>
        <button
          class="btn btn-primary px-6 py-2 text-sm"
          @click="emit('done')"
        >
          View Team →
        </button>
      </div>
    </Transition>
  </div>
  </Teleport>
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
