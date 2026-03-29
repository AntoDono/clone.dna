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

const BADGE_COLOR: Record<string, string> = {
  pm:       'bg-amber-950/40 text-amber-400 border-amber-700',
  swe:      'bg-blue-950/40 text-blue-400 border-blue-700',
  designer: 'bg-purple-950/40 text-purple-400 border-purple-700',
}
</script>

<template>
  <div
    class="bg-slate-900/60 border transition-colors p-5"
    :class="slot.filled ? 'border-green-600' : isActive ? 'border-blue-500' : 'border-slate-800 hover:border-slate-600'"
  >
    <!-- Badge + status -->
    <div class="flex items-center justify-between mb-3">
      <span class="text-xs font-medium border px-2 py-0.5" :class="BADGE_COLOR[slot.role]">
        {{ meta.badge }}{{ slot.slot_index > 0 ? ` #${slot.slot_index + 1}` : '' }}
      </span>
      <span v-if="slot.filled" class="text-xs text-green-400 font-medium">✓ Filled</span>
      <span v-else-if="isScanning || isExtracting" class="text-xs text-blue-400 animate-pulse">
        {{ isExtracting ? 'Extracting...' : 'Scanning...' }}
      </span>
    </div>

    <!-- Role name -->
    <h3 class="font-semibold text-white mb-0.5">{{ meta.label }}</h3>
    <p class="text-xs text-slate-500">{{ meta.desc }}</p>

    <!-- FILLED -->
    <div v-if="slot.filled && slot.candidate" class="mt-4 pt-4 border-t border-slate-800">
      <div class="flex items-center gap-2.5 mb-2">
        <img
          v-if="slot.candidate.avatar_url"
          :src="slot.candidate.avatar_url"
          :alt="slot.candidate.name"
          class="w-8 h-8 border border-slate-700 object-cover flex-shrink-0"
        />
        <div
          v-else
          class="w-8 h-8 border border-slate-700 bg-slate-800 flex items-center justify-center text-sm font-semibold text-slate-400 flex-shrink-0"
        >
          {{ (slot.candidate.name ?? '?')[0]?.toUpperCase() }}
        </div>
        <div class="min-w-0">
          <p class="font-medium text-sm text-white truncate">{{ slot.candidate.name }}</p>
          <p class="text-xs text-slate-500 truncate">{{ slot.candidate.location || slot.candidate.profile_url }}</p>
        </div>
      </div>
      <p v-if="slot.candidate.description" class="text-xs text-slate-400 mb-2 leading-relaxed">
        {{ slot.candidate.description }}
      </p>
      <div class="flex flex-wrap gap-1">
        <span
          v-for="skill in (slot.candidate.soft_skills?.length ? slot.candidate.soft_skills : slot.candidate.skills).slice(0, 3)"
          :key="skill"
          class="text-xs border border-slate-700 text-slate-500 px-2 py-0.5"
        >{{ skill }}</span>
      </div>
      <div class="mt-3 flex gap-2">
        <a
          v-if="slot.candidate.dna_cloned"
          :href="`${useRuntimeConfig().public.apiBase}/registry/${teamId}/${slot.candidate.github_handle}/download`"
          download
          class="flex-1 text-xs text-green-400 border border-green-700 py-1.5 text-center hover:bg-green-950/40 transition-colors"
        >
          ↓ .dna
        </a>
        <button
          class="flex-1 text-xs text-slate-500 border border-slate-700 py-1.5 hover:border-red-700 hover:text-red-400 transition-colors"
          @click="emit('remove')"
        >
          Remove
        </button>
      </div>
    </div>

    <!-- EMPTY -->
    <div v-else class="mt-4 space-y-2">
      <!-- Primary: GitHub -->
      <button
        class="w-full border border-blue-500 text-blue-400 text-sm py-2 font-medium hover:bg-blue-600 hover:text-white transition-colors disabled:opacity-40"
        :disabled="isScanning || isExtracting"
        @click="inputMode = null; emit('scan')"
      >
        {{ isScanning ? 'Scanning GitHub...' : 'Scan GitHub' }}
      </button>

      <!-- Secondary row -->
      <div class="grid grid-cols-2 gap-2">
        <button
          class="text-xs border py-2 transition-colors"
          :class="inputMode === 'website'
            ? 'border-blue-500 text-blue-400 bg-blue-950/40'
            : 'border-slate-700 text-slate-500 hover:border-blue-600'"
          :disabled="isScanning || isExtracting"
          @click="inputMode === 'website' ? closeInput() : openInput('website')"
        >
          Website URL
        </button>
        <button
          class="text-xs border py-2 transition-colors"
          :class="inputMode === 'resume'
            ? 'border-amber-500 text-amber-400 bg-amber-950/40'
            : 'border-slate-700 text-slate-500 hover:border-amber-600'"
          :disabled="isScanning || isExtracting"
          @click="inputMode === 'resume' ? closeInput() : openInput('resume')"
        >
          Paste Resume
        </button>
      </div>

      <!-- Inline input -->
      <div v-if="inputMode" class="border border-slate-700 bg-slate-900/40 p-3 space-y-2">
        <p class="text-xs font-medium text-slate-400 uppercase tracking-wide">
          {{ inputMode === 'website' ? 'Website URL' : 'Resume Text' }}
        </p>

        <input
          v-if="inputMode === 'website'"
          :id="`inp-${slot.id}-website`"
          v-model="inputValue"
          type="url"
          placeholder="https://..."
          class="w-full border border-slate-700 focus:border-blue-500 bg-slate-800 text-white placeholder-slate-600 px-3 py-2 text-sm outline-none"
          @keydown.enter="runExtraction"
          @keydown.esc="closeInput"
        />
        <textarea
          v-else
          :id="`inp-${slot.id}-resume`"
          v-model="inputValue"
          rows="4"
          placeholder="Paste resume text here..."
          class="w-full border border-slate-700 focus:border-amber-500 bg-slate-800 text-white placeholder-slate-600 px-3 py-2 text-sm outline-none resize-none"
          @keydown.esc="closeInput"
        ></textarea>

        <div class="flex gap-2">
          <button
            class="flex-1 text-xs border border-slate-700 text-slate-500 py-1.5 hover:border-slate-500 hover:text-slate-300 transition-colors"
            @click="closeInput"
          >Cancel</button>
          <button
            class="flex-1 text-xs border py-1.5 font-medium transition-colors disabled:opacity-40"
            :class="inputMode === 'website'
              ? 'border-blue-500 text-blue-400 hover:bg-blue-600 hover:text-white'
              : 'border-amber-500 text-amber-400 hover:bg-amber-500 hover:text-white'"
            :disabled="!inputValue.trim() || isExtracting"
            @click="runExtraction"
          >
            {{ isExtracting ? 'Extracting...' : 'Extract' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
