<script setup lang="ts">
/**
 * Talent Registry page — browse, search, and download minted .dna blocks.
 * Fetches all blocks from GET /registry and filters client-side by handle, skills, and tags.
 * Expandable block cards show eval metrics (style consistency, domain accuracy, loss).
 * Download link fetches a .zip of the full .dna block from GET /registry/{team_id}/{handle}/download.
 * Revoke button calls DELETE /registry/{team_id}/{handle} to remove a block from the registry.
 */
const config = useRuntimeConfig()
const base = config.public.apiBase
const api = useApi()

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
    perplexity_reduction_ratio?: number
    teacher_model?: string
  }
  training_pairs?: number
}

const blocks = ref<DnaBlock[]>([])
const loading = ref(true)
const search = ref('')
const selectedBlock = ref<DnaBlock | null>(null)
const revoking = ref<string | null>(null)
const revokeError = ref('')

// Import state
const showImport = ref(false)
const importFile = ref<File | null>(null)
const importTeamId = ref('')
const importing = ref(false)
const importError = ref('')
const importSuccess = ref('')
const importFileInput = ref<HTMLInputElement | null>(null)

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

async function revokeBlock(b: DnaBlock) {
  if (!confirm(`Revoke ${b.handle}? This cannot be undone.`)) return
  revoking.value = b.handle
  revokeError.value = ''
  try {
    await api.revokeBlock(b.team_id, b.handle)
    blocks.value = blocks.value.filter(x => !(x.team_id === b.team_id && x.handle === b.handle))
    if (selectedBlock.value?.handle === b.handle) selectedBlock.value = null
  } catch {
    revokeError.value = `Failed to revoke ${b.handle}`
    setTimeout(() => { revokeError.value = '' }, 5000)
  } finally {
    revoking.value = null
  }
}

function openImport() {
  showImport.value = true
  importFile.value = null
  importTeamId.value = ''
  importError.value = ''
  importSuccess.value = ''
}

function closeImport() {
  if (importing.value) return
  showImport.value = false
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  importFile.value = input.files?.[0] ?? null
  importError.value = ''
  importSuccess.value = ''
}

async function doImport() {
  if (!importFile.value) { importError.value = 'Please select a .dna zip file.'; return }
  if (!importTeamId.value.trim()) { importError.value = 'Please enter a team ID.'; return }
  importing.value = true
  importError.value = ''
  importSuccess.value = ''
  try {
    const result = await api.importBlock(importFile.value, importTeamId.value.trim())
    importSuccess.value = `Imported @${result.handle} → team ${result.team_id} (${result.files} files)`
    await fetchBlocks()
    setTimeout(() => { showImport.value = false; importSuccess.value = '' }, 2500)
  } catch (err: unknown) {
    const msg = (err as { data?: { detail?: string } })?.data?.detail
    importError.value = msg || 'Import failed. Check the zip is a valid .dna block.'
  } finally {
    importing.value = false
  }
}

onMounted(fetchBlocks)
</script>

