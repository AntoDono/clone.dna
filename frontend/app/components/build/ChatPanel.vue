<script setup lang="ts">
import { marked } from 'marked'
import type { CandidateProfile, ChatMessage } from '~/composables/useApi'
import type { ActiveThread } from '~/composables/useTeamChat'

marked.setOptions({ breaks: true, gfm: true })

const props = defineProps<{
  activeThread: ActiveThread | null
  messages: ChatMessage[]
  streaming: boolean
  streamingHandle: string | null
  isThinking: boolean
  inputText: string
  chatEndRef: HTMLElement | null
  candidateOf: (handle: string) => CandidateProfile | undefined
  roleOf: (handle: string) => string
  useGrok?: boolean
}>()

const emit = defineEmits<{
  'update:inputText': [value: string]
  send: []
  stop: []
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

interface ContentSegment {
  type: 'text' | 'tool_call' | 'tool_result'
  data: string | Record<string, any>
}

const KNOWN_COMMANDS = new Set([
  'run_command', 'write_file', 'read_file', 'create_folder', 'list_files', 'edit_file',
])

function tryExtractJsonCommand(text: string): ContentSegment[] {
  const segments: ContentSegment[] = []
  const jsonPattern = /```(?:json)?\s*\n?\s*(\{[\s\S]*?\})\s*\n?\s*```|\{[\t ]*"name"[\t ]*:[\t ]*"[^"]+?"[\t ]*,[\t ]*"arguments"[\t ]*:[\t ]*\{[\s\S]*?\}\s*\}/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = jsonPattern.exec(text)) !== null) {
    const raw = match[1] ?? match[0]
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed.name === 'string' && KNOWN_COMMANDS.has(parsed.name) && parsed.arguments) {
        console.log('[ChatPanel] Detected inline JSON command:', parsed.name, parsed.arguments)
        if (match.index > lastIndex) {
          const before = text.slice(lastIndex, match.index).replace(/^\n+|\n+$/g, '')
          if (before.trim()) segments.push({ type: 'text', data: before })
        }
        segments.push({ type: 'tool_call', data: parsed })
        lastIndex = match.index + match[0].length
      }
    } catch { /* not valid JSON, leave as text */ }
  }

  if (segments.length === 0) return [{ type: 'text', data: text }]

  if (lastIndex < text.length) {
    const after = text.slice(lastIndex).replace(/^\n+/, '')
    if (after.trim()) segments.push({ type: 'text', data: after })
  }
  return segments
}

function parseMessageContent(content: string): ContentSegment[] {
  const segments: ContentSegment[] = []
  const regex = /\[\[(TOOL_CALL|TOOL_RESULT):(.*?)\]\]/gs
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      const text = content.slice(lastIndex, match.index).replace(/^\n+|\n+$/g, '')
      if (text) segments.push(...tryExtractJsonCommand(text))
    }
    try {
      const parsed = JSON.parse(match[2])
      segments.push({ type: match[1] === 'TOOL_CALL' ? 'tool_call' : 'tool_result', data: parsed })
    } catch {
      segments.push({ type: 'text', data: match[0] })
    }
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < content.length) {
    const text = content.slice(lastIndex).replace(/^\n+/, '')
    if (text) segments.push(...tryExtractJsonCommand(text))
  }

  return segments
}

function renderMarkdown(text: string): string {
  return marked.parse(text, { async: false }) as string
}

function truncate(s: string, max: number = 120): string {
  return s.length > max ? s.slice(0, max) + '...' : s
}

const TOOL_ICONS: Record<string, string> = {
  write_file: '> write',
  read_file: '> read',
  create_folder: '> mkdir',
  list_files: '> ls',
  edit_file: '> edit',
  run_command: '> $',
}

const expandedTools = ref<Set<number>>(new Set())
function toggleExpand(idx: number) {
  if (expandedTools.value.has(idx)) expandedTools.value.delete(idx)
  else expandedTools.value.add(idx)
}

const inputModel = computed({
  get: () => props.inputText,
  set: (v) => emit('update:inputText', v),
})
</script>

