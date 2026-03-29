<script setup lang="ts">
/**
 * Individual role slot card (PM / SWE / Designer).
 * Filled state: shows candidate avatar, name, description, skills, and action buttons.
 * Empty state: three input methods — GitHub scan trigger, website URL extraction,
 * or resume text paste.
 *
 * Props: slot (RoleSlot), meta ({label, badge, desc}), isActive (bool), isScanning (bool), teamId (number)
 * Emits: scan, remove, extracted, error
 */
import type { RoleSlot, CandidateProfile } from '~/composables/useApi'

const props = defineProps<{
  slot: RoleSlot
  meta: { label: string; badge: string; desc: string }
  isActive: boolean
  isScanning: boolean
  teamId: number
}>()

const emit = defineEmits<{
  scan: []
  remove: []
  extracted: [candidate: CandidateProfile]
  error: [msg: string]
}>()

const api = useApi()
const inputMode = ref<null | 'website' | 'resume'>(null)
const inputValue = ref('')
const isExtracting = ref(false)

function openInput(mode: 'website' | 'resume') {
  inputMode.value = mode
  inputValue.value = ''
  nextTick(() => document.getElementById(`inp-${props.slot.id}-${mode}`)?.focus())
}

function closeInput() {
  inputMode.value = null
  inputValue.value = ''
}

async function runExtraction() {
  const val = inputValue.value.trim()
  if (!val || isExtracting.value) return
  isExtracting.value = true
  try {
    const result = inputMode.value === 'website'
      ? await api.extractFromWebsite(props.teamId, props.slot.id, val)
      : await api.extractFromResume(props.teamId, props.slot.id, val)
    closeInput()
    emit('extracted', result)
  } catch (e: any) {
    emit('error', e?.data?.detail ?? e?.message ?? 'Extraction failed.')
  } finally {
    isExtracting.value = false
  }
}

const ROLE_BADGE: Record<string, { bg: string; text: string; border: string }> = {
  pm:       { bg: '#FFFBEB', text: '#92400E', border: '#FDE68A' },
  swe:      { bg: '#EFF6FF', text: '#1E40AF', border: '#BFDBFE' },
  designer: { bg: '#F5F3FF', text: '#5B21B6', border: '#DDD6FE' },
}
</script>

