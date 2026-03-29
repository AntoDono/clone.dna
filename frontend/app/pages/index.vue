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
const username = ref('')

function logout() {
  api.logout()
  router.push('/login')
}

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
    createError.value = 'Failed — is the backend running on :8000?'
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
  { num: '02', label: 'Extract', desc: 'AI reads their public code and generates training pairs.' },
  { num: '03', label: 'Train', desc: 'QLoRA fine-tunes a LoRA adapter encoding their style.' },
  { num: '04', label: 'Deploy', desc: 'Chat with the clone or orchestrate a full AI team.' },
]

onMounted(() => {
  username.value = api.getUsername() ?? ''
  fetchTeams()
})
</script>

<template>
  <div class="page-root">

    <!-- Sticky header -->
    <header class="page-header">
      <div class="header-left">
        <span class="logo font-display">Clone.dna</span>
        <span class="header-sep" aria-hidden="true">/</span>
        <span class="header-page">Workspace</span>
      </div>
      <nav class="header-right">
        <span v-if="username" class="header-username font-mono">{{ username }}</span>
        <NuxtLink to="/registry" class="nav-link">Registry</NuxtLink>
        <NuxtLink to="/developer" class="nav-link">Developer Portal</NuxtLink>
        <button class="btn btn-ghost btn-sm" @click="logout">Sign out</button>
      </nav>
    </header>

    <!-- Hero -->
    <section class="hero">
      <div class="hero-inner">
        <div class="hero-badge font-mono">LoRA · QLoRA · PEFT hot-swap</div>
        <h1 class="hero-headline font-display">
          Hire the Mind.<br /><em>Not the Body.</em>
        </h1>
        <p class="hero-body">
          Clone.dna mints a portable <strong>.dna block</strong> from a developer's public GitHub work —
          a LoRA adapter encoding their coding style, architecture instincts, and domain vocabulary.
          Evaluate real thinking before scheduling a single interview.
        </p>
        <div class="hero-actions">
          <button class="btn btn-primary" @click="openModal">+ Build a Team</button>
          <NuxtLink to="/registry" class="btn btn-secondary">Browse Registry</NuxtLink>
        </div>
      </div>

      <!-- Pipeline strip (Build-style outline: --border on --bg-card) -->
      <div class="pipeline border border-[var(--border)] bg-[var(--bg-card)] rounded shadow-sm">
        <div v-for="(step, i) in steps" :key="step.label" class="pipeline-step">
          <div class="step-num font-mono">{{ step.num }}</div>
          <div class="step-body">
            <p class="step-label">{{ step.label }}</p>
            <p class="step-desc">{{ step.desc }}</p>
          </div>
          <div v-if="i < steps.length - 1" class="step-arrow" aria-hidden="true">→</div>
        </div>
      </div>
    </section>

    <hr class="divider" />

    <!-- Teams section -->
    <main class="teams-section">
      <div class="section-header">
        <div>
          <h2 class="section-title">Your Teams</h2>
          <p class="section-sub">Each team: 1 PM · 2 SWE · 1 Designer</p>
        </div>
        <button class="btn btn-primary" @click="openModal">+ New Team</button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="state-loading">
        <span class="streaming-dot"></span>
        <span>Loading teams…</span>
      </div>

      <!-- Empty -->
      <div v-else-if="!teams.length" class="state-empty animate-in">
        <div class="empty-icon">⬡</div>
        <p class="empty-title">No teams yet</p>
        <p class="empty-desc">Build your first AI team to start cloning developer DNA.</p>
        <button class="btn btn-primary" @click="openModal">Build First Team</button>
      </div>

      <!-- Teams grid: subtle tray like Build sidebar -->
      <div
        v-else
        class="teams-board rounded border border-[var(--border)] bg-[var(--bg-subtle)] p-3 shadow-sm"
      >
        <div class="teams-grid stagger">
          <NuxtLink
            v-for="team in teams"
            :key="team.id"
            :to="`/teams/${team.id}`"
            class="team-card animate-in border border-[var(--border)] bg-[var(--bg-card)] rounded shadow-sm transition-all hover:border-[var(--border-mid)] hover:shadow-md"
          >
          <div class="team-card-header">
            <div>
              <span class="team-id font-mono">#{{ team.id }}</span>
              <h2 class="team-name">{{ team.name }}</h2>
            </div>
            <span
              class="pill"
              :class="filledCount(team) === 4 ? 'pill-green' : filledCount(team) > 0 ? 'pill-amber' : ''"
            >
              {{ filledCount(team) }}/4 filled
            </span>
          </div>

          <div class="team-slots">
            <span
              v-for="slot in team.slots"
              :key="slot.id"
              class="pill"
              :class="slot.filled ? 'pill-green' : ''"
            >
              {{ ROLE_LABEL[slot.role] }}{{ slot.slot_index > 0 ? ` ${slot.slot_index + 1}` : '' }}
            </span>
          </div>

          <div class="team-card-footer">
            <span class="team-date">
              {{ new Date(team.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }}
            </span>
            <span class="team-open">Open →</span>
          </div>
          </NuxtLink>
        </div>
      </div>
    </main>

    <!-- Create Team Modal -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
          <div class="modal-box card animate-in">
            <div class="modal-header">
              <h2 class="font-display modal-title">New Team</h2>
              <button class="btn btn-ghost" style="font-size:18px; padding:4px 8px;" @click="showModal = false">×</button>
            </div>
            <p class="modal-desc">Creates 4 role slots automatically — 1 PM, 2 SWE, 1 Designer.</p>

            <div class="field-group" style="margin-top:20px;">
              <label class="field-label">Team Name</label>
              <input
                id="new-team-input"
                v-model="newTeamName"
                type="text"
                placeholder="e.g. Alpha Squad"
                class="input"
                @keydown.enter="initTeam"
                @keydown.esc="showModal = false"
              />
              <p v-if="createError" class="error-callout" style="margin-top:8px;">{{ createError }}</p>
            </div>

            <div class="modal-actions">
              <button class="btn btn-secondary" @click="showModal = false">Cancel</button>
              <button
                class="btn btn-primary"
                :disabled="!newTeamName.trim() || creating"
                @click="initTeam"
              >
                <span v-if="creating" class="streaming-dot"></span>
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
.page-root { min-height: 100vh; background: var(--bg); }

/* Header */
.logo {
  font-size: 18px;
  font-weight: 400;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  padding: 6px 12px;
  border-radius: var(--radius);
}
.header-sep {
  color: var(--border-mid);
  margin: 0;
  font-size: 16px;
  padding: 6px 6px;
}
.header-page {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 400;
  padding: 6px 12px;
}
.header-left { display: flex; align-items: center; gap: 24px; }
.header-right { display: flex; align-items: center; gap: 18px; }
.header-username {
  font-size: 11px;
  color: var(--text-muted);
  padding: 6px 12px;
  background: var(--bg-subtle);
  border-radius: 20px;
  border: 1px solid var(--border);
  margin-right: 4px;
}

/* Hero */
.hero {
  max-width: 900px;
  margin: 0 auto;
  padding: 72px 32px 56px;
}
.hero-inner { max-width: 600px; }
.hero-badge {
  display: inline-block;
  font-size: 11px;
  color: var(--accent-text);
  background: var(--accent-light);
  border: 1px solid #86EFAC;
  border-radius: 2px;
  padding: 3px 10px;
  margin-bottom: 24px;
  letter-spacing: 0.04em;
}
.hero-headline {
  font-size: 52px;
  line-height: 1.08;
  letter-spacing: -0.03em;
  color: var(--text-primary);
  margin-bottom: 20px;
  font-weight: 400;
}
.hero-headline em { color: var(--accent); font-style: italic; }
.hero-body {
  font-size: 16px;
  line-height: 1.65;
  color: var(--text-secondary);
  margin-bottom: 32px;
  max-width: 520px;
}
.hero-body strong { color: var(--text-primary); font-weight: 600; }
.hero-actions { display: flex; gap: 12px; flex-wrap: wrap; }

/* Pipeline (edge tokens match Build: --border) */
.pipeline {
  display: flex;
  align-items: flex-start;
  gap: 0;
  margin-top: 56px;
  overflow: hidden;
}
.pipeline-step {
  flex: 1;
  padding: 20px 20px 20px 24px;
  border-right: 1px solid var(--border);
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pipeline-step:last-child { border-right: none; }
.step-num {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
  letter-spacing: 0.05em;
}
.step-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.step-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.step-arrow {
  position: absolute;
  right: -10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--border-mid);
  font-size: 16px;
  z-index: 1;
}

/* Teams section */
.teams-section {
  max-width: 900px;
  margin: 0 auto;
  padding: 40px 32px 80px;
}
.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
  gap: 16px;
}
.section-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.section-sub { font-size: 13px; color: var(--text-muted); margin-top: 2px; }