<template>
  <div class="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">

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
      <div class="ml-auto flex items-center gap-2">
        <span
          v-if="useGrok"
          class="px-2 py-0.5 text-xs font-bold border border-orange-600 text-orange-400 bg-orange-950/40 tracking-wide animate-pulse"
        >GROK</span>
        <span v-else class="px-2 py-0.5 text-xs border border-slate-700 text-slate-600">LOCAL</span>
      </div>
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
              class="px-4 py-2.5 text-sm leading-relaxed break-words"
              :class="isUserMsg(msg)
                ? 'bg-blue-700/40 border border-blue-600/40 text-white whitespace-pre-wrap'
                : 'bg-slate-900/80 border border-slate-700/60 text-slate-200'"
            >
              <template v-if="isUserMsg(msg)">{{ msg.content }}</template>
              <template v-else>
                <template v-for="(seg, sIdx) in parseMessageContent(msg.content)" :key="sIdx">
                  <div v-if="seg.type === 'text'" class="prose-chat" v-html="renderMarkdown(seg.data as string)"></div>

                  <div v-else-if="seg.type === 'tool_call'" class="my-2 bg-slate-950 border border-slate-700 text-xs font-mono overflow-hidden">
                    <div class="flex items-center gap-2 px-3 py-1.5 border-b border-slate-800 bg-slate-900/60">
                      <span class="text-blue-400 font-semibold">{{ TOOL_ICONS[(seg.data as any).name] || (seg.data as any).name }}</span>
                      <span class="text-slate-500">{{ (seg.data as any).name }}</span>
                    </div>
                    <div class="px-3 py-2 text-slate-400 space-y-0.5">
                      <template v-for="(val, argKey) in (seg.data as any).arguments" :key="argKey">
                        <div class="flex gap-2">
                          <span class="text-slate-500 shrink-0">{{ argKey }}:</span>
                          <span
                            class="text-slate-300 cursor-pointer"
                            @click="toggleExpand(sIdx)"
                          >{{ expandedTools.has(sIdx) ? String(val) : truncate(String(val)) }}</span>
                        </div>
                      </template>
                    </div>
                  </div>

                  <div v-else-if="seg.type === 'tool_result'" class="my-2 border text-xs font-mono overflow-hidden"
                    :class="(seg.data as any).success ? 'bg-slate-950 border-green-800 border-l-2 border-l-green-500' : 'bg-slate-950 border-red-800 border-l-2 border-l-red-500'"
                  >
                    <div class="px-3 py-1.5 border-b border-slate-800 bg-slate-900/60">
                      <span :class="(seg.data as any).success ? 'text-green-400' : 'text-red-400'">
                        {{ (seg.data as any).success ? 'OK' : 'FAIL' }}
                      </span>
                      <span class="text-slate-500 ml-2">{{ (seg.data as any).name }}</span>
                    </div>
                    <div
                      class="px-3 py-2 text-slate-400 whitespace-pre-wrap cursor-pointer"
                      :class="(seg.data as any).name === 'run_command' ? 'bg-black/40' : ''"
                      @click="toggleExpand(sIdx + 10000)"
                    >{{ expandedTools.has(sIdx + 10000) ? (seg.data as any).output : truncate((seg.data as any).output, 200) }}</div>
                  </div>
                </template>
              </template>
              <span
                v-if="streaming && streamingHandle && !isUserMsg(msg) && msg === messages[messages.length - 1]"
                class="inline-block w-1.5 h-3.5 bg-blue-400 animate-pulse ml-0.5 align-text-bottom"
              ></span>
            </div>

            <span class="text-xs text-slate-700 mt-1">
              {{ new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}
            </span>
          </div>
        </div>
      </TransitionGroup>

      <!-- Thinking / waiting indicator (shown until the first real token arrives) -->
      <div
        v-if="streaming && activeThread && streamingHandle === threadKey(activeThread) && (messages.length === 0 || messages.at(-1)?.sender === 'user')"
        class="flex gap-3 items-center"
      >
        <div class="w-7 h-7 bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0">
          <span class="flex gap-0.5">
            <span class="w-1 h-1 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
            <span class="w-1 h-1 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 100ms"></span>
            <span class="w-1 h-1 bg-slate-500 rounded-full animate-bounce" style="animation-delay: 200ms"></span>
          </span>
        </div>
        <span v-if="isThinking" class="text-xs text-slate-500 animate-pulse tracking-wide">Thinking…</span>
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
          v-if="streaming"
          class="px-5 py-3 text-sm font-semibold border border-red-600 text-red-400 hover:bg-red-950/40 transition-colors"
          @click="emit('stop')"
        >
          Stop ■
        </button>
        <button
          v-else
          :disabled="!inputText.trim() || !activeThread"
          class="px-5 py-3 text-sm font-semibold border transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          :class="activeThread === 'orchestrate'
            ? 'border-green-600 text-green-400 hover:bg-green-950/40'
            : 'border-blue-600 text-blue-400 hover:bg-blue-950/40'"
          @click="emit('send')"
        >
          {{ activeThread === 'orchestrate' ? 'Build →' : 'Send →' }}
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

/* Markdown prose styling for chat bubbles */
.prose-chat :deep(p) {
  margin: 0.25em 0;
}
.prose-chat :deep(p:first-child) {
  margin-top: 0;
}
.prose-chat :deep(p:last-child) {
  margin-bottom: 0;
}
.prose-chat :deep(h1),
.prose-chat :deep(h2),
.prose-chat :deep(h3),
.prose-chat :deep(h4) {
  color: #e2e8f0;
  font-weight: 600;
  margin: 0.6em 0 0.3em;
}
.prose-chat :deep(h1) { font-size: 1.2em; }
.prose-chat :deep(h2) { font-size: 1.1em; }
.prose-chat :deep(h3) { font-size: 1.05em; }
.prose-chat :deep(strong) {
  color: #e2e8f0;
  font-weight: 600;
}
.prose-chat :deep(em) {
  font-style: italic;
}
.prose-chat :deep(a) {
  color: #60a5fa;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.prose-chat :deep(a:hover) {
  color: #93bbfd;
}
.prose-chat :deep(code) {
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(100, 116, 139, 0.3);
  padding: 0.15em 0.35em;
  border-radius: 3px;
  font-size: 0.88em;
  font-family: ui-monospace, 'Cascadia Code', 'Source Code Pro', Menlo, monospace;
  color: #93c5fd;
}
.prose-chat :deep(pre) {
  background: rgba(0, 0, 0, 0.45);
  border: 1px solid rgba(100, 116, 139, 0.3);
  padding: 0.75em 1em;
  margin: 0.5em 0;
  overflow-x: auto;
  font-size: 0.85em;
}
.prose-chat :deep(pre code) {
  background: none;
  border: none;
  padding: 0;
  color: #cbd5e1;
}
.prose-chat :deep(ul),
.prose-chat :deep(ol) {
  margin: 0.4em 0;
  padding-left: 1.5em;
}
.prose-chat :deep(ul) {
  list-style-type: disc;
}
.prose-chat :deep(ol) {
  list-style-type: decimal;
}
.prose-chat :deep(li) {
  margin: 0.15em 0;
}
.prose-chat :deep(li p) {
  margin: 0;
}
.prose-chat :deep(blockquote) {
  border-left: 3px solid #475569;
  padding-left: 0.75em;
  margin: 0.4em 0;
  color: #94a3b8;
}
.prose-chat :deep(hr) {
  border: none;
  border-top: 1px solid rgba(100, 116, 139, 0.3);
  margin: 0.6em 0;
}
.prose-chat :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.5em 0;
  font-size: 0.9em;
}
.prose-chat :deep(th),
.prose-chat :deep(td) {
  border: 1px solid rgba(100, 116, 139, 0.3);
  padding: 0.35em 0.6em;
  text-align: left;
}
.prose-chat :deep(th) {
  background: rgba(0, 0, 0, 0.25);
  color: #e2e8f0;
  font-weight: 600;
}
</style>
