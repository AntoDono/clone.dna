<script setup lang="ts">
/**
 * Developer self-service portal — look up any GitHub handle to see if it has
 * been used to mint a .dna block. Shows consent status, source repos, and a
 * one-click revoke button per block. Designed for developers who want to audit
 * and control their code's use in AI training.
 */
const config = useRuntimeConfig()
const base = config.public.apiBase

interface DeveloperBlock {
  team_id: string
  handle: string
  version: string
  base_model: string
  created: string
  consent_status: string
  consent_verified: boolean
  revocable: boolean
  revoked: boolean
  revoked_at: string | null
  source_urls: string[]
  revocation_endpoint: string
}

interface LookupResult {
  handle: string
  total: number
  blocks: DeveloperBlock[]
  message: string
}

const handleInput = ref('')
const result = ref<LookupResult | null>(null)
const loading = ref(false)
const lookupError = ref('')
const revoking = ref<string | null>(null)
const revokeError = ref('')

async function lookup() {
  const h = handleInput.value.trim().replace(/^@/, '')
  if (!h) return
  loading.value = true
  result.value = null
  lookupError.value = ''
  try {
    result.value = await $fetch<LookupResult>(`${base}/registry/developer/${h}`)
  } catch (e: any) {
    lookupError.value = e?.data?.detail ?? 'Lookup failed — is the backend running?'
  } finally {
    loading.value = false
  }
}

async function revoke(block: DeveloperBlock) {
  if (!confirm(`Revoke your .dna block from team ${block.team_id}? This removes it from all registry listings immediately.`)) return
  revoking.value = block.team_id
  revokeError.value = ''
  try {
    await $fetch(`${base}${block.revocation_endpoint}`, { method: 'DELETE' })
    // Mark locally
    if (result.value) {
      const idx = result.value.blocks.findIndex(b => b.team_id === block.team_id)
      if (idx !== -1) {
        result.value.blocks[idx].revoked = true
        result.value.blocks[idx].revoked_at = new Date().toISOString()
      }
    }
  } catch (e: any) {
    revokeError.value = e?.data?.detail ?? 'Revoke failed'
  } finally {
    revoking.value = null
  }
}

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') lookup()
}
</script>

