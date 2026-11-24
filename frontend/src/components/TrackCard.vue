<template>
  <transition name="fade">
    <section v-if="track" class="card preview-card">
      <div class="preview">
        <img
          v-if="track.artwork_url"
          :src="track.artwork_url"
          :alt="`Cover van ${track.title}`"
          class="artwork"
          @error="track.artwork_url = ''"
        />
        <div v-else class="artwork-placeholder">🎵</div>

        <div class="track-meta">
          <div class="track-meta-header">
            <div class="track-meta-header-left">
              <span class="track-label">TRACK PREVIEW</span>
              <span v-if="selectedFormat?.id === 'original' || (track.is_artist_download && !selectedFormat)" class="badge-artist-download">
                ⭐ Officiële artist download
              </span>
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
          <h2 class="track-title">{{ track.title }}</h2>
          <p class="track-artist">{{ track.artist }}</p>
          <p class="track-duration">{{ formatDuration(track.duration_ms) }}</p>
          <p class="track-filename">📄 {{ currentFilename }}</p>
        </div>
      </div>

      <!-- Formaat- en kwaliteitskeuze -->
      <div v-if="track.formats && track.formats.length > 1" class="format-choice-block">
        <label class="field-label" for="format-select">FORMAAT / KWALITEIT</label>
        <div class="format-select-container">
          <select
            id="format-select"
            :value="selectedFormatId"
            @change="$emit('update:selectedFormatId', $event.target.value)"
            class="format-select"
            :disabled="downloading || downloadingZip"
          >
            <option v-for="fmt in track.formats" :key="fmt.id" :value="fmt.id">
              {{ fmt.label }} ({{ fmt.extension }})
            </option>
          </select>
        </div>
      </div>

      <!-- Audio Preview Speler -->
      <div class="player-block">
        <span class="field-label">AUDIO VOORBEELD</span>
        <AudioPlayer
          ref="audioPlayerRef"
          :src="previewAudioUrl"
          :duration-ms="track.duration_ms"
        />
      </div>

      <!-- Voortgangsbalk -->
      <div class="progress-block">
        <div class="progress-header">
          <span class="field-label">VOORTGANG</span>
          <span class="progress-detail">{{ progressText }}</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: progress + '%' }"></div>
        </div>
      </div>

      <!-- Volume-normalisatie schakelaar -->
      <div class="normalize-block">
        <label class="toggle-control" for="normalize-toggle-track">
          <span class="toggle-info">
            <span class="toggle-icon">🔊</span>
            <span class="toggle-label">Volume gelijktrekken (-14 LUFS)</span>
          </span>
          <span class="toggle-switch">
            <input
              id="normalize-toggle-track"
              type="checkbox"
              :checked="normalizeAudio"
              @change="$emit('update:normalizeAudio', $event.target.checked)"
              :disabled="downloading || downloadingZip"
              class="toggle-checkbox"
            />
            <span class="toggle-slider"></span>
          </span>
        </label>
      </div>

      <!-- Download knop -->
      <button
        class="btn btn-accent btn-full"
        @click="$emit('download')"
        :disabled="downloading || downloadingZip"
      >
        <span v-if="downloading" class="spinner"></span>
        <span v-else>⬇️ Download {{ downloadButtonFormat }}</span>
      </button>

      <p v-if="downloadError" class="status error">❌ {{ downloadError }}</p>
      <p v-if="downloadSuccess" class="status success">✅ {{ downloadSuccess }}</p>
    </section>
  </transition>
</template>

<script setup>
import { computed, ref } from 'vue'
import { formatDuration } from '../services/api'
import AudioPlayer from './AudioPlayer.vue'

const props = defineProps({
  track: {
    type: Object,
    default: null,
  },
  selectedFormatId: {
    type: String,
    default: '',
  },
  selectedFormat: {
    type: Object,
    default: null,
  },
  currentFilename: {
    type: String,
    default: '',
  },
  downloadButtonFormat: {
    type: String,
    default: 'MP3',
  },
  previewAudioUrl: {
    type: String,
    default: '',
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
  downloadError: {
    type: String,
    default: '',
  },
  downloadSuccess: {
    type: String,
    default: '',
  },
  progress: {
    type: Number,
    default: 0,
  },
  progressText: {
    type: String,
    default: 'Wachten op download...',
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
  'update:selectedFormatId',
  'update:normalizeAudio',
  'close',
  'download',
])

const audioPlayerRef = ref(null)

const closeLabel = computed(() => {
  return props.hasSearchResults && props.isSearchMode
    ? '✕ Terug naar resultaten'
    : '✕ Sluiten'
})

const closeTitle = computed(() => {
  return props.hasSearchResults && props.isSearchMode
    ? 'Sluit preview en toon zoekresultaten'
    : 'Track preview sluiten'
})

function resetAudioPlayer() {
  if (audioPlayerRef.value) {
    audioPlayerRef.value.reset()
  }
}

defineExpose({
  resetAudioPlayer,
})
</script>

<style scoped>
.preview-card {
  gap: 14px;
  flex-shrink: 0;
  min-height: 0;
  padding: 16px 20px;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.preview {
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
.badge-artist-download {
  display: inline-block;
  background: rgba(0, 230, 118, 0.15);
  color: #00E676;
  border: 1px solid rgba(0, 230, 118, 0.3);
  font-size: 0.72rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  width: fit-content;
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
.track-filename {
  color: var(--muted);
  font-size: .78rem;
  word-break: break-all;
}
.format-choice-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.format-select-container {
  position: relative;
  display: flex;
  width: 100%;
}
.format-select {
  width: 100%;
  background: var(--input-bg);
  border: 1.5px solid var(--border);
  border-radius: 7px;
  color: var(--text);
  font-family: var(--font);
  font-size: 0.9rem;
  font-weight: 500;
  padding: 9px 36px 9px 13px;
  outline: none;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%23A0A0A0' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 14px center;
  transition: border-color .15s;
}
.format-select:focus {
  border-color: var(--accent);
}
.format-select:disabled {
  opacity: .5;
  cursor: not-allowed;
}
.format-select option {
  background: #242424;
  color: #fff;
  padding: 8px;
}
.player-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.progress-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
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
.progress-track {
  height: 8px;
  background: var(--input-bg);
  border-radius: 99px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 99px;
  transition: width .2s ease;
}
</style>
