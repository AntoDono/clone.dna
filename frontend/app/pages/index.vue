<script setup lang="ts">
import type { Team } from '~/composables/useApi'

const api = useApi()
const router = useRouter()

const teams = ref<Team[]>([])
const loading = ref(true)
const showModal = ref(false)
const newTeamName = ref('')
const creating = ref(false)
const createError = ref('')

async function fetchTeams() {
  loading.value = true
  try { teams.value = await api.getTeams() }
  catch { teams.value = [] }
  finally { loading.value = false }
}

async function initTeam() {
  const name = newTeamName.value.trim()
  if (!name) return
  creating.value = true
  createError.value = ''
  try {
    const team = await api.createTeam(name)
    router.push(`/teams/${team.id}?headhunt=true`)
  } catch {
    createError.value = 'Failed — is the backend running?'
    creating.value = false
  }
}

function openModal() {
  newTeamName.value = ''
  createError.value = ''
  showModal.value = true
  nextTick(() => document.getElementById('new-team-input')?.focus())
}

function filledCount(team: Team) {
  return team.slots.filter(s => s.filled).length
}

const ROLE_LABEL: Record<string, string> = { pm: 'PM', swe: 'SWE', designer: 'Design' }

const steps = [
  { num: '01', label: 'Headhunt', desc: 'AI scans GitHub for candidates matching each role.' },
  { num: '02', label: 'Extract',  desc: 'Grok-4 reads their public code and generates training pairs.' },
  { num: '03', label: 'Train',    desc: 'QLoRA fine-tunes a LoRA adapter encoding their style.' },
  { num: '04', label: 'Deploy',   desc: 'Chat with the clone or orchestrate a full AI team.' },
]

onMounted(() => {
  fetchTeams()
})
</script>

