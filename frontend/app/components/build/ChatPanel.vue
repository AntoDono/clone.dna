<script setup lang="ts">
import type { CandidateProfile, ChatMessage } from '~/composables/useApi'
import type { ActiveThread } from '~/composables/useTeamChat'

const props = defineProps<{
  activeThread: ActiveThread | null
  messages: ChatMessage[]
  streaming: boolean
  streamingHandle: string | null
  inputText: string
  chatEndRef: HTMLElement | null
  candidateOf: (handle: string) => CandidateProfile | undefined
  roleOf: (handle: string) => string
}>()

const emit = defineEmits<{
  'update:inputText': [value: string]
  send: []
  keydown: [e: KeyboardEvent]
}>()

const ROLE_BADGE: Record<string, string> = { pm: 'PM', swe: 'SWE', designer: 'Design' }
const ROLE_COLOR_CLASS: Record<string, string> = {
  pm: 'border-amber-700 text-amber-400',
  swe: 'border-blue-700 text-blue-400',
  designer: 'border-purple-700 text-purple-400',
}

function threadKey(t: ActiveThread) {
  return t === 'orchestrate' ? 'orchestrate' : (t as CandidateProfile).github_handle
}

function isUserMsg(msg: ChatMessage) { return msg.sender === 'user' }

const inputModel = computed({
  get: () => props.inputText,
  set: (v) => emit('update:inputText', v),
})
</script>

