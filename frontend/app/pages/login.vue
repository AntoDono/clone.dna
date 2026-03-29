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

const features = [
  { icon: '⬡', label: '.dna Blocks', desc: 'Portable LoRA adapters that encode a developer\'s coding style and domain vocabulary.' },
  { icon: '⚡', label: 'Grok-4 Teacher', desc: 'AI reads public repos and generates high-quality instruction-response training pairs.' },
  { icon: '⇄', label: 'Hot-swap Inference', desc: 'Swap developer adapters in milliseconds — no restart, no redeployment.' },
  { icon: '◈', label: 'PM Orchestration', desc: 'PM plans, Grok assigns tasks, specialists respond with tool access.' },
]
</script>

<template>
  <div class="min-h-screen bg-slate-950 flex">
    <!-- Left: branding panel -->
    <div class="hidden lg:flex flex-col justify-between w-96 border-r border-slate-800 p-10 bg-slate-900/40">
      <div>
        <h1 class="text-xl font-bold text-white tracking-tight mb-1">Clone.dna</h1>
        <p class="text-slate-500 text-xs">Hire the Mind. Not the Body.</p>
      </div>
      <div class="space-y-6">
        <div v-for="feat in features" :key="feat.label" class="flex gap-3">
          <span class="text-blue-500 text-lg mt-0.5 leading-none">{{ feat.icon }}</span>
          <div>
            <p class="text-sm font-medium text-slate-200">{{ feat.label }}</p>
            <p class="text-xs text-slate-500 leading-relaxed mt-0.5">{{ feat.desc }}</p>
          </div>
        </div>
      </div>
      <p class="text-xs text-slate-700">LoRA · PEFT · Grok-4 · QLoRA</p>
    </div>

    <!-- Right: form -->
    <div class="flex-1 flex items-center justify-center px-6">
      <div class="w-full max-w-sm">
        <div class="mb-8 lg:hidden">
          <h1 class="text-2xl font-bold text-white tracking-tight">Clone.dna</h1>
          <p class="text-slate-500 text-sm mt-1">Hire the Mind. Not the Body.</p>
        </div>

        <div class="bg-slate-900 border border-slate-800 p-8">
          <h2 class="text-lg font-semibold text-white mb-1">
            {{ mode === 'login' ? 'Welcome back' : 'Get started' }}
          </h2>
          <p class="text-slate-500 text-xs mb-6">
            {{ mode === 'login' ? 'Sign in to your workspace' : 'Create a free workspace' }}
          </p>

          <form @submit.prevent="submit" class="space-y-4">
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wide">Username</label>
              <input
                v-model="username"
                type="text"
                autocomplete="username"
                placeholder="your_handle"
                class="w-full border border-slate-700 focus:border-blue-500 bg-slate-800/80 text-white placeholder-slate-600 px-3 py-2.5 text-sm outline-none transition-colors"
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
                class="w-full border border-slate-700 focus:border-blue-500 bg-slate-800/80 text-white placeholder-slate-600 px-3 py-2.5 text-sm outline-none transition-colors"
                :disabled="loading"
              />
            </div>

            <p v-if="error" class="text-xs text-red-400 bg-red-950/40 border border-red-900 px-3 py-2">{{ error }}</p>

            <button
              type="submit"
              class="w-full bg-blue-600 text-white py-2.5 text-sm font-semibold hover:bg-blue-500 transition-colors disabled:opacity-40"
              :disabled="!username.trim() || !password || loading"
            >
              {{ loading ? 'Please wait...' : mode === 'login' ? 'Sign in' : 'Create account' }}
            </button>
          </form>

          <p class="text-sm text-slate-500 text-center mt-6">
            {{ mode === 'login' ? "Don't have an account?" : 'Already have an account?' }}
            <button class="text-blue-400 hover:text-blue-300 ml-1 transition-colors font-medium" @click="toggle">
              {{ mode === 'login' ? 'Register' : 'Sign in' }}
            </button>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
