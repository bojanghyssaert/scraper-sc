<template>
  <transition name="fade">
    <section v-if="playlist" class="card playlist-card">
      <div class="preview">
        <img
          v-if="playlist.artwork_url"
          :src="playlist.artwork_url"
          :alt="`Cover van ${playlist.title}`"
          class="artwork"
          @error="playlist.artwork_url = ''"
        />
        <div v-else class="artwork-placeholder">📁</div>

        <div class="track-meta">
          <div class="track-meta-header">
            <div class="track-meta-header-left">
              <span class="track-label">PLAYLIST / ALBUM</span>
              <span class="badge-playlist-count">📁 {{ playlist.tracks ? playlist.tracks.length : 0 }} nummers</span>
            </div>
            <button
              type="button"
              class="btn-text btn-close-preview"
              @click="$emit('close')"
              :title="closeTitle"
            >
              {{ closeLabel }}
            </button>
          </div>
          <h2 class="track-title">{{ playlist.title }}</h2>
          <p class="track-artist">{{ playlist.artist }}</p>
          <p v-if="formatPlaylistTotalDuration" class="track-duration">Totale duur: {{ formatPlaylistTotalDuration }}</p>
        </div>
      </div>

      <!-- Selectiebalk & acties -->
      <div class="playlist-toolbar">
        <span class="selection-status">
          {{ selectedTrackUrls.size }} van de {{ downloadableTracksCount }} downloadbare tracks geselecteerd
        </span>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          @click="$emit('toggle-select-all')"
          :disabled="downloadingZip || downloading || downloadableTracksCount === 0"
        >
          {{ allSelected ? 'Deselecteer alles' : 'Alles selecteren' }}
        </button>
      </div>

      <!-- Tracklijst -->
      <div class="playlist-tracklist">
        <div
          v-for="(t, idx) in playlist.tracks"
          :key="t.url || idx"
          class="playlist-item"
          :class="{ 'is-drm': t.is_drm, 'is-checked': selectedTrackUrls.has(t.url) }"
          @click="!t.is_drm && $emit('toggle-track', t.url)"
        >
          <div class="playlist-item-check" @click.stop>
            <input
              type="checkbox"
              :checked="selectedTrackUrls.has(t.url)"
              :disabled="t.is_drm || downloadingZip || downloading"
              @change="$emit('toggle-track', t.url)"
              :title="t.is_drm ? 'DRM-beveiligd: kan niet gedownload worden' : 'Selecteren voor download'"
              class="track-checkbox"
            />
          </div>
          <span class="playlist-item-index">{{ String(idx + 1).padStart(2, '0') }}</span>
          <div class="playlist-item-info">
            <div class="playlist-item-title-row">
              <span class="playlist-item-title" :title="t.title">{{ t.title }}</span>
              <span v-if="t.is_drm" class="badge-drm" title="Dit nummer is DRM-beveiligd door SoundCloud en kan niet worden gedownload">
                🔒 DRM
              </span>
            </div>
            <span class="playlist-item-artist">{{ t.artist }}</span>
          </div>
          <span class="playlist-item-duration">{{ formatDuration(t.duration_ms) }}</span>
        </div>
      </div>

      <!-- Voortgangsbalk & status -->
      <div v-if="zipProgressText" class="progress-block">
        <div class="progress-header">
          <span class="field-label">VOORTGANG</span>
          <span class="progress-detail">{{ zipProgressText }}</span>
        </div>
      </div>

      <!-- Volume-normalisatie schakelaar -->
      <div class="normalize-block">
        <label class="toggle-control" for="normalize-toggle-playlist">
          <span class="toggle-info">
            <span class="toggle-icon">🔊</span>
            <span class="toggle-label">Volume gelijktrekken (-14 LUFS)</span>
          </span>
          <span class="toggle-switch">
            <input
              id="normalize-toggle-playlist"
              type="checkbox"
              :checked="normalizeAudio"
              @change="$emit('update:normalizeAudio', $event.target.checked)"
              :disabled="downloadingZip || downloading"
              class="toggle-checkbox"
            />
            <span class="toggle-slider"></span>
          </span>
        </label>
      </div>

      <!-- Download knop -->
      <button
        class="btn btn-accent btn-full"
        @click="$emit('download-zip')"
        :disabled="selectedTrackUrls.size === 0 || downloadingZip || downloading"
      >
        <span v-if="downloadingZip" class="spinner"></span>
        <span v-else>📦 Download selectie als .zip ({{ selectedTrackUrls.size }} {{ selectedTrackUrls.size === 1 ? 'track' : 'tracks' }})</span>
      </button>

      <p v-if="zipError" class="status error">❌ {{ zipError }}</p>
      <p v-if="zipSuccess" class="status success">✅ {{ zipSuccess }}</p>
    </section>
  </transition>
