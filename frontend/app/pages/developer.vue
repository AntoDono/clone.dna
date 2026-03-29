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
  <div style="min-height:100vh; background:var(--bg);">

    <!-- Header -->
    <header class="page-header">
      <div class="dev-header-left">
        <NuxtLink to="/" class="logo font-display">Clone.dna</NuxtLink>
        <span class="header-sep">/</span>
        <span class="header-page">Developer Portal</span>
      </div>
      <nav class="header-right">
        <NuxtLink to="/registry" class="nav-link">Registry</NuxtLink>
        <NuxtLink to="/" class="nav-link">Workspace</NuxtLink>
      </nav>
    </header>

    <main class="dev-main">

      <!-- Page title -->
      <div class="dev-hero animate-in">
        <div class="accent-bar" style="margin-bottom:20px;"></div>
        <h1 class="dev-title font-display">Is your code in here?</h1>
        <p class="dev-body">
          Clone.dna trains LoRA adapters exclusively from public, MIT/Apache-2.0 licensed repositories.
          Enter your GitHub handle to audit whether a .dna block exists for your work —
          and revoke it instantly if you'd like.
        </p>
      </div>

      <!-- Search row -->
      <div class="dev-search animate-in" style="animation-delay:60ms;">
        <div class="search-handle-wrap">
          <span class="handle-at font-mono">@</span>
          <input
            v-model="handleInput"
            type="text"
            placeholder="your-github-handle"
            class="input handle-input"
            @keydown="handleKeydown"
          />
        </div>
        <button
          class="btn btn-primary"
          style="white-space:nowrap; padding:10px 24px;"
          :disabled="loading || !handleInput.trim()"
          @click="lookup"
        >
          <span v-if="loading" class="streaming-dot"></span>
          {{ loading ? 'Searching…' : 'Look Up' }}
        </button>
      </div>

      <!-- Lookup error -->
      <div v-if="lookupError" class="error-callout" style="margin-bottom:16px;">{{ lookupError }}</div>

      <!-- Results -->
      <div v-if="result" class="dev-results animate-in">

        <!-- Not found -->
        <div v-if="!result.blocks.length" class="state-clean card">
          <div class="clean-check">✓</div>
          <p class="clean-title">No blocks found for <span class="font-mono">@{{ result.handle }}</span></p>
          <p class="clean-body">{{ result.message }}</p>
        </div>

        <!-- Found blocks -->
        <template v-else>
          <div class="results-meta">
            <span class="results-count">
              <strong>{{ result.total }}</strong> block{{ result.total !== 1 ? 's' : '' }} found for
              <span class="font-mono" style="color:var(--accent);">@{{ result.handle }}</span>
            </span>
            <div v-if="revokeError" class="error-callout" style="font-size:12px; padding:6px 12px;">{{ revokeError }}</div>
          </div>

          <div class="blocks-list stagger">
            <div
              v-for="block in result.blocks"
              :key="block.team_id"
              class="block-row card animate-in"
              :class="{ 'block-row--revoked': block.revoked }"
            >
              <div class="block-row-top">
                <div class="block-row-left">
                  <div class="block-row-title">
                    <span class="font-mono block-handle-name">{{ block.handle }}-dna</span>
                    <span class="pill" :class="block.revoked ? '' : 'pill-green'">v{{ block.version }}</span>
                    <span v-if="block.revoked" class="pill" style="border-color:#FECACA; background:#FEF2F2; color:var(--red);">REVOKED</span>
                  </div>
                  <p class="block-row-meta">Team {{ block.team_id }} · Minted {{ formatDate(block.created) }}</p>
                </div>
                <div>
                  <button
                    v-if="!block.revoked && block.revocable"
                    class="btn btn-danger"
                    style="font-size:12px;"
                    :disabled="revoking === block.team_id"
                    @click="revoke(block)"
                  >
                    {{ revoking === block.team_id ? 'Revoking…' : 'Revoke Block' }}
                  </button>
                  <span v-else-if="block.revoked" style="font-size:12px; color:var(--text-muted);">
                    Revoked {{ formatDate(block.revoked_at) }}
                  </span>
                </div>
              </div>

              <hr class="divider" />

              <div class="block-row-details">
                <div class="detail-cell">
                  <span class="detail-lbl">Consent Basis</span>
                  <span class="detail-val">{{ block.consent_status === 'implicit_public' ? 'Public MIT/Apache-2.0' : block.consent_status }}</span>
                </div>
                <div class="detail-cell">
                  <span class="detail-lbl">License</span>
                  <span class="detail-val" :style="block.consent_verified ? 'color:var(--accent)' : 'color:#92400E'">
                    {{ block.consent_verified ? '✓ Verified permissive' : '⚠ Pre-verification' }}
                  </span>
                </div>
                <div class="detail-cell">
                  <span class="detail-lbl">Base Model</span>
                  <span class="detail-val font-mono" style="font-size:11px; word-break:break-all;">{{ block.base_model || '—' }}</span>
                </div>
                <div class="detail-cell">
                  <span class="detail-lbl">Revocable</span>
                  <span class="detail-val">{{ block.revocable ? 'Yes — self-service' : 'Contact team' }}</span>
                </div>
              </div>

              <div v-if="block.source_urls.length" class="block-sources">
                <span class="detail-lbl">Trained from</span>
                <div class="sources-list">
                  <a
                    v-for="url in block.source_urls"
                    :key="url"
                    :href="url"
                    target="_blank"
                    rel="noopener"
                    class="source-link font-mono"
                  >{{ url }}</a>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Info grid (empty state) -->
      <div v-if="!result && !loading" class="info-grid animate-in" style="animation-delay:120ms;">
        <hr class="divider" style="margin-bottom:40px;" />
        <div class="info-cells">
          <div v-for="item in infoItems" :key="item.title" class="info-cell">
            <p class="info-title">{{ item.title }}</p>
            <p class="info-body">{{ item.body }}</p>
          </div>
        </div>
      </div>

    </main>
  </div>
