<script setup lang="ts">
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

onMounted(async () => {
  await fetchTeam()
  await chat.loadHistory(clonedCandidates.value.map(c => c.github_handle))
  const first = clonedCandidates.value[0]
  if (first) chat.setThread(first)
})
</script>

<template>
  <div class="min-h-screen bg-slate-950 flex flex-col">

    <!-- Header -->
    <header class="flex-shrink-0 bg-slate-900/80 border-b border-slate-800 px-6 py-4 flex items-center justify-between backdrop-blur">
      <div class="flex items-center gap-4">
        <NuxtLink :to="`/teams/${teamId}`" class="text-slate-500 hover:text-slate-300 transition-colors text-sm">
          ← {{ team?.name ?? 'Team' }}
        </NuxtLink>
        <span class="text-slate-700">|</span>
        <span class="text-white font-semibold text-sm">Build with Team</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs text-slate-600">{{ clonedCandidates.length }} DNA blocks loaded</span>
      </div>
    </header>

    <!-- Loading / Error -->
    <div v-if="loading" class="flex-1 flex items-center justify-center text-slate-500 text-sm">Loading team...</div>
    <div v-else-if="pageError" class="flex-1 flex items-center justify-center text-red-400 text-sm">{{ pageError }}</div>

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
        @update:input-text="chat.inputText.value = $event"
        @send="chat.sendMessage()"
        @keydown="chat.handleKeydown"
      />
    </div>
  </div>
</template>
