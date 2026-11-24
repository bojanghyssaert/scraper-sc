<template>
  <header class="header">
    <div class="logo">
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="14" cy="14" r="14" fill="#FF5500"/>
        <path d="M6 17.5q0-1.5 1.1-2.55Q8.2 13.9 9.7 13.9q.4 0 .8.1.3-1.6 1.55-2.65Q13.3 10.3 14.9 10.3q1.9 0 3.2 1.3t1.3 3.2v.2q.8.3 1.3 1t.5 1.5q0 1.1-.8 1.9t-1.9.8H8.5q-1 0-1.75-.75T6 17.5z" fill="white"/>
      </svg>
      <span>SoundCloud Downloader</span>
    </div>
    <p class="subtitle">Zoek op SoundCloud of voer een track-link in om direct te beluisteren en downloaden</p>
  </header>
</template>

<script setup>
// Header component met applicatielogo en subtitel
</script>

<style scoped>
.header {
  flex-shrink: 0;
  text-align: left;
  margin-bottom: 2px;
}
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 4px;
}
.subtitle {
  color: var(--muted);
  font-size: 0.82rem;
}
</style>
