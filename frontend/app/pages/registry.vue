<script setup lang="ts">
const config = useRuntimeConfig()
const base = config.public.apiBase

interface DnaBlock {
  team_id: string
  handle: string
  name: string
  version?: string
  expertise_domains: string[]
  tags: string[]
  base_model: string
  vllm_compatible?: boolean
  created: string
  eval_summary: {
    final_loss?: number
    best_loss?: number
    style_consistency?: number
    domain_accuracy?: number
    latency_overhead_ms?: number
    teacher_model?: string
  }
  training_pairs?: number
}

const blocks = ref<DnaBlock[]>([])
const loading = ref(true)
const search = ref('')
const selectedBlock = ref<DnaBlock | null>(null)

async function fetchBlocks() {
  loading.value = true
  try {
    const data = await $fetch<{ total: number; blocks: DnaBlock[] }>(`${base}/registry`)
    blocks.value = data.blocks
  } catch { blocks.value = [] }
  finally { loading.value = false }
}

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  if (!q) return blocks.value
  return blocks.value.filter(b =>
    b.handle.toLowerCase().includes(q)
    || b.name?.toLowerCase().includes(q)
    || b.expertise_domains.some(d => d.toLowerCase().includes(q))
    || b.tags.some(t => t.toLowerCase().includes(q))
  )
})

