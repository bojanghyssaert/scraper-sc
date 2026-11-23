<template>
  <div class="app">
    <!-- ── Header ── -->
    <header class="header">
      <div class="logo">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="14" cy="14" r="14" fill="#FF5500"/>
          <path d="M6 17.5q0-1.5 1.1-2.55Q8.2 13.9 9.7 13.9q.4 0 .8.1.3-1.6 1.55-2.65Q13.3 10.3 14.9 10.3q1.9 0 3.2 1.3t1.3 3.2v.2q.8.3 1.3 1t.5 1.5q0 1.1-.8 1.9t-1.9.8H8.5q-1 0-1.75-.75T6 17.5z" fill="white"/>
        </svg>
        <span>SoundCloud Downloader</span>
      </div>
      <p class="subtitle">Voer een SoundCloud-link in en download de track in de gewenste kwaliteit</p>
    </header>

    <!-- ── Invoerkaart ── -->
    <section class="card">
      <label class="field-label">SoundCloud Track URL</label>
      <div class="input-row">
        <input
          v-model="trackUrl"
          class="url-input"
          type="url"
          placeholder="https://soundcloud.com/artiest/track"
          @keyup.enter="fetchTrack"
          @paste="handlePaste"
          :disabled="loading || downloading"
          autocomplete="off"
          spellcheck="false"
        />
        <button class="btn btn-secondary" @click="pasteFromClipboard" :disabled="loading || downloading" title="Plakken vanuit klembord">
          📋 Plakken
        </button>
        <button class="btn btn-accent" @click="fetchTrack" :disabled="!trackUrl.trim() || loading || downloading">
          <span v-if="loading" class="spinner"></span>
          <span v-else>Zoek track</span>
        </button>
      </div>

      <!-- Algemene foutmelding (alleen bij niet-DRM fouten) -->
      <p v-if="fetchError" class="status error">❌ {{ fetchError }}</p>

      <!-- Rustige informatiebanner voor DRM-beveiligde tracks -->
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

    <!-- ── Track Preview ── -->
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
              <span class="track-label">TRACK PREVIEW</span>
              <span v-if="selectedFormat?.id === 'original' || (track.is_artist_download && !selectedFormat)" class="badge-artist-download">
                ⭐ Officiële artist download
              </span>
            </div>
            <h2 class="track-title">{{ track.title }}</h2>
            <p class="track-artist">{{ track.artist }}</p>
            <p class="track-duration">{{ formatDuration(track.duration_ms) }}</p>
            <p class="track-filename">📄 {{ currentFilename }}</p>
          </div>
        </div>

        <!-- Formaat- en kwaliteitskeuze (indien meerdere opties beschikbaar zijn) -->
        <div v-if="track.formats && track.formats.length > 1" class="format-choice-block">
          <label class="field-label" for="format-select">FORMAAT / KWALITEIT</label>
          <div class="format-select-container">
            <select
              id="format-select"
              v-model="selectedFormatId"
              class="format-select"
              :disabled="downloading"
            >
              <option v-for="fmt in track.formats" :key="fmt.id" :value="fmt.id">
                {{ fmt.label }} ({{ fmt.extension }})
              </option>
            </select>
          </div>
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

        <!-- Download knop -->
        <button
          class="btn btn-accent btn-full"
          @click="downloadTrack"
          :disabled="downloading"
        >
          <span v-if="downloading" class="spinner"></span>
          <span v-else>⬇️ Download {{ downloadButtonFormat }}</span>
        </button>

        <p v-if="downloadError" class="status error">❌ {{ downloadError }}</p>
        <p v-if="downloadSuccess" class="status success">✅ {{ downloadSuccess }}</p>
      </section>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const API = 'http://localhost:8000'

const trackUrl          = ref('')
const track             = ref(null)
const selectedFormatId  = ref('')
const loading           = ref(false)
const fetchError        = ref('')
const drmInfo           = ref(null)
const downloading       = ref(false)
const downloadError     = ref('')
const downloadSuccess   = ref('')
const progress          = ref(0)
const progressText      = ref('Wachten op download...')

