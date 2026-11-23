<template>
  <div class="audio-player">
    <!-- Verborgen HTML5 audio element -->
    <audio
      ref="audioRef"
      :src="src"
      preload="none"
      @play="isPlaying = true"
      @pause="isPlaying = false"
      @ended="onEnded"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
      @waiting="isBuffering = true"
      @canplay="isBuffering = false"
      @error="onError"
    ></audio>

    <div class="player-controls">
      <!-- Play / Pauze-knop -->
      <button
        type="button"
        class="play-btn"
        :class="{ 'is-playing': isPlaying, 'is-buffering': isBuffering }"
        @click="togglePlay"
        :title="isPlaying ? 'Pauzeren' : 'Afspelen'"
        :aria-label="isPlaying ? 'Pauzeren' : 'Afspelen'"
      >
        <span v-if="isBuffering" class="player-spinner" aria-hidden="true"></span>
        <svg v-else-if="isPlaying" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="4" width="4" height="16" rx="1.5" />
          <rect x="14" y="4" width="4" height="16" rx="1.5" />
        </svg>
        <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8 5.14v13.72a1 1 0 0 0 1.5.86l11-6.86a1 1 0 0 0 0-1.72l-11-6.86A1 1 0 0 0 8 5.14z" />
        </svg>
      </button>

      <!-- Tijdlijn & Scrubber met tijdsweergave -->
      <div class="timeline-container">
        <div class="timeline-meta">
          <span class="time-label current">{{ formattedCurrentTime }}</span>
          <span class="time-divider">/</span>
          <span class="time-label total">{{ formattedTotalDuration }}</span>
        </div>

        <div
          ref="timelineRef"
          class="timeline-track"
          role="slider"
          :aria-valuenow="Math.round(currentTime)"
          :aria-valuemin="0"
          :aria-valuemax="Math.round(totalDuration)"
          aria-label="Audio voortgang"
          tabindex="0"
          @mousedown="onTimelineMouseDown"
          @touchstart="onTimelineTouchStart"
          @keydown="onTimelineKeyDown"
        >
          <div class="timeline-buffer" :style="{ width: bufferPercent + '%' }"></div>
          <div class="timeline-fill" :style="{ width: progressPercent + '%' }">
            <div class="timeline-handle"></div>
          </div>
        </div>
      </div>

      <!-- Compacte volumeregelaar / mute-knop -->
      <div class="volume-container">
        <button
          type="button"
          class="volume-btn"
          @click="toggleMute"
          :title="isMuted || volume === 0 ? 'Geluid dempen opheffen' : 'Geluid dempen'"
          :aria-label="isMuted || volume === 0 ? 'Geluid dempen opheffen' : 'Geluid dempen'"
        >
          <svg v-if="isMuted || volume === 0" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
            <line x1="23" y1="9" x2="17" y2="15"></line>
            <line x1="17" y1="9" x2="23" y2="15"></line>
          </svg>
          <svg v-else-if="volume <= 0.5" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
          </svg>
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
            <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
          </svg>
        </button>

        <div class="volume-slider-wrapper">
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            :value="isMuted ? 0 : volume"
            @input="onVolumeInput"
            class="volume-slider"
            title="Volume regelen"
            aria-label="Volume"
          />
        </div>
      </div>
    </div>

    <!-- Foutmelding status -->
    <div v-if="audioError" class="player-error">
      <span>⚠️ {{ audioError }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'

const props = defineProps({
  src: {
    type: String,
    required: true,
  },
  durationMs: {
    type: Number,
    default: 0,
  },
})

const audioRef = ref(null)
const timelineRef = ref(null)

const isPlaying = ref(false)
const isBuffering = ref(false)
const currentTime = ref(0)
const internalDuration = ref(0)
const bufferPercent = ref(0)
const volume = ref(0.8)
const isMuted = ref(false)
const previousVolume = ref(0.8)
const audioError = ref('')

let isDragging = false

// Totale duur in seconden: fallback op track.duration_ms
const totalDuration = computed(() => {
  if (internalDuration.value && isFinite(internalDuration.value) && internalDuration.value > 0) {
    return internalDuration.value
  }
  if (props.durationMs && props.durationMs > 0) {
    return props.durationMs / 1000
  }
  return 0
})

const progressPercent = computed(() => {
  const total = totalDuration.value
  if (!total || total <= 0) return 0
  return Math.min(100, Math.max(0, (currentTime.value / total) * 100))
})

const formattedCurrentTime = computed(() => formatTime(currentTime.value))
const formattedTotalDuration = computed(() => formatTime(totalDuration.value))

function formatTime(seconds) {
  if (!seconds || isNaN(seconds) || seconds < 0) return '0:00'
  const totalSec = Math.floor(seconds)
  const min = Math.floor(totalSec / 60)
  const sec = String(totalSec % 60).padStart(2, '0')
  return `${min}:${sec}`
}

async function togglePlay() {
  if (!audioRef.value) return
  audioError.value = ''

  if (isPlaying.value) {
    audioRef.value.pause()
  } else {
    try {
      isBuffering.value = true
      await audioRef.value.play()
    } catch (err) {
      isBuffering.value = false
      if (err.name !== 'AbortError') {
        audioError.value = 'Audiostream kon niet worden gestart.'
      }
    }
  }
}

function onTimeUpdate() {
  if (!audioRef.value || isDragging) return
  currentTime.value = audioRef.value.currentTime

  if (audioRef.value.buffered && audioRef.value.buffered.length > 0) {
    try {
      const bufferedEnd = audioRef.value.buffered.end(audioRef.value.buffered.length - 1)
      const total = totalDuration.value
      if (total > 0) {
        bufferPercent.value = Math.min(100, (bufferedEnd / total) * 100)
      }
    } catch {
      // safe fallback
    }
  }
}

function onLoadedMetadata() {
  if (audioRef.value && isFinite(audioRef.value.duration) && audioRef.value.duration > 0) {
    internalDuration.value = audioRef.value.duration
  }
}

function onEnded() {
  isPlaying.value = false
  currentTime.value = 0
  if (audioRef.value) {
    audioRef.value.currentTime = 0
  }
}

function onError() {
  isBuffering.value = false
  isPlaying.value = false
  if (props.src) {
    audioError.value = 'Kan audiostream niet laden.'
  }
}

// ── Tijdlijn interacties (Scrubbing) ──
function getTimelineRatio(event) {
  if (!timelineRef.value) return 0
  const rect = timelineRef.value.getBoundingClientRect()
  const clientX = event.touches ? event.touches[0].clientX : event.clientX
  const clampedX = Math.max(0, Math.min(clientX - rect.left, rect.width))
  return clampedX / rect.width
}

function applySeek(ratio) {
  const total = totalDuration.value
  if (!total || total <= 0) return
  const targetTime = ratio * total
  currentTime.value = targetTime
  if (audioRef.value) {
    audioRef.value.currentTime = targetTime
  }
}

function onTimelineMouseDown(event) {
  event.preventDefault()
  isDragging = true
  const ratio = getTimelineRatio(event)
  applySeek(ratio)

  window.addEventListener('mousemove', onWindowMouseMove)
  window.addEventListener('mouseup', onWindowMouseUp)
}

function onWindowMouseMove(event) {
  if (!isDragging) return
  const ratio = getTimelineRatio(event)
  applySeek(ratio)
}

function onWindowMouseUp(event) {
  if (!isDragging) return
  isDragging = false
  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)
}

