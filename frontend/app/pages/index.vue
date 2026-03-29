<script setup lang="ts">
/**
 * Home page — list all teams and create new ones.
 * Teams display slot fill status. Creating a team redirects to the team page
 * with ?headhunt=true to auto-open the headhunt overlay.
 */
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
  { num: '01', label: 'Headhunt', desc: 'AI scans GitHub to find candidates matching each role.' },
  { num: '02', label: 'Extract', desc: 'Grok-4 reads their public code and generates training pairs.' },
  { num: '03', label: 'Train', desc: 'QLoRA fine-tunes a LoRA adapter encoding their style.' },
  { num: '04', label: 'Deploy', desc: 'Chat with the clone or orchestrate the full team.' },
]

onMounted(() => {
  username.value = api.getUsername() ?? ''
  fetchTeams()
})
</script>

<template>
  <div class="min-h-screen bg-slate-950">

    <!-- Header -->
    <header class="bg-slate-900/80 border-b border-slate-800 px-6 py-4 flex items-center justify-between backdrop-blur">
      <div>
        <span class="text-xl font-bold text-white tracking-tight">Clone.dna</span>
        <span class="ml-2 text-sm text-slate-500 hidden sm:inline">Hire the Mind. Not the Body.</span>
      </div>
      <div class="flex items-center gap-3">
        <span v-if="username" class="text-xs text-slate-500 hidden sm:inline">{{ username }}</span>
        <NuxtLink
          to="/registry"
          class="border border-slate-700 text-slate-400 font-medium px-4 py-1.5 text-sm hover:border-slate-500 hover:text-white transition-colors"
        >
          Registry
        </NuxtLink>
        <button
          class="border border-blue-500 text-blue-400 font-medium px-4 py-1.5 text-sm hover:bg-blue-600 hover:text-white transition-colors"
          @click="openModal"
        >
          + New Team
        </button>
        <button
          class="border border-slate-700 text-slate-500 font-medium px-4 py-1.5 text-sm hover:border-slate-500 hover:text-slate-300 transition-colors"
          @click="logout"
        >
          Sign out
        </button>
      </div>
    </header>

    <!-- Hero -->
    <section class="border-b border-slate-800/60 bg-gradient-to-b from-slate-900/60 to-transparent">
      <div class="max-w-4xl mx-auto px-6 py-14">
        <div class="max-w-2xl">
          <div class="flex items-center gap-2 mb-5">
            <span class="text-xs font-mono text-blue-400 border border-blue-800 bg-blue-950/40 px-2 py-0.5 tracking-wider">LoRA · PEFT · Grok-4</span>
            <span class="text-xs font-mono text-slate-500 border border-slate-800 px-2 py-0.5">v2.0 adapter format</span>
          </div>
          <h1 class="text-4xl font-bold text-white leading-tight mb-4">
            Hire the Mind.<br /><span class="text-blue-400">Not the Body.</span>
          </h1>
          <p class="text-slate-400 text-base leading-relaxed mb-8 max-w-xl">
            Clone.dna mints a portable <span class="text-white font-medium">.dna block</span> from a developer's public GitHub work —
            a LoRA adapter encoding their coding style, architecture patterns, and domain vocabulary.
            Evaluate a developer's actual thinking before scheduling a single interview.
          </p>
          <div class="flex items-center gap-3 flex-wrap">
            <button
              class="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-6 py-2.5 text-sm transition-colors"
              @click="openModal"
            >
              + Build a Team
            </button>
            <NuxtLink
              to="/registry"
              class="border border-slate-600 text-slate-300 font-medium px-6 py-2.5 text-sm hover:border-slate-400 hover:text-white transition-colors"
            >
              Browse Registry
            </NuxtLink>
            <NuxtLink
              to="/developer"
              class="text-slate-500 text-sm hover:text-slate-300 transition-colors px-2 py-2.5"
            >
              Developer Portal →
            </NuxtLink>
          </div>
        </div>

        <!-- How it works strip -->
        <div class="mt-12 grid grid-cols-4 gap-px bg-slate-800/60">
          <div v-for="step in steps" :key="step.label" class="bg-slate-950 px-5 py-5">
            <p class="text-xs text-slate-600 font-mono mb-1">{{ step.num }}</p>
            <p class="text-sm font-semibold text-slate-200 mb-1">{{ step.label }}</p>
            <p class="text-xs text-slate-500 leading-relaxed">{{ step.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Main -->
    <main class="max-w-4xl mx-auto px-6 py-10">
      <div class="flex items-center justify-between mb-6">
        <div>
          <h2 class="text-lg font-semibold text-white">Your Teams</h2>
          <p class="text-slate-500 text-xs mt-0.5">1 PM · 2 SWE · 1 Designer per team</p>
        </div>
        <button
          class="border border-blue-600 text-blue-400 font-medium px-4 py-1.5 text-sm hover:bg-blue-600 hover:text-white transition-colors"
          @click="openModal"
        >
          + New Team
        </button>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="flex items-center gap-2 text-slate-500 text-sm py-8">
        <span class="animate-pulse">●</span> Loading teams...
      </div>

      <!-- Empty -->
      <div v-else-if="!teams.length" class="border border-dashed border-slate-800 bg-slate-900/30 p-16 text-center">
        <p class="text-slate-400 font-medium mb-1">No teams yet</p>
        <p class="text-slate-600 text-sm mb-6">Build your first AI team to start cloning developers.</p>
        <button
          class="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-6 py-2.5 text-sm transition-colors"
          @click="openModal"
        >
          Build First Team
        </button>
      </div>

      <!-- Teams grid -->
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <NuxtLink
          v-for="team in teams"
          :key="team.id"
          :to="`/teams/${team.id}`"
          class="block bg-slate-900/50 border border-slate-800 hover:border-slate-600 hover:bg-slate-900/80 transition-all p-5 group"
        >
          <div class="flex items-start justify-between mb-4">
            <div>
              <p class="text-xs text-slate-600 font-mono mb-1">#{{ team.id }}</p>
              <h2 class="font-semibold text-white group-hover:text-blue-400 transition-colors text-base">
                {{ team.name }}
              </h2>
            </div>
            <span
              class="text-xs font-medium border px-2 py-0.5 mt-0.5"
              :class="filledCount(team) === 4
                ? 'border-green-600 text-green-400 bg-green-950/40'
                : filledCount(team) > 0
                  ? 'border-amber-700 text-amber-400 bg-amber-950/40'
                  : 'border-slate-700 text-slate-600'"
            >
              {{ filledCount(team) }}/4 filled
            </span>
          </div>

          <div class="flex flex-wrap gap-1.5 mb-4">
            <span
              v-for="slot in team.slots"
              :key="slot.id"
              class="text-xs px-2 py-0.5 border font-mono"
              :class="slot.filled
                ? 'border-green-700 text-green-400 bg-green-950/30'
                : 'border-slate-800 text-slate-600'"
            >
              {{ ROLE_LABEL[slot.role] }}{{ slot.slot_index > 0 ? ` ${slot.slot_index + 1}` : '' }}
            </span>
          </div>

          <div class="flex items-center justify-between text-xs text-slate-600">
            <span>{{ new Date(team.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) }}</span>
            <span class="group-hover:text-blue-400 transition-colors">Open →</span>
          </div>
        </NuxtLink>
      </div>
    </main>

    <!-- Modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-slate-950/70" @click="showModal = false"></div>
          <div class="relative z-10 bg-slate-900 border border-slate-700 w-full max-w-md p-7 shadow-2xl">
            <h2 class="font-semibold text-white text-lg mb-1">New Team</h2>
            <p class="text-slate-400 text-sm mb-5">Creates 4 role slots automatically (1 PM, 2 SWE, 1 Designer)</p>

            <label class="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">Team Name</label>
            <input
              id="new-team-input"
              v-model="newTeamName"
              type="text"
              placeholder="e.g. Alpha Squad"
              class="w-full border border-slate-700 focus:border-blue-500 bg-slate-800 text-white placeholder-slate-600 px-3 py-2 text-sm outline-none transition-colors mb-2"
              @keydown.enter="initTeam"
              @keydown.esc="showModal = false"
            />
            <p v-if="createError" class="text-xs text-red-400 mb-3">{{ createError }}</p>

            <div class="flex gap-3 mt-5">
              <button
                class="flex-1 border border-slate-700 text-slate-500 py-2 text-sm hover:border-slate-500 hover:text-slate-300 transition-colors"
                @click="showModal = false"
              >
                Cancel
              </button>
              <button
                class="flex-1 bg-blue-600 text-white py-2 text-sm font-medium hover:bg-blue-500 transition-colors disabled:opacity-40"
                :disabled="!newTeamName.trim() || creating"
                @click="initTeam"
              >
                {{ creating ? 'Creating...' : 'Create Team' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
