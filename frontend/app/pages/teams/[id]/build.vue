<script setup lang="ts">
/**
 * Build workspace page for a team.
 * Left sidebar lists all cloned candidates with role badges.
 * Main panel is ChatPanel — switches between DM threads and orchestration view.
 * Loads full message history on mount; defaults to the first cloned candidate's thread.
 * Compare overlay lets users see base-model vs adapter side-by-side for any cloned candidate.
 */
definePageMeta({ layout: false })
import type { Team, CandidateProfile } from '~/composables/useApi'
import { useTeamChat } from '~/composables/useTeamChat'
import TeamSidebar from '~/components/build/TeamSidebar.vue'
import ChatPanel from '~/components/build/ChatPanel.vue'

const route = useRoute()
const config = useRuntimeConfig()
const teamId = Number(route.params.id)

// ── Team data ─────────────────────────────────────────────────────────────────

const team = ref<Team | null>(null)
const loading = ref(true)
const pageError = ref('')

async function fetchTeam() {
  try { team.value = await useApi().getTeam(teamId) }
  catch { pageError.value = 'Team not found.' }
  finally { loading.value = false }
}

const candidates = computed<CandidateProfile[]>(() =>
  (team.value?.slots ?? [])
    .map(s => s.candidate)
    .filter((c): c is CandidateProfile => c !== null)
)

const clonedCandidates = computed(() => candidates.value.filter(c => c.dna_cloned))

// ── Role helpers ──────────────────────────────────────────────────────────────

function roleOf(handle: string): string {
  return team.value?.slots.find(s => s.candidate?.github_handle === handle)?.role ?? 'swe'
}

function candidateOf(handle: string): CandidateProfile | undefined {
  return candidates.value.find(c => c.github_handle === handle)
}

// ── Chat composable ───────────────────────────────────────────────────────────

const chat = useTeamChat(teamId, config.public.apiBase as string)

function onGrokKeydown(e: KeyboardEvent) {
  if (e.code === 'ShiftLeft' && !e.ctrlKey && !e.altKey && !e.metaKey) {
    console.log("Toggled")
    chat.toggleGrok()
  }
}

onMounted(async () => {
  await fetchTeam()
  await chat.loadHistory(clonedCandidates.value.map(c => c.github_handle))
  const first = clonedCandidates.value[0]
  if (first) chat.setThread(first)
  window.addEventListener('keydown', onGrokKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onGrokKeydown)
})

// ── Compare overlay ───────────────────────────────────────────────────────────

const compareOpen = ref(false)
const comparePrompt = ref('')
const compareHandle = computed(() =>
  chat.activeThread.value && chat.activeThread.value !== 'orchestrate'
    ? (chat.activeThread.value as CandidateProfile).github_handle
    : clonedCandidates.value[0]?.github_handle ?? ''
)

function openCompare() {
  comparePrompt.value = ''
  chat.compareBase.value = ''
  chat.compareAdapter.value = ''
  chat.compareError.value = ''
  compareOpen.value = true
}

async function runCompare() {
  if (!comparePrompt.value.trim() || !compareHandle.value) return
  await chat.sendCompare(compareHandle.value, comparePrompt.value.trim())
}
</script>