function onTimelineTouchStart(event) {
  isDragging = true
  const ratio = getTimelineRatio(event)
  applySeek(ratio)

  window.addEventListener('touchmove', onWindowTouchMove, { passive: false })
  window.addEventListener('touchend', onWindowTouchEnd)
}

function onWindowTouchMove(event) {
  if (!isDragging) return
  event.preventDefault()
  const ratio = getTimelineRatio(event)
  applySeek(ratio)
}

function onWindowTouchEnd() {
  if (!isDragging) return
  isDragging = false
  window.removeEventListener('touchmove', onWindowTouchMove)
  window.removeEventListener('touchend', onWindowTouchEnd)
}

function onTimelineKeyDown(event) {
  const total = totalDuration.value
  if (!total || total <= 0 || !audioRef.value) return

  if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
    event.preventDefault()
    const target = Math.min(total, audioRef.value.currentTime + 5)
    audioRef.value.currentTime = target
    currentTime.value = target
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
    event.preventDefault()
    const target = Math.max(0, audioRef.value.currentTime - 5)
    audioRef.value.currentTime = target
    currentTime.value = target
  }
}

// ── Volume & Mute ──
function toggleMute() {
  if (!audioRef.value) return
  if (isMuted.value || volume.value === 0) {
    isMuted.value = false
    volume.value = previousVolume.value || 0.8
    audioRef.value.volume = volume.value
    audioRef.value.muted = false
  } else {
    previousVolume.value = volume.value
    isMuted.value = true
    volume.value = 0
    audioRef.value.volume = 0
    audioRef.value.muted = true
  }
}

