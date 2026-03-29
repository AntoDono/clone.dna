<script setup lang="ts">
/**
 * Root application layout.
 * Manages global emergency calibration state (toggle: press Shift anywhere).
 * Orange dot indicator appears in corner when emergency calibration is active.
 * Emergency calibration enables DNA cloning simulation without a real GPU.
 */
const emergencyCalibration = useState('emergencyCalibration', () => false)

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Shift' && !e.repeat) {
    emergencyCalibration.value = !emergencyCalibration.value
  }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <div class="min-h-screen bg-slate-950">
    <NuxtRouteAnnouncer />
    <NuxtPage />
    <Transition name="ec-dot">
      <div
        v-if="emergencyCalibration"
        class="fixed bottom-4 right-4 z-[999] w-3 h-3 rounded-full bg-orange-500 shadow-lg shadow-orange-500/40"
        title="Emergency calibration active"
      />
    </Transition>
  </div>
</template>

<style>
*, *::before, *::after { box-sizing: border-box; }

body {
  background-color: #020617;
  color: #f1f5f9;
  font-family: 'DM Sans', ui-sans-serif, system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
}

::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #020617; }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #334155; }

.ec-dot-enter-active,
.ec-dot-leave-active { transition: opacity 0.15s, transform 0.15s; }
.ec-dot-enter-from,
.ec-dot-leave-to { opacity: 0; transform: scale(0); }
</style>