</template>

<script setup>
import { computed } from 'vue'
import { formatDuration } from '../services/api'

const props = defineProps({
  playlist: {
    type: Object,
    default: null,
  },
  selectedTrackUrls: {
    type: Set,
    default: () => new Set(),
  },
  downloadableTracksCount: {
    type: Number,
    default: 0,
  },
  formatPlaylistTotalDuration: {
    type: String,
    default: '',
  },
  allSelected: {
    type: Boolean,
    default: false,
  },
  normalizeAudio: {
    type: Boolean,
    default: false,
  },
  downloading: {
    type: Boolean,
    default: false,
  },
  downloadingZip: {
    type: Boolean,
    default: false,
  },
  zipProgressText: {
    type: String,
    default: '',
  },
  zipError: {
    type: String,
    default: '',
  },
  zipSuccess: {
    type: String,
    default: '',
  },
  isSearchMode: {
    type: Boolean,
    default: false,
  },
  hasSearchResults: {
    type: Boolean,
    default: false,
  },
})

defineEmits([
  'update:normalizeAudio',
  'close',
  'toggle-track',
  'toggle-select-all',
  'download-zip',
])

const closeLabel = computed(() => {
  return props.hasSearchResults && props.isSearchMode
    ? '✕ Terug naar resultaten'
    : '✕ Sluiten'
})

const closeTitle = computed(() => {
  return props.hasSearchResults && props.isSearchMode
    ? 'Sluit preview en toon zoekresultaten'
    : 'Playlist sluiten'
})
</script>

<style scoped>
.playlist-card {
  gap: 12px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 16px 20px;
}
.playlist-card .preview {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  flex-shrink: 0;
  width: 100%;
}
.artwork {
  width: 84px;
  height: 84px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
}
.artwork-placeholder {
  width: 84px;
  height: 84px;
  border-radius: 8px;
  background: var(--input-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2.2rem;
  flex-shrink: 0;
}
.track-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
  flex: 1;
  min-width: 0;
}
.track-meta-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
}
.track-meta-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}
.btn-close-preview {
  margin-left: auto;
  white-space: nowrap;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.track-label {
  font-size: .68rem;
  font-weight: 700;
  letter-spacing: .07em;
  color: var(--accent);
  text-transform: uppercase;
}
.badge-playlist-count {
  display: inline-block;
  background: rgba(255, 85, 0, 0.12);
  color: var(--accent);
  border: 1px solid rgba(255, 85, 0, 0.3);
  font-size: 0.72rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}
.track-title {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text);
  line-height: 1.3;
  word-break: break-word;
}
.track-artist {
  color: var(--muted);
  font-size: .875rem;
}
.track-duration {
  color: var(--muted);
  font-size: .8rem;
}
.playlist-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 8px;
  border-bottom: 1px solid #333333;
  flex-shrink: 0;
}
.selection-status {
  font-size: 0.82rem;
  color: var(--muted);
  font-weight: 500;
}
.playlist-tracklist {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-height: 0;
  max-height: min(380px, calc(100vh - 350px));
  max-height: min(380px, calc(100dvh - 350px));
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: #444444 #242424;
}
.playlist-tracklist::-webkit-scrollbar {
  width: 6px;
}
.playlist-tracklist::-webkit-scrollbar-track {
  background: #242424;
  border-radius: 4px;
}
.playlist-tracklist::-webkit-scrollbar-thumb {
  background: #444444;
  border-radius: 4px;
  transition: background 0.15s ease;
}
.playlist-tracklist::-webkit-scrollbar-thumb:hover {
  background: #FF5500;
}
.progress-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}
.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.progress-detail {
  font-size: .8rem;
  color: var(--muted);
}
.playlist-item {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #1e1e1e;
  border: 1px solid #303030;
  border-radius: 7px;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.playlist-item:hover:not(.is-drm) {
  background: #282828;
  border-color: #404040;
}
.playlist-item.is-checked {
  border-color: rgba(255, 85, 0, 0.45);
  background: rgba(255, 85, 0, 0.04);
}
.playlist-item.is-drm {
  opacity: 0.6;
  cursor: not-allowed;
}
.playlist-item-check {
  display: flex;
  align-items: center;
}
.track-checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
  cursor: pointer;
}
.playlist-item-index {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--muted);
  width: 20px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.playlist-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.playlist-item-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.playlist-item-title {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.playlist-item-artist {
  font-size: 0.75rem;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.playlist-item-duration {
  font-size: 0.75rem;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.badge-drm {
  display: inline-flex;
  align-items: center;
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.35);
  font-size: 0.65rem;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 4px;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}
</style>
