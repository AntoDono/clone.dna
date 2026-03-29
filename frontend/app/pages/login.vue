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
    error.value = e?.data?.detail || (mode.value === 'login' ? 'Invalid credentials' : 'Registration failed')
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
  <div class="login-root">

    <!-- Left panel: editorial brand -->
    <div class="login-brand">
      <div class="brand-inner">
        <!-- Wordmark -->
        <div class="brand-wordmark">
          <span class="brand-logo">Clone.dna</span>
          <span class="brand-tagline">Hire the Mind. Not the Body.</span>
        </div>

        <!-- Pull quote -->
        <div class="brand-quote">
          <div class="quote-rule"></div>
          <p class="quote-text">
            "A developer's public work is the most honest interview they'll ever give."
          </p>
        </div>

        <!-- Feature list -->
        <ul class="brand-features">
          <li v-for="f in features" :key="f.label" class="brand-feature">
            <span class="feature-dot"></span>
            <div>
              <p class="feature-label">{{ f.label }}</p>
              <p class="feature-desc">{{ f.desc }}</p>
            </div>
          </li>
        </ul>

        <div class="brand-footer">
          <span class="font-mono text-xs" style="color:var(--text-muted)">LoRA · QLoRA · PEFT</span>
        </div>
      </div>
    </div>

    <!-- Right panel: form -->
    <div class="login-form-panel">
      <div class="login-form-inner animate-in">

        <div class="form-header">
          <h1 class="font-display form-title">
            {{ mode === 'login' ? 'Welcome back' : 'Get started' }}
          </h1>
          <p class="form-subtitle">
            {{ mode === 'login'
              ? 'Sign in to your workspace to manage your AI team.'
              : 'Create a workspace to start cloning developer DNA.' }}
          </p>
        </div>

        <form class="login-fields" @submit.prevent="submit">
          <div class="field-group">
            <label class="field-label">Username</label>
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              placeholder="your_handle"
              class="input"
              :disabled="loading"
            />
          </div>

          <div class="field-group">
            <label class="field-label">Password</label>
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="••••••••"
              class="input"
              :disabled="loading"
            />
          </div>

          <div v-if="error" class="error-callout">{{ error }}</div>

          <button
            type="submit"
            class="btn btn-primary submit-btn"
            :disabled="!username.trim() || !password || loading"
          >
            <span v-if="loading" class="streaming-dot"></span>
            {{ loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account' }}
          </button>
        </form>

        <p class="toggle-prompt">
          {{ mode === 'login' ? "Don't have an account?" : 'Already have an account?' }}
          <button class="toggle-link" @click="toggle">
            {{ mode === 'login' ? 'Register' : 'Sign in' }}
          </button>
        </p>

      </div>
    </div>
  </div>
</template>

<script lang="ts">
export default {
  data() {
    return {
      features: [
        {
          label: '.dna Blocks',
          desc: 'Portable LoRA adapters encoding a developer\'s coding style and architecture patterns.',
        },
        {
          label: 'AI Teacher',
          desc: 'Reads public repos and generates high-quality instruction–response training pairs.',
        },
        {
          label: 'Hot-swap Inference',
          desc: 'Switch developer adapters in milliseconds via PEFT. No restart needed.',
        },
        {
          label: 'PM Orchestration',
          desc: 'PM plans a task, AI assigns sub-tasks, specialists respond with tool access.',
        },
      ],
    }
  },
}
</script>

<style scoped>
.login-root {
  min-height: 100vh;
  display: flex;
  background-color: #FAF8F4;
}

/* ── Left brand panel ── */
.login-brand {
  width: 420px;
  flex-shrink: 0;
  background-color: #1C1811 !important;
  display: flex;
  align-items: stretch;
  position: relative;
  overflow: hidden;
}
.login-brand::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at 20% 80%, rgba(22,101,52,0.35) 0%, transparent 60%),
              radial-gradient(ellipse at 80% 10%, rgba(22,101,52,0.18) 0%, transparent 50%);
  pointer-events: none;
  z-index: 0;
}
.brand-inner {
  position: relative;
  z-index: 2;
  padding: 48px 40px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  width: 100%;
  color: #FFFFFF;
}
.brand-wordmark {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.brand-logo {
  font-family: 'Instrument Serif', Georgia, serif;
  font-size: 28px;
  color: #FFFFFF;
  letter-spacing: -0.02em;
}
.brand-tagline {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.5);
  font-weight: 400;
  letter-spacing: 0.01em;
}
.brand-quote {
  padding: 28px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.quote-rule {
  width: 24px;
  height: 2px;
  background-color: #15803D;
  margin-bottom: 16px;
}
.quote-text {
  font-family: 'Instrument Serif', Georgia, serif;
  font-style: italic;
  font-size: 17px;
  line-height: 1.65;
  color: rgba(255, 255, 255, 0.82);
}
.brand-features {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.brand-feature {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.feature-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #15803D;
  margin-top: 6px;
  flex-shrink: 0;
}
.feature-label {
  font-size: 13px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  margin-bottom: 2px;
}
.feature-desc {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.62);
  line-height: 1.55;
}
.brand-footer {
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.brand-footer span {
  color: rgba(255, 255, 255, 0.35);
  font-size: 11px;
}

/* ── Right form panel ── */
.login-form-panel {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  background-color: #FFFFFF;
}
.login-form-inner {
  width: 100%;
  max-width: 360px;
}
.form-header {
  margin-bottom: 32px;
}
.form-title {
  font-size: 30px;
  font-weight: 400;
  letter-spacing: -0.02em;
  color: #1C1811;
  line-height: 1.2;
  margin-bottom: 8px;
}
.form-subtitle {
  font-size: 14px;
  color: #6B6050;
  line-height: 1.5;
}
.login-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 24px;
}
.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  font-size: 11px;
  font-weight: 700;
  color: #6B6050;
  text-transform: uppercase;
  letter-spacing: 0.07em;
}
.submit-btn {
  width: 100%;
  justify-content: center;
  padding: 11px 20px;
  font-size: 14px;
  margin-top: 4px;
}
.error-callout {
  font-size: 13px;
  color: #991B1B;
  background-color: #FEE2E2;
  border: 1px solid #FECACA;
  border-radius: 4px;
  padding: 10px 14px;
}
.toggle-prompt {
  text-align: center;
  font-size: 13px;
  color: #A8A098;
}
.toggle-link {
  color: #166534;
  font-weight: 500;
  background: none;
  border: none;
  cursor: pointer;
  margin-left: 4px;
  padding: 0;
  font-size: 13px;
  font-family: 'Outfit', system-ui, sans-serif;
}
.toggle-link:hover { text-decoration: underline; }

@media (max-width: 768px) {
  .login-brand { display: none; }
  .login-form-panel { background-color: #FAF8F4; }
}
</style>
