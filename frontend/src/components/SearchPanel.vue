<template>
  <section class="card input-card" :class="{ 'has-results': searchResults.length > 0 && !hasActiveItem }">
    <!-- Modus-schakelaar: Zoek op naam / Plak URL -->
    <div class="mode-switch">
      <button
        type="button"
        class="mode-btn"
        :class="{ active: inputMode === 'search' }"
        @click="$emit('update:inputMode', 'search')"
      >
        🔍 Zoek op naam
      </button>
      <button
        type="button"
        class="mode-btn"
        :class="{ active: inputMode === 'url' }"
        @click="$emit('update:inputMode', 'url')"
      >
        🔗 Plak URL
      </button>
    </div>

    <!-- Modus: Zoeken op naam -->
    <div v-if="inputMode === 'search'" class="input-block search-input-block">
      <label class="field-label" for="search-input">ZOEKEN OP SOUNDCLOUD</label>
      <div class="input-row">
        <input
          id="search-input"
          :value="searchQuery"
          class="url-input"
          type="text"
          placeholder="Artiest of titel (bijv. Flume, Odesza, Martin Garrix)..."
          @input="$emit('update:searchQuery', $event.target.value)"
          @keyup.enter="$emit('search')"
          @paste="$emit('search-paste', $event)"
          :disabled="searching || loading || downloading"
          autocomplete="off"
          spellcheck="false"
        />
        <button
          class="btn btn-accent"
          @click="$emit('search')"
          :disabled="!searchQuery.trim() || searching || loading || downloading"
        >
          <span v-if="searching" class="spinner"></span>
          <span v-else>Zoeken</span>
        </button>
      </div>

      <p v-if="searchError" class="status error">❌ {{ searchError }}</p>
      <p v-if="hasSearched && searchResults.length === 0 && !searching && !searchError" class="status muted-info">
        Geen tracks gevonden voor '{{ lastSearchedQuery }}'. Probeer een andere artiest of titel.
      </p>

      <!-- Zoekresultatenlijst -->
      <transition name="fade">
        <div v-if="searchResults.length > 0 && !hasActiveItem" class="search-results">
          <div class="search-results-header">
            <span class="field-label">ZOEKRESULTATEN ({{ searchResults.length }})</span>
            <button type="button" class="btn-text" @click="$emit('clear-search')" title="Resultaten wissen">
              ✕ Wissen
            </button>
          </div>

          <div class="search-list">
            <div
              v-for="item in searchResults"
              :key="item.permalink_url"
              class="search-item"
              :class="{
                'is-selected': trackUrl === item.permalink_url && hasActiveItem,
                'is-drm': item.is_drm,
              }"
              @click="$emit('select-result', item)"
              role="button"
              tabindex="0"
              @keydown.enter="$emit('select-result', item)"
              :title="item.is_drm ? `${item.title} (DRM-beveiligd)` : item.title"
            >
              <img
                v-if="item.artwork_url"
                :src="item.artwork_url"
                :alt="`Cover van ${item.title}`"
                class="search-thumb"
                @error="item.artwork_url = ''"
              />
              <div v-else class="search-thumb-placeholder">🎵</div>

              <div class="search-details">
                <div class="search-title-row">
                  <span class="search-title">{{ item.title }}</span>
                  <span v-if="item.is_drm" class="badge-drm" title="Dit nummer is DRM-beveiligd door SoundCloud">
                    🔒 DRM
                  </span>
                </div>
                <div class="search-sub-row">
                  <span class="search-artist">{{ item.artist }}</span>
                  <span class="search-dot">•</span>
                  <span class="search-duration">{{ formatDuration(item.duration_ms) }}</span>
                </div>
              </div>

              <div class="search-action">
                <span class="search-action-btn">
                  {{ loading && trackUrl === item.permalink_url ? 'Laden...' : (trackUrl === item.permalink_url && hasActiveItem ? 'Geselecteerd' : 'Kies track') }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- Modus: Direct URL plakken -->
    <div v-else class="input-block">
      <label class="field-label" for="track-url-input">SOUNDCLOUD TRACK URL</label>
      <div class="input-row">
        <input
          id="track-url-input"
          :value="trackUrl"
          class="url-input"
          type="url"
          placeholder="https://soundcloud.com/artiest/track"
          @input="$emit('update:trackUrl', $event.target.value)"
          @keyup.enter="$emit('fetch-track')"
          @paste="$emit('url-paste', $event)"
          :disabled="loading || downloading"
          autocomplete="off"
          spellcheck="false"
        />
        <button
          class="btn btn-secondary"
          @click="$emit('paste-clipboard')"
          :disabled="loading || downloading"
          title="Plakken vanuit klembord"
        >
          📋 Plakken
        </button>
        <button
          class="btn btn-accent"
          @click="$emit('fetch-track')"
          :disabled="!trackUrl.trim() || loading || downloading"
        >
          <span v-if="loading" class="spinner"></span>
          <span v-else>Zoek track</span>
        </button>
      </div>
    </div>

    <!-- Algemene foutmelding (alleen bij niet-DRM fouten) -->
    <p v-if="fetchError" class="status error">❌ {{ fetchError }}</p>

    <!-- Informatiebanner voor DRM-beveiligde tracks -->
    <transition name="fade">
      <div v-if="drmInfo" class="drm-banner">
        <div class="drm-header">
          <span class="drm-icon">ℹ️</span>
          <div class="drm-body">
            <h3 class="drm-title">DRM-beveiligd nummer</h3>
            <p class="drm-message">{{ drmInfo.message }}</p>
          </div>
        </div>
        <div class="drm-actions">
          <a
            :href="drmInfo.url"
            target="_blank"
            rel="noopener noreferrer"
            class="btn btn-secondary drm-btn"
          >
            <span>Open op SoundCloud</span>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
          </a>
        </div>
      </div>
    </transition>
  </section>
</template>

<script setup>
import { formatDuration } from '../services/api'

defineProps({
  inputMode: {
    type: String,
    default: 'search',
  },
  searchQuery: {
    type: String,
    default: '',
  },
  searching: {
    type: Boolean,
    default: false,
  },
  searchResults: {
    type: Array,
    default: () => [],
  },
  searchError: {
    type: String,
    default: '',
  },
  hasSearched: {
    type: Boolean,
    default: false,
  },
  lastSearchedQuery: {
    type: String,
    default: '',
  },
  trackUrl: {
    type: String,
    default: '',
  },
  loading: {
    type: Boolean,
    default: false,
  },
  downloading: {
    type: Boolean,
    default: false,
  },
  fetchError: {
    type: String,
    default: '',
  },
  drmInfo: {
    type: Object,
    default: null,
  },
  hasActiveItem: {
    type: Boolean,
    default: false,
  },
})

defineEmits([
  'update:inputMode',
  'update:searchQuery',
  'update:trackUrl',
  'search',
  'clear-search',
  'select-result',
  'search-paste',
  'fetch-track',
  'url-paste',
  'paste-clipboard',
])
</script>

<style scoped>
.input-card {
  flex-shrink: 0;
}
.input-card.has-results {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.mode-switch {
  display: flex;
  background: var(--input-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 3px;
  gap: 4px;
  flex-shrink: 0;
}
.mode-btn {
  flex: 1;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--muted);
  font-family: var(--font);
  font-size: 0.85rem;
  font-weight: 600;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.mode-btn:hover:not(.active) {
  color: var(--text);
  background: rgba(255, 255, 255, 0.05);
}
.mode-btn.active {
  background: var(--accent);
  color: #ffffff;
}
.input-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
.search-input-block {
  flex: 1;
  min-height: 0;
}
.search-results {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 2px;
  border-top: 1px solid #333333;
  padding-top: 10px;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}
.search-results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}
.btn-text {
  background: transparent;
  border: none;
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: color 0.15s ease, background-color 0.15s ease;
}
.btn-text:hover {
  color: #FF5500;
}
.search-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-height: 0;
  max-height: min(380px, calc(100vh - 250px));
  max-height: min(380px, calc(100dvh - 250px));
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 4px;
  scrollbar-width: thin;
  scrollbar-color: #444444 #242424;
}
.search-list::-webkit-scrollbar {
  width: 6px;
}
.search-list::-webkit-scrollbar-track {
  background: #242424;
  border-radius: 4px;
}
.search-list::-webkit-scrollbar-thumb {
  background: #444444;
  border-radius: 4px;
  transition: background 0.15s ease;
}
.search-list::-webkit-scrollbar-thumb:hover {
  background: #FF5500;
}
.search-item {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #1e1e1e;
  border: 1px solid #333333;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.1s ease;
  outline: none;
}
.search-item:hover {
  background: #2a2a2a;
  border-color: #4a4a4a;
}
.search-item:focus-visible {
  border-color: var(--accent);
}
.search-item.is-selected {
  border-color: var(--accent);
  background: rgba(255, 85, 0, 0.08);
}
.search-thumb {
  width: 44px;
  height: 44px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
}
.search-thumb-placeholder {
  width: 44px;
  height: 44px;
  border-radius: 6px;
  background: #2d2d2d;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  flex-shrink: 0;
}
.search-details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.search-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.search-title {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.search-sub-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: var(--muted);
}
.search-artist {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
}
.search-dot {
  color: #555555;
}
.search-duration {
  font-variant-numeric: tabular-nums;
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
.search-action-btn {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--muted);
  background: #2b2b2b;
  border: 1px solid #3d3d3d;
  padding: 4px 9px;
  border-radius: 5px;
  transition: all 0.15s ease;
  white-space: nowrap;
}
.search-item:hover .search-action-btn {
  background: var(--accent);
  border-color: var(--accent);
  color: #ffffff;
}
.muted-info {
  color: var(--muted);
  font-size: 0.85rem;
}
.input-row {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.url-input {
  flex: 1;
  background: var(--input-bg);
  border: 1.5px solid var(--border);
  border-radius: 7px;
  color: var(--text);
  font-family: var(--font);
  font-size: 0.9rem;
  padding: 9px 13px;
  outline: none;
  transition: border-color .15s;
  min-width: 0;
}
.url-input:focus {
  border-color: var(--accent);
}
.drm-banner {
  background: #221c11;
  border: 1px solid #6b4d1b;
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.drm-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.drm-icon {
  font-size: 1.25rem;
  line-height: 1.2;
}
.drm-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.drm-title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: #f6c065;
}
.drm-message {
  margin: 0;
  font-size: 0.85rem;
  color: #d1b48c;
  line-height: 1.4;
}
.drm-actions {
  display: flex;
  justify-content: flex-end;
}
.drm-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.82rem;
  padding: 6px 12px;
  text-decoration: none;
  color: #f5f5f5;
  background: #332616;
  border: 1px solid #7c5822;
  border-radius: 6px;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.drm-btn:hover {
  background: #46341d;
  border-color: #9c6e2b;
}
</style>