function onVolumeInput(event) {
  const val = parseFloat(event.target.value)
  volume.value = val
  if (audioRef.value) {
    audioRef.value.volume = val
    if (val === 0) {
      isMuted.value = true
      audioRef.value.muted = true
    } else {
      isMuted.value = false
      audioRef.value.muted = false
      previousVolume.value = val
    }
  }
}

// ── Pauzeren & Resetten ──
function reset() {
  if (audioRef.value) {
    audioRef.value.pause()
    audioRef.value.currentTime = 0
  }
  isPlaying.value = false
  isBuffering.value = false
  currentTime.value = 0
  internalDuration.value = 0
  bufferPercent.value = 0
  audioError.value = ''
}

defineExpose({
  reset,
})

watch(() => props.src, (newSrc, oldSrc) => {
  if (newSrc !== oldSrc) {
    reset()
  }
})

onBeforeUnmount(() => {
  reset()
  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)
  window.removeEventListener('touchmove', onWindowTouchMove)
  window.removeEventListener('touchend', onWindowTouchEnd)
  if (audioRef.value) {
    audioRef.value.src = ''
    audioRef.value.load()
  }
})
</script>

<style scoped>
.audio-player {
  background: #1e1e1e;
  border: 1px solid #333333;
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.player-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Play/Pause Button */
.play-btn {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--accent);
  color: #ffffff;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.15s ease, background 0.15s ease;
}

.play-btn:hover {
  background: var(--accent-h);
  transform: scale(1.04);
}

.play-btn:active {
  transform: scale(0.96);
}

.player-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Timeline */
.timeline-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.timeline-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.time-label.current {
  color: var(--text);
}

.time-divider {
  color: #666;
}

.time-label.total {
  color: var(--muted);
}

.timeline-track {
  height: 8px;
  background: #2e2e2e;
  border-radius: 99px;
  position: relative;
  cursor: pointer;
  outline: none;
}

.timeline-track:focus-visible {
  box-shadow: 0 0 0 2px var(--accent);
}

.timeline-buffer {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: #3e3e3e;
  border-radius: 99px;
  transition: width 0.2s ease;
}

.timeline-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: var(--accent);
  border-radius: 99px;
  pointer-events: none;
}

.timeline-handle {
  position: absolute;
  right: -5px;
  top: 50%;
  transform: translateY(-50%);
  width: 11px;
  height: 11px;
  background: #ffffff;
  border-radius: 50%;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
  opacity: 0.9;
  transition: transform 0.1s ease;
}

.timeline-track:hover .timeline-handle {
  transform: translateY(-50%) scale(1.2);
  opacity: 1;
}

/* Volume Control */
.volume-container {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.volume-btn {
  background: transparent;
  border: none;
  color: var(--muted);
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s ease, background 0.15s ease;
}

.volume-btn:hover {
  color: var(--text);
  background: #2a2a2a;
}

.volume-slider-wrapper {
  display: flex;
  align-items: center;
}

.volume-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 58px;
  height: 4px;
  background: #383838;
  border-radius: 99px;
  outline: none;
  accent-color: var(--accent);
  cursor: pointer;
}

.volume-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  transition: transform 0.1s ease;
}

.volume-slider::-webkit-slider-thumb:hover {
  transform: scale(1.25);
}

.volume-slider::-moz-range-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  border: none;
  cursor: pointer;
}

/* Foutmelding */
.player-error {
  font-size: 0.78rem;
  color: var(--error);
  padding: 2px 4px;
}
</style>