<template>
  <div class="bg-[var(--bg)]">

    <!-- Main -->
    <main class="reg-main">

      <!-- Page title + search row -->
      <div class="reg-top">
        <div>
          <h1 class="reg-title font-display">DNA Registry</h1>
          <p class="reg-subtitle">Browse, download, and manage minted .dna blocks</p>
        </div>
        <div class="reg-top-right">
          <div class="reg-search-wrap">
            <svg class="search-icon" width="14" height="14" viewBox="0 0 16 16" fill="none">
              <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" stroke-width="1.5"/>
              <path d="M10.5 10.5L14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            <input
              v-model="search"
              type="text"
              placeholder="Search by handle, skill, or domain…"
              class="reg-search"
            />
          </div>
          <button class="btn btn-primary" style="font-size:13px; white-space:nowrap;" @click="openImport">
            ↑ Import .dna
          </button>
        </div>
      </div>

      <!-- Error -->
      <div v-if="revokeError" class="error-callout" style="margin-bottom:16px;">{{ revokeError }}</div>

      <!-- Loading -->
      <div v-if="loading" class="state-row">
        <span class="streaming-dot"></span>
        <span style="color:var(--text-muted); font-size:14px;">Loading registry…</span>
      </div>

      <!-- Empty -->
      <div v-else-if="!blocks.length" class="state-empty">
        <p class="empty-title">Registry is empty</p>
        <p class="empty-sub">Clone a team's DNA to populate the registry.</p>
      </div>

      <!-- No results -->
      <p v-else-if="!filtered.length" style="color:var(--text-muted); font-size:14px;">
        No blocks match "{{ search }}"
      </p>

      <!-- Grid -->
      <div v-else class="reg-grid stagger">
        <div
          v-for="block in filtered"
          :key="`${block.team_id}-${block.handle}`"
          class="block-card card animate-in"
          :class="{ 'block-card--open': selectedBlock?.handle === block.handle }"
          @click="selectedBlock = selectedBlock?.handle === block.handle ? null : block"
        >
          <!-- Card top -->
          <div class="block-header">
            <div class="block-identity">
              <span class="block-handle font-mono">@{{ block.handle }}</span>
              <span class="block-name">{{ block.name }}</span>
            </div>
            <span class="pill pill-green">v{{ block.version || '1.0.0' }}</span>
          </div>

          <!-- Domains -->
          <div v-if="block.expertise_domains.length" class="block-domains">
            <span
              v-for="domain in block.expertise_domains.slice(0, 4)"
              :key="domain"
              class="pill"
            >{{ domain }}</span>
          </div>

          <!-- Metrics row -->
          <div class="block-metrics">
            <div class="metric">
              <span class="metric-label">Style</span>
              <span class="metric-value">{{ formatScore(block.eval_summary.style_consistency) }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">Domain</span>
              <span class="metric-value">{{ formatScore(block.eval_summary.domain_accuracy) }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">PPL ×</span>
              <span
                class="metric-value"
                :style="block.eval_summary.perplexity_reduction_ratio && block.eval_summary.perplexity_reduction_ratio > 1 ? 'color:var(--accent)' : ''"
              >
                {{ block.eval_summary.perplexity_reduction_ratio ? `×${block.eval_summary.perplexity_reduction_ratio.toFixed(2)}` : '—' }}
              </span>
            </div>
            <div class="metric">
              <span class="metric-label">Loss</span>
              <span class="metric-value">{{ formatLoss(block.eval_summary.best_loss || block.eval_summary.final_loss) }}</span>
            </div>
          </div>

          <!-- Footer -->
          <div class="block-footer">
            <span class="block-pairs font-mono">{{ block.training_pairs || '—' }} pairs</span>
            <span class="block-date">{{ formatDate(block.created) }}</span>
          </div>

          <!-- Expanded detail -->
          <Transition name="expand">
            <div v-if="selectedBlock?.handle === block.handle" class="block-detail" @click.stop>
              <hr class="divider" style="margin-bottom:16px;" />
              <div class="detail-grid">
                <div class="detail-row">
                  <span class="detail-label">Base Model</span>
                  <span class="detail-val font-mono" style="font-size:11px; word-break:break-all;">{{ block.base_model }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">Latency</span>
                  <span class="detail-val">{{ block.eval_summary.latency_overhead_ms ? block.eval_summary.latency_overhead_ms + ' ms' : '—' }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">Teacher</span>
                  <span class="detail-val">{{ block.eval_summary.teacher_model || '—' }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">vLLM</span>
                  <span class="detail-val" :style="block.vllm_compatible ? 'color:var(--accent)' : ''">
                    {{ block.vllm_compatible ? '✓ Compatible' : 'No' }}
                  </span>
                </div>
              </div>

              <div v-if="block.tags.length" class="block-tags">
                <span v-for="tag in block.tags" :key="tag" class="pill font-mono">{{ tag }}</span>
              </div>

              <div class="block-actions">
                <a :href="downloadUrl(block)" class="btn btn-primary" style="font-size:13px;" @click.stop>
                  ↓ Download .dna
                </a>
                <button
                  class="btn btn-danger"
                  style="font-size:13px;"
                  :disabled="revoking === block.handle"
                  @click.stop="revokeBlock(block)"
                >
                  {{ revoking === block.handle ? 'Revoking…' : 'Revoke Block' }}
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </div>

      <!-- Count -->
      <p v-if="blocks.length && !loading" class="reg-count font-mono">
        {{ filtered.length }} / {{ blocks.length }} blocks
      </p>
    </main>

    <!-- Import modal -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showImport" class="modal-backdrop" @click.self="closeImport">
          <div class="modal-box card" @click.stop>
            <div class="modal-header">
              <span class="modal-title font-display">Import .dna Block</span>
              <button class="modal-close" :disabled="importing" @click="closeImport">✕</button>
            </div>

            <p class="modal-desc">
              Upload a <span class="font-mono">.dna</span> zip archive exported from any Clone.dna registry.
              The block will be registered under the team ID you specify.
            </p>

            <!-- File drop zone -->
            <label class="drop-zone" :class="{ 'drop-zone--has-file': importFile }">
              <input
                ref="importFileInput"
                type="file"
                accept=".zip"
                style="display:none"
                @change="onFileChange"
              />
              <div v-if="!importFile" class="drop-inner">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                <span>Click to select a .dna zip file</span>
              </div>
              <div v-else class="drop-inner drop-inner--selected">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <span class="font-mono" style="font-size:13px;">{{ importFile.name }}</span>
                <span style="font-size:11px; color:var(--text-muted);">{{ (importFile.size / 1024).toFixed(0) }} KB</span>
              </div>
            </label>

            <div class="modal-field">
              <label class="field-label">Target Team ID</label>
              <input
                v-model="importTeamId"
                type="text"
                class="reg-search"
                style="width:100%; padding-left:14px;"
                placeholder="e.g. 1"
                :disabled="importing"
              />
              <span class="field-hint">The block will be stored under <span class="font-mono">dnas/{team_id}/{handle}/</span></span>
            </div>

            <div v-if="importError" class="error-callout">{{ importError }}</div>
            <div v-if="importSuccess" class="success-callout">{{ importSuccess }}</div>

            <div class="modal-actions">
              <button class="btn" :disabled="importing" @click="closeImport">Cancel</button>
              <button
                class="btn btn-primary"
                :disabled="importing || !importFile"
                @click="doImport"
              >
                {{ importing ? 'Importing…' : 'Import Block' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* Page layout */
.reg-main { max-width: 960px; margin: 0 auto; padding: 40px 32px 80px; }
.reg-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
  flex-wrap: wrap;
}
.reg-title { font-size: 30px; font-weight: 400; letter-spacing: -0.02em; color: var(--text-primary); }
.reg-subtitle { font-size: 14px; color: var(--text-muted); margin-top: 4px; }
.reg-search-wrap {
  position: relative;
  display: flex;
  align-items: center;
}
.search-icon {
  position: absolute;
  left: 12px;
  color: var(--text-muted);
  pointer-events: none;
}
.reg-search {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-family: var(--font-ui);
  font-size: 13px;
  padding: 9px 14px 9px 34px;
  width: 280px;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.reg-search::placeholder { color: var(--text-muted); }
.reg-search:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(22,101,52,0.08);
}

/* States */
.state-row { display: flex; align-items: center; gap: 10px; padding: 32px 0; }
.state-empty {
  border: 1px dashed var(--border);
  background: var(--bg-card);
  border-radius: var(--radius);
  padding: 64px 32px;
  text-align: center;
}
.empty-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.empty-sub { font-size: 13px; color: var(--text-muted); }

/* Grid */
.reg-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}
.reg-count {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 20px;
  letter-spacing: 0.04em;
}

/* Block card */
.block-card {
  padding: 20px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
}
.block-card:hover { transform: translateY(-1px); }
.block-card--open { border-color: var(--accent) !important; }

.block-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}
.block-identity { display: flex; flex-direction: column; gap: 2px; }
.block-handle { font-size: 14px; font-weight: 500; color: var(--text-primary); }
.block-name { font-size: 12px; color: var(--text-muted); }

.block-domains { display: flex; flex-wrap: wrap; gap: 5px; }

.block-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  padding: 12px 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.metric { display: flex; flex-direction: column; gap: 3px; }
.metric-label { font-size: 10px; color: var(--text-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }
.metric-value { font-size: 13px; font-weight: 600; color: var(--text-primary); }

.block-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.block-pairs { font-size: 11px; color: var(--text-muted); }
.block-date { font-size: 12px; color: var(--text-muted); }

/* Expanded detail */
.block-detail { display: flex; flex-direction: column; gap: 12px; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.detail-row { display: flex; flex-direction: column; gap: 3px; }
.detail-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }
.detail-val { font-size: 13px; color: var(--text-primary); }
.block-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.block-actions { display: flex; gap: 10px; padding-top: 4px; flex-wrap: wrap; }

/* Error */
.error-callout {
  font-size: 13px;
  color: var(--red);
  background: var(--red-light);
  border: 1px solid #FECACA;
  border-radius: var(--radius);
  padding: 10px 14px;
}

/* Expand transition */
.expand-enter-active, .expand-leave-active { transition: all 0.2s ease; overflow: hidden; }
.expand-enter-from, .expand-leave-to { opacity: 0; max-height: 0; }
.expand-enter-to, .expand-leave-from { opacity: 1; max-height: 600px; }

/* Top-right row with search + import button */
.reg-top-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* Import modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 16px;
}
.modal-box {
  width: 100%;
  max-width: 460px;
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.modal-title { font-size: 18px; font-weight: 400; color: var(--text-primary); }
.modal-close {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 16px;
  padding: 4px 8px;
  border-radius: var(--radius);
  transition: background 0.15s;
}
.modal-close:hover { background: var(--border); }
.modal-desc { font-size: 13px; color: var(--text-muted); line-height: 1.6; }

/* Drop zone */
.drop-zone {
  border: 1.5px dashed var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100px;
}
.drop-zone:hover, .drop-zone--has-file { border-color: var(--accent); }
.drop-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-muted);
  font-size: 13px;
  padding: 20px;
}
.drop-inner--selected { color: var(--accent); }

/* Field */
.modal-field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); }
.field-hint { font-size: 11px; color: var(--text-muted); }

/* Success */
.success-callout {
  font-size: 13px;
  color: var(--accent);
  background: rgba(22,101,52,0.08);
  border: 1px solid rgba(22,101,52,0.2);
  border-radius: var(--radius);
  padding: 10px 14px;
}

.modal-actions { display: flex; gap: 10px; justify-content: flex-end; }

/* Fade transition for modal */
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
