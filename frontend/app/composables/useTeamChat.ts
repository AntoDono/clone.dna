import type { CandidateProfile, ChatMessage } from '~/composables/useApi'

export type ActiveThread = CandidateProfile | 'orchestrate'

const KNOWN_COMMANDS = new Set([
  'run_command', 'write_file', 'read_file', 'create_folder', 'list_files', 'edit_file',
])

const JSON_CMD_PATTERN = /```(?:json)?\s*\n?\s*(\{[\s\S]*?\})\s*\n?\s*```|\{[\t ]*"name"[\t ]*:[\t ]*"[^"]+?"[\t ]*,[\t ]*"arguments"[\t ]*:[\t ]*\{[\s\S]*?\}\s*\}/g

function convertInlineJsonToToolMarkers(content: string): string {
  return content.replace(JSON_CMD_PATTERN, (fullMatch, fencedBody) => {
    const raw = fencedBody ?? fullMatch
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed.name === 'string' && KNOWN_COMMANDS.has(parsed.name) && parsed.arguments) {
        console.log('[useTeamChat] Converted inline JSON command →', parsed.name, parsed.arguments)
        return `\n[[TOOL_CALL:${JSON.stringify(parsed)}]]\n`
      }
    } catch { /* not valid JSON */ }
    return fullMatch
  })
}

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
  const isThinking = ref(false)
  let abortController: AbortController | null = null

  function stopStreaming() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    isThinking.value = false
    streaming.value = false
    streamingHandle.value = null
  }

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
    isThinking.value = false
    abortController = new AbortController()

    pushMessage(key, {
      id: Date.now(), thread: key, sender: 'user',
      content: message, created_at: new Date().toISOString(),
    })

    let response: Response
    try {
      response = await fetch(`${apiBase}/teams/${teamId}/build/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ handle: key, message }),
        signal: abortController.signal,
      })
    } catch (e: any) {
      if (e.name === 'AbortError') {
        streaming.value = false
        streamingHandle.value = null
        isThinking.value = false
        return
      }
      throw e
    }

    if (!response.ok) {
      pushMessage(key, {
        id: Date.now() + 1, thread: key, sender: key,
        content: '[Error sending message]', created_at: new Date().toISOString(),
      })
      streaming.value = false
      streamingHandle.value = null
      isThinking.value = false
      return
    }

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let assistantIdx = -1
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()!
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.thinking === true) {
              isThinking.value = true
            } else if (data.thinking === false) {
              isThinking.value = false
            } else if (data.token) {
              isThinking.value = false
              if (assistantIdx === -1) {
                if (!threads.value[key]) threads.value[key] = []
                threads.value[key].push({
                  id: Date.now() + 1, thread: key, sender: key,
                  content: '', created_at: new Date().toISOString(),
                })
                assistantIdx = threads.value[key].length - 1
              }
              threads.value[key]![assistantIdx]!.content += data.token
              scrollToBottom()
            } else if (data.tool_call) {
              if (assistantIdx === -1) {
                if (!threads.value[key]) threads.value[key] = []
                threads.value[key].push({
                  id: Date.now() + 1, thread: key, sender: key,
                  content: '', created_at: new Date().toISOString(),
                })
                assistantIdx = threads.value[key].length - 1
              }
              threads.value[key]![assistantIdx]!.content += `\n[[TOOL_CALL:${JSON.stringify(data.tool_call)}]]\n`
              scrollToBottom()
            } else if (data.tool_result) {
              if (assistantIdx !== -1) {
                threads.value[key]![assistantIdx]!.content += `\n[[TOOL_RESULT:${JSON.stringify(data.tool_result)}]]\n`
                scrollToBottom()
              }
            } else if (data.done && data.message_id) {
              if (assistantIdx !== -1) threads.value[key]![assistantIdx]!.id = data.message_id
            } else if (data.error) {
              if (assistantIdx === -1) {
                if (!threads.value[key]) threads.value[key] = []
                threads.value[key].push({
                  id: Date.now() + 1, thread: key, sender: key,
                  content: '', created_at: new Date().toISOString(),
                })
                assistantIdx = threads.value[key].length - 1
              }
              threads.value[key]![assistantIdx]!.content = `[Error: ${data.error}]`
            }
          } catch { /* skip malformed */ }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') throw e
    }

    if (assistantIdx !== -1) {
      const msg = threads.value[key]![assistantIdx]!
      msg.content = convertInlineJsonToToolMarkers(msg.content)
    }

    abortController = null
    isThinking.value = false
    streaming.value = false
    streamingHandle.value = null
  }

  // ── Orchestrate ───────────────────────────────────────────────────────────

  async function sendOrchestrate(prompt: string) {
    const key = 'orchestrate'
    streaming.value = true
    streamingHandle.value = key
    isThinking.value = false
    abortController = new AbortController()

    pushMessage(key, {
      id: Date.now(), thread: key, sender: 'user',
      content: prompt, created_at: new Date().toISOString(),
    })

    let response: Response
    try {
      response = await fetch(`${apiBase}/teams/${teamId}/build/orchestrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
        signal: abortController.signal,
      })
    } catch (e: any) {
      if (e.name === 'AbortError') {
        streaming.value = false
        streamingHandle.value = null
        isThinking.value = false
        return
      }
      throw e
    }

    if (!response.ok) {
      streaming.value = false
      streamingHandle.value = null
      isThinking.value = false
      return
    }

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let currentSpeaker: string | null = null
    let currentMsgIdx = -1
    let orchBuffer = ''

    function getOrCreateBubbleIdx(speaker: string): number {
      if (currentSpeaker !== speaker) {
        currentSpeaker = speaker
        if (!threads.value[key]) threads.value[key] = []
        threads.value[key].push({
          id: Date.now() + Math.random(), thread: key,
          sender: speaker, content: '', created_at: new Date().toISOString(),
        })
        currentMsgIdx = threads.value[key].length - 1
        scrollToBottom()
      }
      return currentMsgIdx
    }

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        orchBuffer += decoder.decode(value, { stream: true })
        const lines = orchBuffer.split('\n')
        orchBuffer = lines.pop()!
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.done) break
            if (data.phase === 'specialist') {
              currentSpeaker = null
              continue
            }
            if (data.speaker && data.token) {
              const idx = getOrCreateBubbleIdx(data.speaker)
              threads.value[key]![idx]!.content += data.token
              scrollToBottom()
            } else if (data.speaker && data.tool_call) {
              const idx = getOrCreateBubbleIdx(data.speaker)
              threads.value[key]![idx]!.content += `\n[[TOOL_CALL:${JSON.stringify(data.tool_call)}]]\n`
              scrollToBottom()
            } else if (data.speaker && data.tool_result) {
              if (currentMsgIdx !== -1) {
                threads.value[key]![currentMsgIdx]!.content += `\n[[TOOL_RESULT:${JSON.stringify(data.tool_result)}]]\n`
                scrollToBottom()
              }
            }
          } catch { /* skip malformed */ }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') throw e
    }

    const orchMsgs = threads.value[key]
    if (orchMsgs) {
      for (const msg of orchMsgs) {
        if (msg.sender !== 'user') {
          msg.content = convertInlineJsonToToolMarkers(msg.content)
        }
      }
    }

    abortController = null
    isThinking.value = false
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
    isThinking,
    sendMessage,
    stopStreaming,
    handleKeydown,
  }
}
