<script setup lang="ts">
const api = useApi()
const router = useRouter()
const route = useRoute()

const username = ref('')

onMounted(() => {
  username.value = api.getUsername() ?? ''
})

function logout() {
  api.logout()
  router.push('/login')
}

// Derive breadcrumb label from route
const pageLabel = computed(() => {
  const p = route.path
  if (p === '/') return 'Workspace'
  if (p === '/registry') return 'Talent Registry'
  if (p === '/developer') return 'Developer Portal'
  if (p.includes('/build')) return 'Build'
  if (p.match(/^\/teams\/\d+/)) return 'Team'
  return ''
})
</script>

<template>
  <div style="min-height:100vh; background:var(--bg);">
    <NuxtRouteAnnouncer />

    <!-- ── Shared Navbar ─────────────────────────────────────────────────────── -->
    <header
      class="sticky top-0 z-40 flex h-14 items-center justify-between px-6 backdrop-blur-md"
      style="background:rgba(250,248,244,0.92); border-bottom:1px solid var(--border);"
    >
      <!-- Left: wordmark + breadcrumb -->
      <div class="flex items-center gap-2 min-w-0">
        <NuxtLink
          to="/"
          class="font-display text-[17px] tracking-tight shrink-0 no-underline"
          style="color:var(--text-primary); letter-spacing:-0.02em;"
        >
          Clone.dna
        </NuxtLink>
        <span v-if="pageLabel" style="color:var(--border-mid); margin:0 2px; user-select:none;">/</span>
        <span
          v-if="pageLabel"
          class="text-[13px] truncate"
          style="color:var(--text-muted);"
        >{{ pageLabel }}</span>
      </div>

      <!-- Right: slot for page-specific controls + common nav -->
      <nav class="flex items-center gap-1 shrink-0">
        <!-- Page-specific header actions injected via layout slot -->
        <slot name="header-actions" />

        <span
          v-if="username"
          class="font-mono text-[11px] rounded-full px-3 py-1 mr-2 max-w-[180px] truncate"
          style="color:var(--text-muted); background:var(--bg-subtle); border:1px solid var(--border);"
        >{{ username }}</span>

        <NuxtLink
          to="/registry"
          class="text-[13px] font-medium rounded px-3 py-1.5 transition-colors"
          style="color:var(--text-secondary); text-decoration:none;"
          active-class="!text-[var(--accent)]"
          @mouseenter="$event.target.style.background='var(--bg-subtle)'"
          @mouseleave="$event.target.style.background=''"
        >Registry</NuxtLink>

        <NuxtLink
          to="/developer"
          class="text-[13px] font-medium rounded px-3 py-1.5 transition-colors"
          style="color:var(--text-secondary); text-decoration:none;"
          active-class="!text-[var(--accent)]"
          @mouseenter="$event.target.style.background='var(--bg-subtle)'"
          @mouseleave="$event.target.style.background=''"
        >Developer Portal</NuxtLink>

        <button
          class="text-[13px] font-medium rounded px-3 py-1.5 transition-colors"
          style="color:var(--text-muted); background:transparent; border:none; cursor:pointer;"
          @click="logout"
          @mouseenter="$event.target.style.background='var(--bg-subtle)'; $event.target.style.color='var(--text-primary)'"
          @mouseleave="$event.target.style.background=''; $event.target.style.color='var(--text-muted)'"
        >Sign out</button>
      </nav>
    </header>

    <!-- ── Page content ──────────────────────────────────────────────────────── -->
    <slot />
  </div>
</template>
