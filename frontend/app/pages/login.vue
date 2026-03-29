<script setup lang="ts">
definePageMeta({ layout: false })

const config = useRuntimeConfig()
const base = config.public.apiBase
const router = useRouter()

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!username.value.trim() || !password.value) return
  loading.value = true
  try {
    const endpoint = mode.value === 'login' ? '/auth/login' : '/auth/register'
    const data = await $fetch<{ token: string; username: string }>(`${base}${endpoint}`, {
      method: 'POST',
      body: { username: username.value.trim(), password: password.value },
    })
    localStorage.setItem('auth_token', data.token)
    localStorage.setItem('auth_username', data.username)
    router.push('/')
  } catch (e: any) {
    error.value = e?.data?.detail || (mode.value === 'login' ? 'Invalid username or password' : 'Registration failed')
  } finally {
    loading.value = false
  }
}

function toggle() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  error.value = ''
}
</script>

<template>
  <div class="min-h-screen bg-slate-950 flex items-center justify-center px-4">
    <div class="w-full max-w-sm">

      <!-- Logo -->
      <div class="text-center mb-8">
        <h1 class="text-2xl font-bold text-white tracking-tight">Clone.dna</h1>
        <p class="text-slate-500 text-sm mt-1">Hire the Mind. Not the Body.</p>
      </div>

      <!-- Card -->
      <div class="bg-slate-900 border border-slate-800 p-8">
        <h2 class="text-lg font-semibold text-white mb-6">
          {{ mode === 'login' ? 'Sign in' : 'Create account' }}
        </h2>

        <form @submit.prevent="submit" class="space-y-4">
          <div>
            <label class="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">Username</label>
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              placeholder="your_handle"
              class="w-full border border-slate-700 focus:border-blue-500 bg-slate-800 text-white placeholder-slate-600 px-3 py-2 text-sm outline-none transition-colors"
              :disabled="loading"
            />
          </div>

          <div>
            <label class="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">Password</label>
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="••••••••"
              class="w-full border border-slate-700 focus:border-blue-500 bg-slate-800 text-white placeholder-slate-600 px-3 py-2 text-sm outline-none transition-colors"
              :disabled="loading"
            />
          </div>

          <p v-if="error" class="text-xs text-red-400">{{ error }}</p>

          <button
            type="submit"
            class="w-full bg-blue-600 text-white py-2.5 text-sm font-medium hover:bg-blue-500 transition-colors disabled:opacity-40"
            :disabled="!username.trim() || !password || loading"
          >
            {{ loading ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account' }}
          </button>
        </form>

        <p class="text-sm text-slate-500 text-center mt-6">
          {{ mode === 'login' ? "Don't have an account?" : 'Already have an account?' }}
          <button class="text-blue-400 hover:text-blue-300 ml-1 transition-colors" @click="toggle">
            {{ mode === 'login' ? 'Register' : 'Sign in' }}
          </button>
        </p>
      </div>
    </div>
  </div>
</template>