// Bepaal het huidig actieve formaatobject
const selectedFormat = computed(() => {
  if (!track.value?.formats?.length) return null
  return track.value.formats.find(f => f.id === selectedFormatId.value) || track.value.formats[0]
})

// Dynamische bestandsnaam afgestemd op de gekozen formaatextensie
const currentFilename = computed(() => {
  if (!track.value) return ''
  const baseName = track.value.filename.replace(/\.[a-zA-Z0-9]+$/, '')
  const ext = selectedFormat.value?.extension || track.value.extension || '.mp3'
  return `${baseName}${ext}`
})

// Label voor de downloadknop
const downloadButtonFormat = computed(() => {
  if (selectedFormat.value?.label) {
    return selectedFormat.value.label
  }
  const ext = (track.value?.extension || (track.value?.filename?.includes('.') ? '.' + track.value.filename.split('.').pop() : '')).toLowerCase()
  if (ext === '.m4a') return 'M4A'
  if (ext === '.ogg') return 'OGG (Opus)'
  if (ext === '.wav') return 'WAV'
  if (ext === '.flac') return 'FLAC'
  if (ext === '.aiff' || ext === '.aif') return 'AIFF'
  return 'MP3'
})

// Hulpfunctie om te valideren of een string een geldige SoundCloud track-URL is
function isSoundCloudUrl(url) {
  if (!url || typeof url !== 'string') return false
  const trimmed = url.trim()
  try {
    const parsed = new URL(
      trimmed.startsWith('http://') || trimmed.startsWith('https://')
        ? trimmed
        : `https://${trimmed}`
    )
    const host = parsed.hostname.toLowerCase()
    return (
      host === 'soundcloud.com' ||
      host.endsWith('.soundcloud.com')
    ) && parsed.pathname.length > 1
  } catch {
    return false
  }
}

// ── Plak-afhandeling (Ctrl+V / contextmenu) in het invoerveld ──
function handlePaste(event) {
  const pastedText = (event.clipboardData || window.clipboardData)?.getData('text') || ''
  const trimmed = pastedText.trim()
  if (isSoundCloudUrl(trimmed)) {
    event.preventDefault()
    trackUrl.value = trimmed
    fetchTrack()
  }
}

// ── Klembord knop ──
async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    const trimmed = text.trim()
    trackUrl.value = trimmed
    if (isSoundCloudUrl(trimmed)) {
      fetchTrack()
    }
  } catch {
    alert('Klembord-toegang niet beschikbaar. Plak de URL handmatig.')
  }
}

// ── Track ophalen ──
async function fetchTrack() {
  if (!trackUrl.value.trim()) return
  loading.value = true
  fetchError.value = ''
  drmInfo.value = null
  track.value = null
  selectedFormatId.value = ''
  downloadError.value = ''
  downloadSuccess.value = ''
  progress.value = 0
  progressText.value = 'Wachten op download...'

  const targetUrl = trackUrl.value.trim()

  try {
    const res = await fetch(`${API}/api/track?url=${encodeURIComponent(targetUrl)}`)
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      const detailMsg = typeof data.detail === 'string' ? data.detail : ''
      const isDrm = res.status === 403 || detailMsg.toLowerCase().includes('drm')

      if (isDrm) {
        drmInfo.value = {
          message: detailMsg || 'Dit nummer is DRM-beveiligd door SoundCloud en kan niet worden gedownload.',
          url: targetUrl
        }
      } else {
        fetchError.value = detailMsg || `Fout ${res.status}: Kan track niet ophalen.`
      }
      return
    }
    const trackData = await res.json()
    track.value = trackData
    if (trackData.formats && trackData.formats.length > 0) {
      selectedFormatId.value = trackData.formats[0].id
    }
  } catch (err) {
    fetchError.value = 'Verbindingsfout: controleer of de backend actief is op poort 8000.'
  } finally {
    loading.value = false
  }
}