.state-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-muted);
  font-size: 14px;
  padding: 32px 0;
}
.state-empty {
  border: 1px dashed var(--border);
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 64px 32px;
  text-align: center;
}
.empty-icon { font-size: 32px; margin-bottom: 16px; opacity: 0.3; }
.empty-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.empty-desc { font-size: 14px; color: var(--text-muted); margin-bottom: 24px; }

/* Team grid */
.teams-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.team-card {
  padding: 20px;
  text-decoration: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.team-card:hover {
  transform: translateY(-1px);
}
.team-slots .pill:not(.pill-green):not(.pill-amber) {
  border-color: var(--border);
  background: var(--bg-card);
}
.team-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}
.team-id {
  font-size: 11px;
  color: var(--text-muted);
  display: block;
  margin-bottom: 3px;
}
.team-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  line-height: 1.3;
}
.team-card:hover .team-name { color: var(--accent); }
.team-slots { display: flex; flex-wrap: wrap; gap: 6px; }
.team-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
.team-date { font-size: 12px; color: var(--text-muted); }
.team-open {
  font-size: 12px;
  color: var(--text-muted);
  transition: color 0.15s;
}
.team-card:hover .team-open { color: var(--accent); }

/* Fields */
.field-group { display: flex; flex-direction: column; gap: 6px; }
.field-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-secondary);
}
.btn-sm { font-size: 13px; padding: 6px 12px; }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(28,24,17,0.35);
  backdrop-filter: blur(4px);
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.modal-box {
  width: 100%;
  max-width: 420px;
  padding: 28px;
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.modal-title { font-size: 22px; font-weight: 400; letter-spacing: -0.02em; }
.modal-desc { font-size: 13px; color: var(--text-muted); }
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 24px;
}
.error-callout {
  font-size: 13px;
  color: var(--red);
  background: var(--red-light);
  border: 1px solid #FECACA;
  border-radius: var(--radius);
  padding: 8px 12px;
}

/* Transitions */
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-active .modal-box { animation: fadeUp 0.2s ease both; }

@media (max-width: 640px) {
  .hero-headline { font-size: 36px; }
  .pipeline { flex-direction: column; }
  .pipeline-step { border-right: none; border-bottom: 1px solid var(--border); }
  .pipeline-step:last-child { border-bottom: none; }
  .step-arrow { display: none; }
}
</style>
