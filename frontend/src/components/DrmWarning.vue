<template>
  <transition name="fade">
    <section v-if="drmInfo" class="card drm-card">
      <div class="drm-header">
        <span class="drm-icon">🔒</span>
        <div class="drm-title-group">
          <h3 class="drm-title">DRM-beveiligde track</h3>
          <p class="drm-message">{{ drmInfo.message }}</p>
        </div>
      </div>
      <div class="drm-actions">
        <a
          v-if="drmInfo.url"
          :href="drmInfo.url"
          target="_blank"
          rel="noopener noreferrer"
          class="btn btn-secondary btn-sm"
        >
          Open op SoundCloud ↗
        </a>
        <button class="btn btn-outline btn-sm" @click="$emit('close')">
          Sluiten
        </button>
      </div>
    </section>
  </transition>
</template>

<script setup>
defineProps({
  drmInfo: {
    type: Object,
    default: null,
  },
})

defineEmits(['close'])
</script>

<style scoped>
.drm-card {
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.35);
  gap: 10px;
}
.drm-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.drm-icon {
  font-size: 1.5rem;
  line-height: 1;
}
.drm-title-group {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.drm-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: #fbbf24;
}
.drm-message {
  font-size: 0.82rem;
  color: var(--muted);
  line-height: 1.4;
}
.drm-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.btn-sm {
  font-size: 0.78rem;
  padding: 6px 12px;
}
</style>