// ── Download ──
async function downloadTrack() {
  if (!track.value) return
  downloading.value = true
  downloadError.value = ''
  downloadSuccess.value = ''
  progress.value = 0
  progressText.value = 'Verbinding maken...'

  const targetUrl = trackUrl.value.trim()
  const formatQuery = selectedFormatId.value ? `&format_id=${encodeURIComponent(selectedFormatId.value)}` : ''

  try {
    const res = await fetch(`${API}/api/download?url=${encodeURIComponent(targetUrl)}${formatQuery}`)
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      const detailMsg = typeof data.detail === 'string' ? data.detail : ''
      const isDrm = res.status === 403 || detailMsg.toLowerCase().includes('drm')

      if (isDrm) {
        drmInfo.value = {
          message: detailMsg || 'Dit nummer is DRM-beveiligd door SoundCloud en kan niet worden gedownload.',
          url: targetUrl
        }
      } else {
        downloadError.value = detailMsg || `Fout ${res.status}: Download mislukt.`
      }
      return
    }

    const contentLength = res.headers.get('content-length')
    const totalBytes = contentLength ? parseInt(contentLength, 10) : 0
    const reader = res.body.getReader()

    // Bepaal de bestandsextensie en het juiste MIME-type voor window.showSaveFilePicker
    const ext = (selectedFormat.value?.extension || track.value.extension || (track.value.filename.includes('.') ? '.' + track.value.filename.split('.').pop() : '.mp3')).toLowerCase()
    let pickerTypes = [{ description: 'MP3-audiobestand', accept: { 'audio/mpeg': ['.mp3'] } }]
    if (ext === '.m4a') {
      pickerTypes = [{ description: 'M4A-audiobestand', accept: { 'audio/mp4': ['.m4a'] } }]
    } else if (ext === '.ogg') {
      pickerTypes = [{ description: 'OGG-audiobestand', accept: { 'audio/ogg': ['.ogg'] } }]
    } else if (ext === '.wav') {
      pickerTypes = [{ description: 'WAV-audiobestand', accept: { 'audio/wav': ['.wav'] } }]
    } else if (ext === '.flac') {
      pickerTypes = [{ description: 'FLAC-audiobestand', accept: { 'audio/flac': ['.flac'] } }]
    } else if (ext === '.aiff' || ext === '.aif') {
      pickerTypes = [{ description: 'AIFF-audiobestand', accept: { 'audio/aiff': ['.aiff', '.aif'] } }]
    }

    const useFSA = typeof window.showSaveFilePicker === 'function'
    let fileHandle = null
    let writable = null
    const chunks = []

    if (useFSA) {
      try {
        fileHandle = await window.showSaveFilePicker({
          suggestedName: currentFilename.value,
          types: pickerTypes,
        })
        writable = await fileHandle.createWritable()
      } catch (err) {
        // Gebruiker annuleerde dialoog
        if (err.name === 'AbortError') {
          progressText.value = 'Download geannuleerd.'
          return
        }
        // FSA niet ondersteund of toegang geweigerd → fallback
        fileHandle = null
      }
    }

    // Lees en schrijf stream
    let downloaded = 0
    progressText.value = 'Downloaden...'

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      downloaded += value.byteLength

      if (writable) {
        await writable.write(value)
      } else {
        chunks.push(value)
      }

      if (totalBytes > 0) {
        const pct = Math.min(100, (downloaded / totalBytes) * 100)
        progress.value = pct
        const mb = (downloaded / 1048576).toFixed(1)
        const tot = (totalBytes / 1048576).toFixed(1)
        progressText.value = `${mb} MB / ${tot} MB (${Math.round(pct)}%)`
      } else {
        const mb = (downloaded / 1048576).toFixed(1)
        progressText.value = `${mb} MB gedownload...`
      }
    }

    if (writable) {
      await writable.close()
      progress.value = 100
      progressText.value = 'Opgeslagen!'
      downloadSuccess.value = `'${currentFilename.value}' is succesvol opgeslagen!`
    } else {
      // Fallback: <a download> in de browser
      const mime = selectedFormat.value?.media_type || track.value.media_type || (
        ext === '.m4a' ? 'audio/mp4' :
        ext === '.ogg' ? 'audio/ogg' :
        ext === '.wav' ? 'audio/wav' :
        ext === '.flac' ? 'audio/flac' :
        ext === '.aiff' || ext === '.aif' ? 'audio/aiff' : 'audio/mpeg'
      )
      const blob = new Blob(chunks, { type: mime })
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = currentFilename.value
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      progress.value = 100
      progressText.value = 'Download klaar!'
      downloadSuccess.value = `'${currentFilename.value}' is succesvol gedownload!`
    }
  } catch (err) {
    downloadError.value = `Onverwachte fout: ${err.message}`
  } finally {
    downloading.value = false
  }
}