<template>
  <div class="flex-1 flex flex-col min-w-0">

    <!-- Thread header -->
    <div class="flex-shrink-0 px-6 py-3 border-b border-slate-800 flex items-center gap-3">
      <template v-if="activeThread === 'orchestrate'">
        <span class="text-lg">⚡</span>
        <div>
          <p class="text-sm font-semibold text-white">Orchestrate</p>
          <p class="text-xs text-slate-500">PM coordinates the full team toward your goal</p>
        </div>
      </template>
      <template v-else-if="activeThread">
        <img
          v-if="(activeThread as CandidateProfile).avatar_url"
          :src="(activeThread as CandidateProfile).avatar_url"
          class="w-8 h-8 object-cover"
        />
        <div>
          <p class="text-sm font-semibold text-white">
            {{ (activeThread as CandidateProfile).name || (activeThread as CandidateProfile).github_handle }}
          </p>
          <p class="text-xs text-slate-500">
            @{{ (activeThread as CandidateProfile).github_handle }}
            · {{ ROLE_BADGE[roleOf((activeThread as CandidateProfile).github_handle)] }}
            <span v-if="(activeThread as CandidateProfile).dna_cloned" class="text-green-500 ml-1">· DNA loaded</span>
          </p>
        </div>
      </template>
      <template v-else>
        <p class="text-sm text-slate-500">Select a team member to start chatting</p>
      </template>
    </div>

    <!-- Messages -->
    <div class="flex-1 overflow-y-auto px-6 py-4 space-y-4">
      <div v-if="!activeThread" class="h-full flex flex-col items-center justify-center text-center">
        <p class="text-slate-600 text-sm">Pick a team member from the sidebar to DM them,</p>
        <p class="text-slate-600 text-sm">or use <span class="text-green-400">Orchestrate</span> to let the PM coordinate the whole team.</p>
      </div>

      <div v-else-if="messages.length === 0 && !streaming" class="h-full flex flex-col items-center justify-center text-center">
        <p class="text-slate-600 text-sm">
          <template v-if="activeThread === 'orchestrate'">
            Describe what you want to build — the PM will plan and delegate to the team.
          </template>
          <template v-else>
            Start a conversation with {{ (activeThread as CandidateProfile).name || (activeThread as CandidateProfile).github_handle }}.
          </template>
        </p>
      </div>

      <TransitionGroup name="msg" tag="div" class="space-y-4">
        <div
          v-for="msg in messages"
          :key="msg.id"
          class="flex gap-3"
          :class="isUserMsg(msg) ? 'flex-row-reverse' : 'flex-row'"
        >
          <!-- Avatar -->
          <div class="flex-shrink-0 mt-0.5">
            <div v-if="isUserMsg(msg)" class="w-7 h-7 bg-slate-700 border border-slate-600 flex items-center justify-center text-xs font-bold text-slate-300">
              U
            </div>
            <template v-else>
              <img
                v-if="candidateOf(msg.sender)?.avatar_url"
                :src="candidateOf(msg.sender)!.avatar_url"
                class="w-7 h-7 object-cover"
              />
              <div v-else class="w-7 h-7 bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-slate-400">
                {{ (candidateOf(msg.sender)?.name ?? msg.sender)[0]?.toUpperCase() }}
              </div>
            </template>
          </div>

          <!-- Bubble -->
          <div class="flex flex-col max-w-[72%]" :class="isUserMsg(msg) ? 'items-end' : 'items-start'">
            <div v-if="!isUserMsg(msg)" class="flex items-center gap-1.5 mb-1">
              <span class="text-xs font-medium text-slate-400">
                {{ candidateOf(msg.sender)?.name || msg.sender }}
              </span>
              <span
                class="text-xs border px-1 py-px"
                :class="ROLE_COLOR_CLASS[roleOf(msg.sender)] ?? 'border-slate-700 text-slate-500'"
              >{{ ROLE_BADGE[roleOf(msg.sender)] ?? msg.sender }}</span>
            </div>

            <div
              class="px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words"
              :class="isUserMsg(msg)
                ? 'bg-blue-700/40 border border-blue-600/40 text-white'
                : 'bg-slate-900/80 border border-slate-700/60 text-slate-200'"
            >
              {{ msg.content }}
              <span
                v-if="streaming && streamingHandle && !isUserMsg(msg) && msg === messages[messages.length - 1] && msg.content === ''"
                class="inline-block w-1.5 h-3.5 bg-blue-400 animate-pulse ml-0.5 align-text-bottom"
              ></span>
            </div>

            <span class="text-xs text-slate-700 mt-1">
              {{ new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}
            </span>
          </div>
        </div>
      </TransitionGroup>

      <!-- Streaming dots while waiting for first token -->
      <div
        v-if="streaming && activeThread && streamingHandle === threadKey(activeThread) && messages.every(m => m.content !== '' || m.sender === 'user')"
        class="flex gap-3"
      >
        <div class="w-7 h-7 bg-slate-800 border border-slate-700 flex items-center justify-center">
          <span class="flex gap-0.5">
            <span class="w-1 h-1 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
            <span class="w-1 h-1 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 100ms"></span>
            <span class="w-1 h-1 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 200ms"></span>
          </span>
        </div>
      </div>

      <div :ref="(el) => $emit('update:chatEndRef', el)"></div>
    </div>

    <!-- Input -->
    <div class="flex-shrink-0 border-t border-slate-800 bg-slate-900/40 p-4">
      <div class="flex gap-3 items-end">
        <textarea
          v-model="inputModel"
          :placeholder="activeThread === 'orchestrate'
            ? 'Describe what you want to build...'
            : activeThread
              ? `Message ${(activeThread as CandidateProfile).name || (activeThread as CandidateProfile).github_handle}...`
              : 'Select a team member first'"
          :disabled="!activeThread || streaming || (activeThread !== 'orchestrate' && !(activeThread as CandidateProfile).dna_cloned)"
          rows="2"
          class="flex-1 bg-slate-900 border border-slate-700 text-slate-200 text-sm px-4 py-3 resize-none focus:outline-none focus:border-blue-600 transition-colors placeholder-slate-600 disabled:opacity-40"
          @keydown="emit('keydown', $event)"
        ></textarea>
        <button
          :disabled="!inputText.trim() || streaming || !activeThread"
          class="px-5 py-3 text-sm font-semibold border transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          :class="activeThread === 'orchestrate'
            ? 'border-green-600 text-green-400 hover:bg-green-950/40'
            : 'border-blue-600 text-blue-400 hover:bg-blue-950/40'"
          @click="emit('send')"
        >
          {{ streaming ? '...' : activeThread === 'orchestrate' ? 'Build →' : 'Send →' }}
        </button>
      </div>
      <p class="text-xs text-slate-700 mt-2">Enter to send · Shift+Enter for new line</p>
    </div>
  </div>
</template>

<style scoped>
.msg-enter-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.msg-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
</style>