</template>

<script lang="ts">
export default {
  data() {
    return {
      infoItems: [
        { title: 'What gets trained?', body: 'Only public repositories carrying an MIT or Apache-2.0 license. Private repos are never accessed.' },
        { title: 'Can I opt out?', body: 'Yes — revoke any block instantly. It is removed from all registry listings, search, and downloads immediately.' },
        { title: 'What\'s stored?', body: 'LoRA adapter weights (no raw code) plus a manifest, sources list, and consent record — all auditable.' },
      ],
    }
  },
}
</script>

<style scoped>
.logo { font-size: 18px; font-weight: 400; color: var(--text-primary); letter-spacing: -0.02em; text-decoration: none; }
.header-sep { color: var(--border-mid); margin: 0 10px; }
.header-page { font-size: 13px; color: var(--text-muted); }
.dev-header-left { display: flex; align-items: center; }
.header-right { display: flex; gap: 4px; align-items: center; }

.dev-main { max-width: 720px; margin: 0 auto; padding: 52px 32px 80px; }

.dev-hero { margin-bottom: 36px; }
.dev-title { font-size: 36px; font-weight: 400; letter-spacing: -0.03em; color: var(--text-primary); margin-bottom: 14px; line-height: 1.15; }
.dev-body { font-size: 15px; color: var(--text-secondary); line-height: 1.65; max-width: 560px; }

.dev-search {
  display: flex;
  gap: 10px;
  margin-bottom: 28px;
}
.search-handle-wrap {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
}
.handle-at {
  position: absolute;
  left: 12px;
  color: var(--text-muted);
  font-size: 14px;
  pointer-events: none;
}
.handle-input { padding-left: 30px; }

.dev-results { margin-top: 8px; }

.state-clean {
  padding: 48px 32px;
  text-align: center;
}
.clean-check { font-size: 28px; margin-bottom: 12px; color: var(--accent); }
.clean-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.clean-body { font-size: 13px; color: var(--text-muted); }

.results-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.results-count { font-size: 14px; color: var(--text-secondary); }
.results-count strong { color: var(--text-primary); }

.blocks-list { display: flex; flex-direction: column; gap: 12px; }

.block-row {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  transition: opacity 0.2s;
}
.block-row--revoked { opacity: 0.55; }
.block-row-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.block-row-left { display: flex; flex-direction: column; gap: 4px; }
.block-row-title { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.block-handle-name { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.block-row-meta { font-size: 12px; color: var(--text-muted); }

.block-row-details { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.detail-cell { display: flex; flex-direction: column; gap: 3px; }
.detail-lbl { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }
.detail-val { font-size: 13px; color: var(--text-primary); }

.block-sources { display: flex; flex-direction: column; gap: 6px; }
.sources-list { display: flex; flex-direction: column; gap: 4px; }
.source-link {
  font-size: 11px;
  color: var(--accent);
  text-decoration: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
}
.source-link:hover { text-decoration: underline; }

.info-grid { margin-top: 40px; }
.info-cells { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
.info-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.info-body { font-size: 12px; color: var(--text-muted); line-height: 1.6; }

.error-callout {
  font-size: 13px;
  color: var(--red);
  background: var(--red-light);
  border: 1px solid #FECACA;
  border-radius: var(--radius);
  padding: 10px 14px;
  margin-bottom: 16px;
}

@media (max-width: 640px) {
  .block-row-details { grid-template-columns: 1fr; }
  .info-cells { grid-template-columns: 1fr; }
  .dev-search { flex-direction: column; }
}
</style>
