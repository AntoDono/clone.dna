import type { CandidateProfile, ChatMessage } from '~/composables/useApi'

export type ActiveThread = CandidateProfile | 'orchestrate'

export function useTeamChat(teamId: number, apiBase: string) {
  const api = useApi()

  // ── Thread state ──────────────────────────────────────────────────────────

  const activeThread = ref<ActiveThread | null>(null)
  const threads = ref<Record<string, ChatMessage[]>>({})

  function threadKey(t: ActiveThread) {
    return t === 'orchestrate' ? 'orchestrate' : (t as CandidateProfile).github_handle
  }

  function activeMessages() {
    if (!activeThread.value) return []
    return threads.value[threadKey(activeThread.value)] ?? []
  }

  function setThread(t: ActiveThread) {
    activeThread.value = t
    scrollToBottom()
  }

  // ── Message history ───────────────────────────────────────────────────────

  async function loadHistory(handles: string[]) {
    const keys = [...handles, 'orchestrate']
    await Promise.all(keys.map(async (key) => {
      try {
        threads.value[key] = await api.getBuildMessages(teamId, key)
      } catch { /* empty thread */ }
    }))
  }

  // ── Scroll helper ─────────────────────────────────────────────────────────

  const chatEndRef = ref<HTMLElement | null>(null)

  function scrollToBottom() {
    nextTick(() => {
      chatEndRef.value?.scrollIntoView({ behavior: 'smooth' })
    })
  }

  // ── Message helpers ───────────────────────────────────────────────────────

  function pushMessage(key: string, msg: ChatMessage) {
    if (!threads.value[key]) threads.value[key] = []
    threads.value[key].push(msg)
    scrollToBottom()
  }

  // ── Streaming state ───────────────────────────────────────────────────────

  const inputText = ref('')
  const streaming = ref(false)
  const streamingHandle = ref<string | null>(null)

  async function sendMessage() {
    if (!inputText.value.trim() || streaming.value || !activeThread.value) return
    const text = inputText.value.trim()
    inputText.value = ''

    if (activeThread.value === 'orchestrate') {
      await sendOrchestrate(text)
    } else {
      await sendDm(activeThread.value as CandidateProfile, text)
    }
  }

  // ── Direct message ────────────────────────────────────────────────────────

  async function sendDm(candidate: CandidateProfile, message: string) {
    const key = candidate.github_handle
    streaming.value = true
    streamingHandle.value = key

    const userMsg: ChatMessage = {
      id: Date.now(), thread: key, sender: 'user',
      content: message, created_at: new Date().toISOString(),
    }
    pushMessage(key, userMsg)

    const assistantMsg: ChatMessage = {
      id: Date.now() + 1, thread: key, sender: key,
      content: '', created_at: new Date().toISOString(),
    }
    pushMessage(key, assistantMsg)

    const response = await fetch(`${apiBase}/teams/${teamId}/build/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ handle: key, message }),
    })

    if (!response.ok) {
      assistantMsg.content = '[Error sending message]'
      streaming.value = false
      streamingHandle.value = null
      return
    }

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value)
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))
          if (data.token) {
            assistantMsg.content += data.token
            scrollToBottom()
          } else if (data.done && data.message_id) {
            assistantMsg.id = data.message_id
          } else if (data.error) {
            assistantMsg.content = `[Error: ${data.error}]`
          }
        } catch { /* skip malformed */ }
      }
    }

    streaming.value = false
    streamingHandle.value = null
  }

  // ── Orchestrate ───────────────────────────────────────────────────────────

  async function sendOrchestrate(prompt: string) {
    const key = 'orchestrate'
    streaming.value = true
    streamingHandle.value = key

    const userMsg: ChatMessage = {
      id: Date.now(), thread: key, sender: 'user',
      content: prompt, created_at: new Date().toISOString(),
    }
    pushMessage(key, userMsg)

    const response = await fetch(`${apiBase}/teams/${teamId}/build/orchestrate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    })

    if (!response.ok) {
      streaming.value = false
      streamingHandle.value = null
      return
    }

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let currentSpeaker: string | null = null
    let currentMsg: ChatMessage | null = null

    function getOrCreateBubble(speaker: string): ChatMessage {
      if (currentSpeaker !== speaker) {
        currentSpeaker = speaker
        currentMsg = {
          id: Date.now() + Math.random(), thread: key,
          sender: speaker, content: '', created_at: new Date().toISOString(),
        }
        pushMessage(key, currentMsg)
      }
      return currentMsg!
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value)
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))
          if (data.done) break
          if (data.phase === 'specialist') {
            currentSpeaker = null
            continue
          }
          if (data.speaker && data.token) {
            const bubble = getOrCreateBubble(data.speaker)
            bubble.content += data.token
            scrollToBottom()
          }
        } catch { /* skip malformed */ }
      }
    }

    streaming.value = false
    streamingHandle.value = null
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return {
    activeThread,
    threads,
    activeMessages,
    setThread,
    threadKey,
    loadHistory,
    chatEndRef,
    scrollToBottom,
    inputText,
    streaming,
    streamingHandle,
    sendMessage,
    handleKeydown,
  }
}
