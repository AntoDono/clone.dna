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

onMounted(fetchTeams)
</script>

<template>
  <div class="min-h-screen bg-slate-950">

    <!-- Header -->
    <header class="bg-slate-900/80 border-b border-slate-800 px-6 py-4 flex items-center justify-between backdrop-blur">
      <div>
        <span class="text-xl font-bold text-white tracking-tight">Clone.dna</span>
        <span class="ml-2 text-sm text-slate-500 hidden sm:inline">Hire the Mind. Not the Body.</span>
      </div>
      <button
        class="border border-blue-500 text-blue-400 font-medium px-4 py-1.5 text-sm hover:bg-blue-600 hover:text-white transition-colors"
        @click="openModal"
      >
        + New Team
      </button>
    </header>

    <!-- Main -->
    <main class="max-w-4xl mx-auto px-6 py-10">
      <div class="mb-8">
        <h1 class="text-2xl font-semibold text-white">Your Teams</h1>
        <p class="text-slate-500 text-sm mt-1">Each team: 1 PM · 2 SWE · 1 Designer</p>
      </div>

      <!-- Loading -->
      <p v-if="loading" class="text-slate-500 text-sm">Loading...</p>

      <!-- Empty -->
      <div v-else-if="!teams.length" class="border border-dashed border-slate-700 bg-slate-900/40 p-16 text-center">
        <p class="text-slate-500 mb-4">No teams yet.</p>
        <button
          class="border border-blue-500 text-blue-400 font-medium px-6 py-2 hover:bg-blue-600 hover:text-white transition-colors"
          @click="openModal"
        >
          Create First Team
        </button>
      </div>

      <!-- Teams grid -->
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <NuxtLink
          v-for="team in teams"
          :key="team.id"
          :to="`/teams/${team.id}`"
          class="block bg-slate-900/60 border border-slate-800 hover:border-slate-600 transition-colors p-5 group"
        >
          <div class="flex items-start justify-between mb-3">
            <div>
              <p class="text-xs text-slate-500 mb-0.5">Team #{{ team.id }}</p>
              <h2 class="font-semibold text-white group-hover:text-blue-400 transition-colors">
                {{ team.name }}
              </h2>
            </div>
            <span
              class="text-xs font-medium border px-2 py-0.5"
              :class="filledCount(team) === 4
                ? 'border-green-600 text-green-400 bg-green-950/50'
                : 'border-slate-700 text-slate-500'"
            >
              {{ filledCount(team) }}/4
            </span>
          </div>

          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="slot in team.slots"
              :key="slot.id"
              class="text-xs px-2 py-0.5 border"
              :class="slot.filled
                ? 'border-green-600 text-green-400 bg-green-950/50'
                : 'border-slate-700 text-slate-600'"
            >
              {{ ROLE_LABEL[slot.role] }}{{ slot.slot_index > 0 ? ` #${slot.slot_index + 1}` : '' }}
            </span>
          </div>

          <p class="text-xs text-slate-500 mt-3">
            {{ new Date(team.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }}
          </p>
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