// ── Hulpfunctie: duur opmaken ──
function formatDuration(ms) {
  if (!ms) return ''
  const totalSec = Math.floor(ms / 1000)
  const min = Math.floor(totalSec / 60)
  const sec = String(totalSec % 60).padStart(2, '0')
  return `${min}:${sec}`
}
</script>

<style scoped>
.app {
  width: 100%;
  max-width: 640px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Header */
.header { text-align: left; margin-bottom: 8px; }
.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 6px;
}
.subtitle { color: var(--muted); font-size: 0.875rem; }

/* Card */
.card {
  background: var(--card);
  border-radius: var(--radius);
  padding: 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* Labels */
.field-label {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: var(--accent);
}

/* Input row */
.input-row {
  display: flex;
  gap: 8px;
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
.url-input:focus { border-color: var(--accent); }
.url-input::placeholder { color: var(--muted); }
.url-input:disabled { opacity: .5; cursor: not-allowed; }

/* Buttons */
.btn {
  border: none;
  border-radius: 7px;
  font-family: var(--font);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  padding: 9px 16px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: background .15s, opacity .15s;
  white-space: nowrap;
}
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary {
  background: #333;
  color: var(--text);
}
.btn-secondary:hover:not(:disabled) { background: #444; }
.btn-accent {
  background: var(--accent);
  color: #fff;
}
.btn-accent:hover:not(:disabled) { background: var(--accent-h); }
.btn-full { width: 100%; justify-content: center; padding: 12px; font-size: 1rem; }

/* Spinner */
.spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* DRM Informatiebanner */
.drm-banner {
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.25);
  border-radius: var(--radius);
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 4px;
}
.drm-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.drm-icon {
  font-size: 1.25rem;
  line-height: 1;
  flex-shrink: 0;
  margin-top: 2px;
}
.drm-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.drm-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #93c5fd;
  margin: 0;
}
.drm-message {
  font-size: 0.875rem;
  color: #cbd5e1;
  line-height: 1.45;
  margin: 0;
}
.drm-actions {
  display: flex;
  justify-content: flex-start;
}
.drm-btn {
  text-decoration: none;
  font-size: 0.85rem;
  padding: 8px 14px;
  background: #2d2d2d;
  border: 1px solid #444;
  color: var(--text);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 6px;
  transition: background .15s, border-color .15s;
}
.drm-btn:hover {
  background: #3a3a3a;
  border-color: #666;
  color: #fff;
}

/* Preview */
.preview-card { gap: 18px; }
.preview {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.artwork {
  width: 96px;
  height: 96px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
}
.artwork-placeholder {
  width: 96px;
  height: 96px;
  border-radius: 8px;
  background: var(--input-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2.5rem;
  flex-shrink: 0;
}
.track-meta { display: flex; flex-direction: column; gap: 4px; overflow: hidden; }
.track-meta-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.track-label { font-size: .68rem; font-weight: 700; letter-spacing: .07em; color: var(--accent); text-transform: uppercase; }
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
.track-title { font-size: 1.1rem; font-weight: 700; color: var(--text); line-height: 1.3; word-break: break-word; }
.track-artist { color: var(--muted); font-size: .875rem; }
.track-duration { color: var(--muted); font-size: .8rem; }
.track-filename { color: var(--muted); font-size: .78rem; word-break: break-all; }

/* Formaatkeuze */
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

/* Progress */
.progress-block { display: flex; flex-direction: column; gap: 8px; }
.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.progress-detail { font-size: .8rem; color: var(--muted); }
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

/* Status */
.status { font-size: .875rem; padding: 2px 0; }
.error   { color: var(--error); }
.success { color: var(--success); }

/* Transition */
.fade-enter-active, .fade-leave-active { transition: opacity .3s, transform .3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(8px); }
</style>