<template>
  <div class="min-h-screen bg-slate-950">

    <!-- Header -->
    <header class="bg-slate-900/80 border-b border-slate-800 px-6 py-4 flex items-center justify-between backdrop-blur">
      <div class="flex items-center gap-4">
        <NuxtLink to="/" class="text-xl font-bold text-white tracking-tight hover:text-blue-400 transition-colors">Clone.dna</NuxtLink>
        <span class="text-slate-600">|</span>
        <span class="text-sm font-medium text-slate-400">Developer Portal</span>
      </div>
      <div class="flex items-center gap-3">
        <NuxtLink to="/registry" class="border border-slate-700 text-slate-400 font-medium px-4 py-1.5 text-sm hover:border-slate-500 hover:text-white transition-colors">Registry</NuxtLink>
        <NuxtLink to="/" class="border border-slate-700 text-slate-400 font-medium px-4 py-1.5 text-sm hover:border-slate-500 hover:text-white transition-colors">Teams</NuxtLink>
      </div>
    </header>

    <main class="max-w-3xl mx-auto px-6 py-12">

      <!-- Hero -->
      <div class="mb-10">
        <h1 class="text-3xl font-bold text-white mb-3">Is your code in here?</h1>
        <p class="text-slate-400 text-base leading-relaxed">
          Clone.dna mints LoRA adapters from public, permissively-licensed GitHub repositories.
          Enter your GitHub handle to see if a .dna block has been trained on your work —
          and revoke it immediately if you'd like.
        </p>
      </div>

      <!-- Search -->
      <div class="flex gap-3 mb-8">
        <div class="relative flex-1">
          <span class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-600 text-sm">@</span>
          <input
            v-model="handleInput"
            type="text"
            placeholder="your-github-handle"
            class="w-full pl-8 pr-4 py-3 bg-slate-900 border border-slate-700 focus:border-blue-500 text-white placeholder-slate-600 text-sm outline-none transition-colors"
            @keydown="handleKeydown"
          />
        </div>
        <button
          class="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-sm transition-colors disabled:opacity-40"
          :disabled="loading || !handleInput.trim()"
          @click="lookup"
        >
          {{ loading ? 'Searching...' : 'Look Up' }}
        </button>
      </div>

      <!-- Error -->
      <p v-if="lookupError" class="text-red-400 text-sm mb-6">{{ lookupError }}</p>

      <!-- Results -->
      <div v-if="result">

        <!-- Not found -->
        <div v-if="!result.blocks.length" class="border border-dashed border-slate-700 bg-slate-900/40 p-12 text-center">
          <p class="text-2xl mb-3">✓</p>
          <p class="text-white font-semibold mb-1">No blocks found for @{{ result.handle }}</p>
          <p class="text-slate-500 text-sm">{{ result.message }}</p>
        </div>

        <!-- Found blocks -->
        <div v-else class="space-y-4">
          <div class="flex items-center justify-between mb-2">
            <p class="text-white font-semibold">
              {{ result.total }} block{{ result.total !== 1 ? 's' : '' }} found for <span class="text-blue-400">@{{ result.handle }}</span>
            </p>
          </div>

          <p v-if="revokeError" class="text-red-400 text-sm">{{ revokeError }}</p>

          <div
            v-for="block in result.blocks"
            :key="block.team_id"
            class="border p-5 transition-colors"
            :class="block.revoked ? 'border-slate-800 bg-slate-900/20 opacity-60' : 'border-slate-700 bg-slate-900/60'"
          >
            <div class="flex items-start justify-between mb-4">
              <div>
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-white font-semibold text-sm">{{ block.handle }}-dna</span>
                  <span class="text-xs border px-1.5 py-0.5"
                    :class="block.revoked ? 'border-slate-600 text-slate-500' : 'border-green-700 text-green-400'">
                    v{{ block.version }}
                  </span>
                  <span v-if="block.revoked" class="text-xs border border-red-800 text-red-500 px-1.5 py-0.5">REVOKED</span>
                </div>
                <p class="text-xs text-slate-500">Team {{ block.team_id }} · Minted {{ formatDate(block.created) }}</p>
              </div>
              <button
                v-if="!block.revoked && block.revocable"
                class="text-xs border border-red-800 text-red-500 px-3 py-1.5 hover:bg-red-950/60 transition-colors disabled:opacity-40"
                :disabled="revoking === block.team_id"
                @click="revoke(block)"
              >
                {{ revoking === block.team_id ? 'Revoking...' : 'Revoke Block' }}
              </button>
              <span v-else-if="block.revoked" class="text-xs text-slate-600">Revoked {{ formatDate(block.revoked_at) }}</span>
            </div>

            <!-- Consent details -->
            <div class="grid grid-cols-2 gap-3 text-xs mb-4">
              <div>
                <p class="text-slate-600 mb-0.5">Consent Basis</p>
                <p class="text-slate-400">{{ block.consent_status === 'implicit_public' ? 'Public repos (MIT/Apache-2.0)' : block.consent_status }}</p>
              </div>
              <div>
                <p class="text-slate-600 mb-0.5">License Verified</p>
                <p :class="block.consent_verified ? 'text-green-400' : 'text-amber-400'">
                  {{ block.consent_verified ? '✓ Verified permissive' : '⚠ Pre-verification block' }}
                </p>
              </div>
              <div>
                <p class="text-slate-600 mb-0.5">Base Model</p>
                <p class="text-slate-400 font-mono text-[11px] break-all">{{ block.base_model || '—' }}</p>
              </div>
              <div>
                <p class="text-slate-600 mb-0.5">Revocable</p>
                <p class="text-slate-400">{{ block.revocable ? 'Yes — self-service' : 'Contact team' }}</p>
              </div>
            </div>

            <!-- Source repos -->
            <div v-if="block.source_urls.length">
              <p class="text-xs text-slate-600 mb-1.5">Trained from</p>
              <div class="space-y-1">
                <a
                  v-for="url in block.source_urls"
                  :key="url"
                  :href="url"
                  target="_blank"
                  rel="noopener"
                  class="text-xs text-blue-500 hover:text-blue-400 transition-colors block truncate"
                >{{ url }}</a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Info section (empty state) -->
      <div v-if="!result && !loading" class="mt-12 border-t border-slate-800 pt-10 grid grid-cols-3 gap-6 text-sm">
        <div>
          <p class="text-slate-300 font-semibold mb-1">What gets trained?</p>
          <p class="text-slate-500 text-xs leading-relaxed">Only public repositories carrying an MIT or Apache-2.0 license. Private repos are never accessed.</p>
        </div>
        <div>
          <p class="text-slate-300 font-semibold mb-1">Can I opt out?</p>
          <p class="text-slate-500 text-xs leading-relaxed">Yes — revoke any block instantly. It's removed from all registry listings, search, and downloads immediately.</p>
        </div>
        <div>
          <p class="text-slate-300 font-semibold mb-1">What's stored?</p>
          <p class="text-slate-500 text-xs leading-relaxed">LoRA adapter weights (no raw code) plus a manifest, sources list, and consent record — all auditable.</p>
        </div>
      </div>

    </main>
  </div>
</template>