function downloadUrl(b: DnaBlock) {
  return `${base}/registry/${b.team_id}/${b.handle}/download`
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatScore(val: number | null | undefined) {
  if (val == null) return '—'
  return (val * 100).toFixed(0) + '%'
}

function formatLoss(val: number | null | undefined) {
  if (val == null) return '—'
  return val.toFixed(3)
}

onMounted(fetchBlocks)
</script>

<template>
  <div class="min-h-screen bg-slate-950">

    <!-- Header -->
    <header class="bg-slate-900/80 border-b border-slate-800 px-6 py-4 flex items-center justify-between backdrop-blur">
      <div class="flex items-center gap-4">
        <NuxtLink to="/" class="text-xl font-bold text-white tracking-tight hover:text-blue-400 transition-colors">
          Clone.dna
        </NuxtLink>
        <span class="text-slate-600">|</span>
        <span class="text-sm font-medium text-slate-400">Talent Registry</span>
      </div>
      <NuxtLink
        to="/"
        class="border border-slate-700 text-slate-400 font-medium px-4 py-1.5 text-sm hover:border-slate-500 hover:text-white transition-colors"
      >
        Teams
      </NuxtLink>
    </header>

    <!-- Main -->
    <main class="max-w-5xl mx-auto px-6 py-10">
      <div class="mb-8">
        <h1 class="text-2xl font-semibold text-white">DNA Registry</h1>
        <p class="text-slate-500 text-sm mt-1">Browse, search, and download minted .dna blocks</p>
      </div>

      <!-- Search -->
      <div class="mb-6">
        <input
          v-model="search"
          type="text"
          placeholder="Search by handle, skill, or domain..."
          class="w-full max-w-md border border-slate-700 focus:border-blue-500 bg-slate-900 text-white placeholder-slate-600 px-4 py-2.5 text-sm outline-none transition-colors"
        />
      </div>

      <!-- Loading -->
      <p v-if="loading" class="text-slate-500 text-sm">Loading registry...</p>

      <!-- Empty -->
      <div v-else-if="!blocks.length" class="border border-dashed border-slate-700 bg-slate-900/40 p-16 text-center">
        <p class="text-slate-500">No .dna blocks minted yet.</p>
        <p class="text-slate-600 text-sm mt-2">Clone a team's DNA to populate the registry.</p>
      </div>

      <!-- No results -->
      <p v-else-if="!filtered.length" class="text-slate-500 text-sm">
        No blocks match "{{ search }}"
      </p>

      <!-- Grid -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div
          v-for="block in filtered"
          :key="`${block.team_id}-${block.handle}`"
          class="bg-slate-900/60 border border-slate-800 hover:border-slate-600 transition-colors p-5 cursor-pointer"
          @click="selectedBlock = selectedBlock?.handle === block.handle ? null : block"
        >
          <div class="flex items-start justify-between mb-3">
            <div>
              <p class="font-semibold text-white">{{ block.handle }}</p>
              <p class="text-xs text-slate-500 mt-0.5">{{ block.name }}</p>
            </div>
            <span class="text-xs font-medium border border-green-600 text-green-400 bg-green-950/50 px-2 py-0.5">
              v{{ block.version || '1.0.0' }}
            </span>
          </div>

          <!-- Domains -->
          <div class="flex flex-wrap gap-1.5 mb-3">
            <span
              v-for="domain in block.expertise_domains.slice(0, 5)"
              :key="domain"
              class="text-xs px-2 py-0.5 border border-slate-700 text-slate-400"
            >
              {{ domain }}
            </span>
          </div>

          <!-- Scores row -->
          <div class="grid grid-cols-3 gap-3 text-xs mb-3">
            <div>
              <p class="text-slate-600 mb-0.5">Style</p>
              <p class="text-slate-300 font-medium">{{ formatScore(block.eval_summary.style_consistency) }}</p>
            </div>
            <div>
              <p class="text-slate-600 mb-0.5">Domain</p>
              <p class="text-slate-300 font-medium">{{ formatScore(block.eval_summary.domain_accuracy) }}</p>
            </div>
            <div>
              <p class="text-slate-600 mb-0.5">Loss</p>
              <p class="text-slate-300 font-medium">{{ formatLoss(block.eval_summary.best_loss || block.eval_summary.final_loss) }}</p>
            </div>
          </div>

          <!-- Meta row -->
          <div class="flex items-center justify-between text-xs text-slate-600">
            <span>{{ block.training_pairs || '—' }} pairs</span>
            <span>{{ formatDate(block.created) }}</span>
          </div>

          <!-- Expanded detail -->
          <Transition name="expand">
            <div v-if="selectedBlock?.handle === block.handle" class="mt-4 pt-4 border-t border-slate-800">
              <div class="grid grid-cols-2 gap-3 text-xs mb-4">
                <div>
                  <p class="text-slate-600 mb-0.5">Base Model</p>
                  <p class="text-slate-400 font-mono text-[11px] break-all">{{ block.base_model }}</p>
                </div>
                <div>
                  <p class="text-slate-600 mb-0.5">Latency Overhead</p>
                  <p class="text-slate-300">{{ block.eval_summary.latency_overhead_ms ? block.eval_summary.latency_overhead_ms + 'ms' : '—' }}</p>
                </div>
                <div>
                  <p class="text-slate-600 mb-0.5">Teacher</p>
                  <p class="text-slate-300">{{ block.eval_summary.teacher_model || '—' }}</p>
                </div>
                <div>
                  <p class="text-slate-600 mb-0.5">vLLM</p>
                  <p class="text-slate-300">{{ block.vllm_compatible ? 'Compatible' : 'No' }}</p>
                </div>
              </div>

              <!-- Tags -->
              <div v-if="block.tags.length" class="flex flex-wrap gap-1.5 mb-4">
                <span
                  v-for="tag in block.tags"
                  :key="tag"
                  class="text-xs px-1.5 py-0.5 bg-slate-800 text-slate-500"
                >
                  {{ tag }}
                </span>
              </div>

              <a
                :href="downloadUrl(block)"
                class="inline-block border border-blue-500 text-blue-400 font-medium px-4 py-1.5 text-sm hover:bg-blue-600 hover:text-white transition-colors"
              >
                Download .dna
              </a>
            </div>
          </Transition>
        </div>
      </div>

      <!-- Total -->
      <p v-if="blocks.length" class="text-xs text-slate-600 mt-6">
        {{ filtered.length }} of {{ blocks.length }} block{{ blocks.length === 1 ? '' : 's' }}
      </p>
    </main>
  </div>
</template>

<style scoped>
.expand-enter-active, .expand-leave-active { transition: all 0.2s ease; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; overflow: hidden; }
.expand-enter-to, .expand-leave-from { opacity: 1; max-height: 500px; }
</style>
