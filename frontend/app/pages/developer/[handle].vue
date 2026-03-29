<script setup lang="ts">
/**
 * Developer self-service portal — given a GitHub handle, shows every .dna block
 * minted from that developer's public repos, along with consent status, source repos,
 * and a revocation button to remove blocks from the registry.
 *
 * Route: /developer/:handle
 * Backend: GET /registry/developer/{handle}  →  list of DnaBlock records
 *          DELETE /registry/{team_id}/{handle}  →  revoke a block
 */
import type { DnaBlock } from '~/composables/useApi'

const route = useRoute()
const handle = route.params.handle as string

const api = useApi()

const loading = ref(true)
const error = ref('')
const result = ref<{ handle: string; total: number; blocks: DnaBlock[]; message: string } | null>(null)
const revoking = ref<Record<string, boolean>>({})
const revokeErrors = ref<Record<string, string>>({})

onMounted(async () => {
  try {
    result.value = await api.developerLookup(handle)
  } catch (e: any) {
    error.value = e?.data?.detail ?? e?.message ?? 'Failed to load developer data.'
  } finally {
    loading.value = false
  }
})

async function revokeBlock(block: DnaBlock) {
  const key = `${block.team_id}/${block.handle}`
  revoking.value[key] = true
  revokeErrors.value[key] = ''
  try {
    await api.revokeBlock(block.team_id, block.handle)
    // Mark revoked in local state
    if (result.value) {
      const b = result.value.blocks.find(b => b.team_id === block.team_id && b.handle === block.handle)
      if (b) { b.revoked = true; b.revoked_at = new Date().toISOString() }
    }
  } catch (e: any) {
    revokeErrors.value[key] = e?.data?.detail ?? e?.message ?? 'Revocation failed.'
  } finally {
    revoking.value[key] = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-[var(--bg)] px-6 py-10 max-w-3xl mx-auto">

    <!-- Back -->
    <NuxtLink to="/registry" class="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors mb-6 block">← Registry</NuxtLink>

    <!-- Header -->
    <div class="mb-8">
      <h1 class="text-2xl font-bold text-[var(--text-primary)]">@{{ handle }}</h1>
      <p class="text-sm text-[var(--text-muted)] mt-1">Developer DNA audit — view and revoke .dna blocks minted from your public repos.</p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-sm text-[var(--text-muted)]">Loading…</div>

    <!-- Error -->
    <div v-else-if="error" class="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3">{{ error }}</div>

    <!-- No blocks -->
    <div v-else-if="!result || result.total === 0" class="bg-[var(--bg-card)] border border-[var(--border)] rounded-xl px-6 py-8 text-center">
      <p class="text-sm text-[var(--text-secondary)]">{{ result?.message ?? 'No DNA blocks found.' }}</p>
      <p class="text-xs text-[var(--text-muted)] mt-2">If you believe your code has been used without consent, <a href="mailto:privacy@clone.dna" class="underline">contact us</a>.</p>
    </div>

    <!-- Blocks list -->
    <div v-else class="space-y-4">
      <p class="text-xs text-[var(--text-muted)] mb-4">{{ result.total }} block{{ result.total === 1 ? '' : 's' }} found</p>

      <div
        v-for="block in result.blocks"
        :key="`${block.team_id}/${block.handle}`"
        class="bg-[var(--bg-card)] border rounded-xl px-5 py-4 space-y-3"
        :class="block.revoked ? 'border-[var(--border)] opacity-60' : 'border-[var(--border-mid)]'"
      >
        <!-- Block header -->
        <div class="flex items-start justify-between gap-4">
          <div>
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-mono text-sm font-semibold text-[var(--text-primary)]">Team #{{ block.team_id }}</span>
              <span class="text-xs px-2 py-0.5 rounded-full border"
                :class="block.revoked
                  ? 'border-red-300 text-red-600 bg-red-50'
                  : block.consent_verified
                    ? 'border-green-300 text-green-700 bg-green-50'
                    : 'border-amber-300 text-amber-700 bg-amber-50'"
              >
                {{ block.revoked ? 'Revoked' : block.consent_verified ? 'Consent Verified' : block.consent_status }}
              </span>
              <span class="text-xs text-[var(--text-muted)]">v{{ block.version }}</span>
            </div>
            <p v-if="block.base_model" class="text-xs text-[var(--text-muted)] mt-1">Base: {{ block.base_model }}</p>
          </div>
          <button
            v-if="!block.revoked && block.revocable"
            @click="revokeBlock(block)"
            :disabled="revoking[`${block.team_id}/${block.handle}`]"
            class="text-xs px-3 py-1.5 rounded border border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-40 transition-colors shrink-0"
          >
            {{ revoking[`${block.team_id}/${block.handle}`] ? 'Revoking…' : 'Revoke Block' }}
          </button>
          <span v-else-if="block.revoked" class="text-xs text-[var(--text-muted)] shrink-0">
            Revoked {{ block.revoked_at ? new Date(block.revoked_at).toLocaleDateString() : '' }}
          </span>
        </div>

        <!-- Source repos -->
        <div v-if="block.source_urls.length" class="pt-1">
          <p class="text-xs text-[var(--text-muted)] mb-1">Trained on:</p>
          <ul class="space-y-0.5">
            <li v-for="url in block.source_urls" :key="url" class="text-xs font-mono text-[var(--text-secondary)]">
              <a :href="url" target="_blank" rel="noopener" class="hover:text-[var(--accent)] hover:underline">{{ url }}</a>
            </li>
          </ul>
        </div>

        <!-- Revoke error -->
        <p v-if="revokeErrors[`${block.team_id}/${block.handle}`]" class="text-xs text-red-600">
          {{ revokeErrors[`${block.team_id}/${block.handle}`] }}
        </p>
      </div>

      <!-- Footer note -->
      <p class="text-xs text-[var(--text-muted)] pt-4">{{ result.message }}</p>
    </div>
  </div>
</template>