<template>
  <div class="bg-[var(--bg)]">

    <!-- ── Hero ───────────────────────────────────────────────── -->
    <section class="max-w-5xl mx-auto px-6 pt-16 pb-12 lg:pt-20 lg:pb-16">
      <div class="flex flex-col lg:flex-row lg:items-center gap-12 lg:gap-16">

        <!-- Left: copy -->
        <div class="flex-1 min-w-0 animate-in">

          <!-- Badge -->
          <div class="inline-flex items-center gap-2 mb-6">
            <span class="w-1.5 h-1.5 rounded-full" style="background-color:#15803D;"></span>
            <span
              class="font-mono text-[11px] rounded-[2px] px-2.5 py-0.5 tracking-wide"
              style="color:#14532D; background:#DCFCE7; border:1px solid #86EFAC;"
            >
              Grok-4 · QLoRA · PEFT hot-swap
            </span>
          </div>

          <h1 class="font-display text-[52px] lg:text-[60px] leading-[1.06] tracking-tightest text-ink mb-5">
            Hire the Mind.<br />
            <em class="text-forest not-italic border-b-[3px] border-forest/40">Not the Body.</em>
          </h1>

          <p class="text-[16px] leading-relaxed text-stone mb-8 max-w-[480px]">
            Clone.dna mints a portable <strong class="text-ink font-semibold">.dna block</strong>
            from a developer's public GitHub — a LoRA adapter encoding their coding style,
            architecture instincts, and domain vocabulary. Evaluate real thinking before
            scheduling a single interview.
          </p>

          <div class="flex flex-wrap items-center gap-3">
            <button class="btn btn-primary px-5 py-2.5 text-[13px]" @click="openModal">
              + Build a Team
            </button>
            <NuxtLink
              to="/registry"
              class="btn btn-secondary px-5 py-2.5 text-[13px]"
            >
              Browse Registry →
            </NuxtLink>
          </div>
        </div>

        <!-- Right: visual accent block -->
        <div class="hidden lg:flex items-center justify-center w-[320px] shrink-0 animate-in" style="animation-delay:100ms">
          <div class="relative w-full">
            <!-- Background card -->
            <div class="rounded bg-card border border-border shadow-card p-6 space-y-3">
              <div class="flex items-center gap-2 mb-4">
                <div class="w-2 h-2 rounded-full" style="background-color:#15803D;"></div>
                <span class="font-mono text-[11px] font-semibold tracking-wide" style="color:#14532D;">LIVE .dna BLOCK</span>
              </div>
              <div v-for="(item, i) in [
                { label: 'Handle',  value: '@danroth27',       mono: true  },
                { label: 'Role',    value: 'Senior SWE',       mono: false },
                { label: 'Style',   value: '94%',              mono: true  },
                { label: 'Domain',  value: '87%',              mono: true  },
                { label: 'Loss',    value: '0.312',            mono: true  },
                { label: 'Pairs',   value: '847 training',     mono: false },
              ]" :key="i" class="flex justify-between items-center py-1.5 border-b border-border last:border-0">
                <span class="text-[11px] text-muted uppercase tracking-wide">{{ item.label }}</span>
                <span :class="['text-[13px] font-medium text-ink', item.mono ? 'font-mono' : '']">{{ item.value }}</span>
              </div>
              <div class="pt-3">
                <div class="flex items-center gap-2 mb-1.5">
                  <span class="text-[10px] text-muted uppercase tracking-wide">Adapter quality</span>
                </div>
                <div class="h-1.5 bg-subtle rounded-full overflow-hidden">
                  <div class="rounded-full" style="height:100%; width:94%; background-color:#15803D; transition: width 1s ease-out;"></div>
                </div>
              </div>
            </div>
            <!-- Decorative offset border -->
            <div class="absolute -bottom-2 -right-2 w-full h-full rounded border border-forest/20 -z-10"></div>
          </div>
        </div>
      </div>

      <!-- Pipeline strip -->
      <div class="mt-14 grid grid-cols-2 lg:grid-cols-4 border border-border rounded bg-card shadow-soft overflow-hidden animate-in" style="animation-delay:140ms">
        <div
          v-for="(step, i) in steps"
          :key="step.label"
          class="relative p-5 border-b lg:border-b-0 border-r border-border last:border-r-0 even:border-b-0 lg:even:border-b-0"
        >
          <div class="flex items-center gap-2 mb-2.5">
            <span class="font-mono text-[10px] font-semibold text-forest-mid">{{ step.num }}</span>
            <span class="text-[10px] text-border">——</span>
          </div>
          <p class="text-[13px] font-semibold text-ink mb-1">{{ step.label }}</p>
          <p class="text-[12px] text-stone leading-snug">{{ step.desc }}</p>
          <!-- Green left accent on first step -->
          <div v-if="i === 0" class="absolute left-0 top-0 bottom-0 w-[3px] rounded-l" style="background-color:#15803D;"></div>
        </div>
      </div>
    </section>

    <hr class="border-border max-w-5xl mx-auto" />

    <!-- ── Teams ───────────────────────────────────────────────── -->
    <main class="max-w-5xl mx-auto px-6 py-10 pb-20">

      <!-- Section header -->
      <div class="flex items-start justify-between mb-6 gap-4">
        <div>
          <h2 class="text-[18px] font-semibold text-ink tracking-tight">Your Teams</h2>
          <p class="text-[13px] text-muted mt-0.5">Each team: 1 PM · 2 SWE · 1 Designer</p>
        </div>
        <button class="btn btn-primary shrink-0 text-[13px]" @click="openModal">
          + New Team
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center gap-3 py-10 text-muted text-[14px]">
        <span class="streaming-dot"></span>
        Loading teams…
      </div>

      <!-- Empty state -->
      <div v-else-if="!teams.length" class="border border-dashed border-border bg-card rounded p-16 text-center animate-in">
        <div class="w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-4" style="background:#DCFCE7; border:1px solid #86EFAC;">
          <span class="font-display text-lg" style="color:#15803D;">⬡</span>
        </div>
        <p class="text-[15px] font-semibold text-ink mb-2">No teams yet</p>
        <p class="text-[13px] text-muted mb-6">Build your first AI team to start cloning developer DNA.</p>
        <button class="btn btn-primary px-5 py-2.5 text-[13px]" @click="openModal">
          + Build First Team
        </button>
      </div>

      <!-- Teams grid -->
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 stagger">
        <NuxtLink
          v-for="team in teams"
          :key="team.id"
          :to="`/teams/${team.id}`"
          class="group block bg-card border border-border rounded shadow-soft hover:border-mid hover:shadow-card hover:-translate-y-px transition-all duration-150 p-5 no-underline animate-in"
        >
          <!-- Card header -->
          <div class="flex items-start justify-between gap-2 mb-3">
            <div class="min-w-0">
              <span class="font-mono text-[11px] text-muted block mb-1">#{{ team.id }}</span>
              <h3 class="text-[15px] font-semibold text-ink leading-snug group-hover:text-forest transition-colors truncate">
                {{ team.name }}
              </h3>
            </div>
            <span
              class="shrink-0 font-mono text-[11px] px-2 py-0.5 rounded-[2px] border"
              :style="filledCount(team) === 4
                ? 'background:#DCFCE7; border-color:#86EFAC; color:#14532D;'
                : filledCount(team) > 0
                  ? 'background:#FEF3C7; border-color:#FDE68A; color:#92400E;'
                  : 'background:#F3F0EB; border-color:#E2DDD6; color:#A8A098;'"
            >
              {{ filledCount(team) }}/4
            </span>
          </div>

          <!-- Role pills -->
          <div class="flex flex-wrap gap-1.5 mb-4">
            <span
              v-for="slot in team.slots"
              :key="slot.id"
              class="font-mono text-[11px] px-2 py-0.5 rounded-[2px] border"
              :style="slot.filled
                ? 'background:#DCFCE7; border-color:#86EFAC; color:#14532D;'
                : 'background:#F3F0EB; border-color:#E2DDD6; color:#A8A098;'"
            >
              {{ ROLE_LABEL[slot.role] }}{{ slot.slot_index > 0 ? ` ${slot.slot_index + 1}` : '' }}
            </span>
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-between pt-3 border-t border-border">
            <span class="text-[12px] text-muted">
              {{ new Date(team.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }}
            </span>
            <span class="text-[12px] text-muted group-hover:text-forest transition-colors">Open →</span>
          </div>
        </NuxtLink>
      </div>
    </main>

    <!-- ── Create Team Modal ────────────────────────────────────── -->
    <Teleport to="body">
      <Transition name="modal">
        <div
          v-if="showModal"
          class="fixed inset-0 z-[200] flex items-center justify-center p-6 bg-ink/30 backdrop-blur-sm"
          @click.self="showModal = false"
        >
          <div class="w-full max-w-[400px] bg-card rounded border border-border shadow-card p-7 animate-in">
            <div class="flex items-center justify-between mb-1">
              <h2 class="font-display text-[22px] text-ink tracking-tighter">New Team</h2>
              <button
                class="text-muted hover:text-ink text-xl leading-none px-2 py-1 rounded hover:bg-subtle transition-colors"
                @click="showModal = false"
              >×</button>
            </div>
            <p class="text-[13px] text-muted mb-6">Creates 4 role slots — 1 PM, 2 SWE, 1 Designer.</p>

            <label class="block text-[11px] font-bold text-stone uppercase tracking-widest mb-1.5">
              Team Name
            </label>
            <input
              id="new-team-input"
              v-model="newTeamName"
              type="text"
              placeholder="e.g. Alpha Squad"
              class="w-full bg-card border border-border rounded text-[14px] text-ink placeholder-muted px-3.5 py-2.5 outline-none focus:border-forest focus:ring-2 focus:ring-forest/10 transition"
              @keydown.enter="initTeam"
              @keydown.esc="showModal = false"
            />
            <p v-if="createError" class="mt-2 text-[13px] text-danger bg-danger-light border border-[#FECACA] rounded px-3 py-2">
              {{ createError }}
            </p>

            <div class="flex justify-end gap-2.5 mt-6">
              <button class="btn btn-secondary text-[13px]" @click="showModal = false">
                Cancel
              </button>
              <button
                class="btn btn-primary text-[13px] px-5"
                :disabled="!newTeamName.trim() || creating"
                @click="initTeam"
              >
                <span v-if="creating" class="streaming-dot" style="background:white;"></span>
                {{ creating ? 'Creating…' : 'Create Team' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* Modal transition */
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-active > div { animation: fadeUp 0.2s ease both; }

/* Pipeline grid — 2 cols on mobile, 4 on lg */
@media (max-width: 1024px) {
  /* on 2×2 grid: remove right border on col 2, remove bottom border on row 2 */
  .pipeline-step:nth-child(2) { border-right: none; }
  .pipeline-step:nth-child(3),
  .pipeline-step:nth-child(4) { border-bottom: none; }
}
</style>