<template>
  <div
    class="slot-card card"
    :class="{
      'slot-card--filled': slot.filled,
      'slot-card--active': isActive && !slot.filled,
    }"
  >
    <!-- Badge + status row -->
    <div class="slot-top">
      <span
        class="role-badge font-mono"
        :style="{
          background: ROLE_BADGE[slot.role]?.bg ?? '#F3F0EB',
          color: ROLE_BADGE[slot.role]?.text ?? '#6B6050',
          borderColor: ROLE_BADGE[slot.role]?.border ?? '#E2DDD6',
        }"
      >
        {{ meta.badge }}{{ slot.slot_index > 0 ? ` #${slot.slot_index + 1}` : '' }}
      </span>
      <span v-if="slot.filled" class="status-chip status-filled">✓ Filled</span>
      <span v-else-if="isScanning || isExtracting" class="status-chip status-scanning">
        {{ isExtracting ? 'Extracting…' : 'Scanning…' }}
      </span>
    </div>

    <!-- Role name / desc -->
    <div class="slot-role">
      <h3 class="slot-label">{{ meta.label }}</h3>
      <p class="slot-desc">{{ meta.desc }}</p>
    </div>

    <!-- ── FILLED ── -->
    <div v-if="slot.filled && slot.candidate" class="slot-candidate">
      <div class="candidate-header">
        <img
          v-if="slot.candidate.avatar_url"
          :src="slot.candidate.avatar_url"
          :alt="slot.candidate.name"
          class="candidate-avatar"
        />
        <div v-else class="candidate-avatar candidate-avatar--fallback">
          {{ (slot.candidate.name ?? '?')[0]?.toUpperCase() }}
        </div>
        <div class="candidate-info">
          <p class="candidate-name">{{ slot.candidate.name }}</p>
          <p class="candidate-sub font-mono">{{ slot.candidate.location || slot.candidate.profile_url }}</p>
        </div>
      </div>
      <p v-if="slot.candidate.description" class="candidate-desc">
        {{ slot.candidate.description }}
      </p>
      <div class="candidate-skills">
        <span
          v-for="skill in (slot.candidate.soft_skills?.length ? slot.candidate.soft_skills : slot.candidate.skills).slice(0, 3)"
          :key="skill"
          class="pill"
        >{{ skill }}</span>
      </div>
      <div class="candidate-actions">
        <a
          v-if="slot.candidate.dna_cloned"
          :href="`${useRuntimeConfig().public.apiBase}/registry/${teamId}/${slot.candidate.github_handle}/download`"
          download
          class="btn btn-secondary"
          style="font-size:12px; flex:1; justify-content:center;"
        >
          ↓ .dna
        </a>
        <button
          class="btn btn-ghost"
          style="font-size:12px; flex:1; color:#991B1B;"
          @click="emit('remove')"
        >
          Remove
        </button>
      </div>
    </div>

    <!-- ── EMPTY ── -->
    <div v-else class="slot-empty">
      <button
        class="btn btn-primary scan-btn"
        :disabled="isScanning || isExtracting"
        @click="inputMode = null; emit('scan')"
      >
        <span v-if="isScanning" class="streaming-dot" style="background:#fff;"></span>
        {{ isScanning ? 'Scanning GitHub…' : 'Scan GitHub' }}
      </button>

      <div class="method-row">
        <button
          class="method-btn"
          :class="{ 'method-btn--active-blue': inputMode === 'website' }"
          :disabled="isScanning || isExtracting"
          @click="inputMode === 'website' ? closeInput() : openInput('website')"
        >
          Website URL
        </button>
        <button
          class="method-btn"
          :class="{ 'method-btn--active-amber': inputMode === 'resume' }"
          :disabled="isScanning || isExtracting"
          @click="inputMode === 'resume' ? closeInput() : openInput('resume')"
        >
          Paste Resume
        </button>
      </div>

      <!-- Inline input panel -->
      <div v-if="inputMode" class="input-panel">
        <p class="input-panel-label">{{ inputMode === 'website' ? 'Website URL' : 'Resume Text' }}</p>

        <input
          v-if="inputMode === 'website'"
          :id="`inp-${slot.id}-website`"
          v-model="inputValue"
          type="url"
          placeholder="https://…"
          class="input"
          style="font-size:13px;"
          @keydown.enter="runExtraction"
          @keydown.esc="closeInput"
        />
        <textarea
          v-else
          :id="`inp-${slot.id}-resume`"
          v-model="inputValue"
          rows="4"
          placeholder="Paste resume text here…"
          class="input"
          style="font-size:13px; resize:none;"
          @keydown.esc="closeInput"
        ></textarea>

        <div class="input-panel-actions">
          <button class="btn btn-ghost" style="font-size:12px;" @click="closeInput">Cancel</button>
          <button
            class="btn"
            :class="inputMode === 'website' ? 'btn-primary' : 'btn-amber'"
            style="font-size:12px;"
            :disabled="!inputValue.trim() || isExtracting"
            @click="runExtraction"
          >
            <span v-if="isExtracting" class="streaming-dot" style="background:#fff;"></span>
            {{ isExtracting ? 'Extracting…' : 'Extract' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.slot-card {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.slot-card--filled { border-color: #86EFAC !important; }
.slot-card--active { border-color: #93C5FD !important; }

.slot-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.role-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 2px;
  border: 1px solid;
  letter-spacing: 0.02em;
}
.status-chip {
  font-size: 11px;
  font-weight: 600;
}
.status-filled { color: #166534; }
.status-scanning { color: #1E40AF; }

.slot-role { display: flex; flex-direction: column; gap: 2px; }
.slot-label { font-size: 14px; font-weight: 600; color: #1C1811; }
.slot-desc { font-size: 12px; color: #A8A098; }

/* ── Filled state ── */
.slot-candidate {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 10px;
  border-top: 1px solid #E2DDD6;
}
.candidate-header { display: flex; gap: 10px; align-items: flex-start; }
.candidate-avatar {
  width: 32px;
  height: 32px;
  border: 1px solid #E2DDD6;
  object-fit: cover;
  flex-shrink: 0;
  border-radius: 2px;
}
.candidate-avatar--fallback {
  background: #F3F0EB;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: #6B6050;
  border-radius: 2px;
}
.candidate-info { min-width: 0; }
.candidate-name { font-size: 13px; font-weight: 600; color: #1C1811; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.candidate-sub { font-size: 11px; color: #A8A098; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.candidate-desc { font-size: 12px; color: #6B6050; line-height: 1.5; }
.candidate-skills { display: flex; flex-wrap: wrap; gap: 4px; }
.candidate-actions { display: flex; gap: 8px; }

/* ── Empty state ── */
.slot-empty { display: flex; flex-direction: column; gap: 8px; }
.scan-btn { width: 100%; justify-content: center; font-size: 13px; }
.method-row { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.method-btn {
  font-size: 12px;
  font-weight: 500;
  font-family: 'Outfit', system-ui, sans-serif;
  padding: 7px 8px;
  border-radius: 4px;
  border: 1px solid #E2DDD6;
  background: transparent;
  color: #6B6050;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.method-btn:hover:not(:disabled) { border-color: #CCC7BE; color: #1C1811; background: #F3F0EB; }
.method-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.method-btn--active-blue { border-color: #93C5FD !important; color: #1E40AF !important; background: #EFF6FF !important; }
.method-btn--active-amber { border-color: #FDE68A !important; color: #92400E !important; background: #FFFBEB !important; }

.input-panel {
  background: #F3F0EB;
  border: 1px solid #E2DDD6;
  border-radius: 4px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.input-panel-label { font-size: 11px; font-weight: 700; color: #6B6050; text-transform: uppercase; letter-spacing: 0.06em; }
.input-panel-actions { display: flex; gap: 6px; justify-content: flex-end; }

.btn-amber {
  background: #92400E;
  color: #FFFFFF;
  border-color: #92400E;
}
.btn-amber:hover:not(:disabled) { background: #78350F; }
</style>
