/**
 * Global auth middleware — redirect to /login if no token is stored.
 * Runs on every route navigation automatically (*.global.ts convention).
 * The /login page is exempt.
 */
export default defineNuxtRouteMiddleware((to) => {
  if (to.path === '/login') return

  // localStorage is only available client-side
  if (import.meta.client) {
    const token = localStorage.getItem('auth_token')
    if (!token) {
      return navigateTo('/login')
    }
  }
})