<template>
  <div class="h-screen bg-[var(--bg)] flex flex-col">

    <!-- Header -->
    <header class="flex-shrink-0 bg-[rgba(250,248,244,0.92)] border-b border-[var(--border)] px-8 py-4 flex items-center justify-between gap-6 backdrop-blur-md">
      <div class="flex items-center gap-5 min-w-0">
        <NuxtLink :to="`/teams/${teamId}`" class="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors text-sm">
          ← {{ team?.name ?? 'Team' }}
        </NuxtLink>
        <span class="text-[var(--border-mid)]">|</span>
        <span class="text-[var(--text-primary)] font-semibold text-sm">Build with Team</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs text-[var(--text-muted)]">{{ clonedCandidates.length }} DNA blocks loaded</span>
        <button
          v-if="clonedCandidates.length > 0"
          @click="openCompare"
          class="text-xs px-3 py-1.5 rounded border border-[var(--border-mid)] text-[var(--text-secondary)] hover:bg-[var(--bg-card)] hover:text-[var(--text-primary)] transition-colors"
        >
          Compare vs Base
        </button>
      </div>
    </header>

    <!-- Loading / Error -->
    <div v-if="loading" class="flex-1 flex items-center justify-center text-[var(--text-muted)] text-sm">Loading team...</div>
    <div v-else-if="pageError" class="flex-1 flex items-center justify-center text-[var(--red)] text-sm">{{ pageError }}</div>

    <!-- Main layout -->
    <div v-else class="flex-1 flex overflow-hidden min-h-0">
      <TeamSidebar
        :candidates="candidates"
        :active-thread="chat.activeThread.value"
        :threads="chat.threads.value"
        :role-of="roleOf"
        :team-id="teamId"
        @set-thread="chat.setThread"
      />
      <ChatPanel
        :active-thread="chat.activeThread.value"
        :messages="chat.activeMessages()"
        :streaming="chat.streaming.value"
        :streaming-handle="chat.streamingHandle.value"
        :is-thinking="chat.isThinking.value"
        :input-text="chat.inputText.value"
        :chat-end-ref="chat.chatEndRef.value"
        :candidate-of="candidateOf"
        :role-of="roleOf"
        :use-grok="chat.useGrok.value"
        @update:input-text="chat.inputText.value = $event"
        @send="chat.sendMessage()"
        @stop="chat.stopStreaming()"
        @keydown="chat.handleKeydown"
        @toggle-grok="chat.toggleGrok()"
      />
    </div>
  </div>

  <!-- Compare vs Base overlay -->
  <Teleport to="body">
    <div v-if="compareOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div class="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col">

        <!-- Header -->
        <div class="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
          <div>
            <h2 class="font-semibold text-[var(--text-primary)] text-sm">Compare vs Base Model</h2>
            <p class="text-xs text-[var(--text-muted)] mt-0.5">See how the fine-tuned adapter differs from the raw base model on the same prompt.</p>
          </div>
          <button @click="compareOpen = false; chat.stopCompare()" class="text-[var(--text-muted)] hover:text-[var(--text-primary)] text-xl leading-none">×</button>
        </div>

        <!-- Prompt input -->
        <div class="px-6 py-4 border-b border-[var(--border)] flex gap-3">
          <select v-model="compareHandle" class="text-xs border border-[var(--border-mid)] rounded px-2 py-1.5 bg-[var(--bg)] text-[var(--text-secondary)] shrink-0">
            <option v-for="c in clonedCandidates" :key="c.github_handle" :value="c.github_handle">@{{ c.github_handle }}</option>
          </select>
          <input
            v-model="comparePrompt"
            @keydown.enter.prevent="runCompare"
            placeholder="Enter a prompt to compare base vs adapter…"
            class="flex-1 text-sm border border-[var(--border-mid)] rounded px-3 py-1.5 bg-[var(--bg)] text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)]"
          />
          <button
            @click="runCompare"
            :disabled="chat.compareLoading.value || !comparePrompt.trim()"
            class="text-xs px-4 py-1.5 rounded bg-[var(--accent)] text-white hover:opacity-90 disabled:opacity-40 transition-opacity shrink-0"
          >
            {{ chat.compareLoading.value ? 'Running…' : 'Run' }}
          </button>
        </div>

        <!-- Results -->
        <div class="flex-1 overflow-hidden flex min-h-0">
          <div class="flex-1 flex flex-col border-r border-[var(--border)] overflow-hidden">
            <div class="px-4 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border)] text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide">Base Model</div>
            <div class="flex-1 overflow-y-auto p-4 text-sm text-[var(--text-secondary)] whitespace-pre-wrap font-mono leading-relaxed">
              <span v-if="!chat.compareBase.value && !chat.compareLoading.value" class="text-[var(--text-muted)] italic">Response will appear here…</span>
              <span>{{ chat.compareBase.value }}</span>
            </div>
          </div>
          <div class="flex-1 flex flex-col overflow-hidden">
            <div class="px-4 py-2 bg-[var(--bg-secondary)] border-b border-[var(--border)] text-xs font-medium text-[var(--accent)] uppercase tracking-wide">Fine-tuned Adapter (@{{ compareHandle }})</div>
            <div class="flex-1 overflow-y-auto p-4 text-sm text-[var(--text-secondary)] whitespace-pre-wrap font-mono leading-relaxed">
              <span v-if="!chat.compareAdapter.value && !chat.compareLoading.value" class="text-[var(--text-muted)] italic">Response will appear here…</span>
              <span>{{ chat.compareAdapter.value }}</span>
            </div>
          </div>
        </div>

        <!-- Error -->
        <div v-if="chat.compareError.value" class="px-6 py-3 border-t border-[var(--border)] text-xs text-red-600">{{ chat.compareError.value }}</div>
      </div>
    </div>
  </Teleport>
</template>
