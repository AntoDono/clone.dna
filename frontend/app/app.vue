<template>
  <div class="min-h-screen bg-slate-950">
    <NuxtRouteAnnouncer />
    <NuxtPage />
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
</style>
