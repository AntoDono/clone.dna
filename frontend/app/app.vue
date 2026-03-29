<script setup lang="ts">
const emergencyCalibration = useState('emergencyCalibration', () => false)
const route = useRoute()

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Shift' && !e.repeat && !route.path.endsWith('/build')) {
    emergencyCalibration.value = !emergencyCalibration.value
  }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <NuxtLayout>
    <NuxtPage />
  </NuxtLayout>

  <Transition name="ec-dot">
    <div
      v-if="emergencyCalibration"
      class="fixed top-4 right-4 z-[999] w-3 h-3 rounded-full shadow-lg"
      style="background:#F59E0B; box-shadow:0 0 12px rgba(245,158,11,0.4);"
      title="Emergency calibration active"
    />
  </Transition>
</template>

<style>
.ec-dot-enter-active,
.ec-dot-leave-active { transition: opacity 0.15s, transform 0.15s; }
.ec-dot-enter-from,
.ec-dot-leave-to { opacity: 0; transform: scale(0); }
</style>
