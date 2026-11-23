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
      <p class="subtitle">Voer een SoundCloud-link in en download de track als MP3 of M4A</p>
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
      <p v-if="fetchError" class="status error">❌ {{ fetchError }}</p>
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
            <span class="track-label">TRACK PREVIEW</span>
            <h2 class="track-title">{{ track.title }}</h2>
            <p class="track-artist">{{ track.artist }}</p>
            <p class="track-duration">{{ formatDuration(track.duration_ms) }}</p>
            <p class="track-filename">📄 {{ track.filename }}</p>
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
          <span v-else>⬇️ Download {{ trackFormatLabel }}</span>
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

const trackUrl      = ref('')
const track         = ref(null)
const loading       = ref(false)
const fetchError    = ref('')
const downloading   = ref(false)
const downloadError = ref('')
const downloadSuccess = ref('')
const progress      = ref(0)
const progressText  = ref('Wachten op download...')

const trackFormatLabel = computed(() => {
  if (track.value?.filename?.toLowerCase().endsWith('.m4a') || track.value?.extension === '.m4a') {
    return 'M4A'
  }
  if (track.value?.filename?.toLowerCase().endsWith('.ogg') || track.value?.extension === '.ogg') {
    return 'OGG (Opus)'
  }
  return 'MP3'
})

// ── Klembord ──
async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    trackUrl.value = text.trim()
  } catch {
    // Fallback: niet ondersteund of geen toestemming
    alert('Klembord-toegang niet beschikbaar. Plak de URL handmatig.')
  }
}

// ── Track ophalen ──
async function fetchTrack() {
  if (!trackUrl.value.trim()) return
  loading.value = true
  fetchError.value = ''
  track.value = null
  downloadError.value = ''
  downloadSuccess.value = ''
  progress.value = 0
  progressText.value = 'Wachten op download...'

  try {
    const res = await fetch(`${API}/api/track?url=${encodeURIComponent(trackUrl.value.trim())}`)
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      fetchError.value = data.detail || `Fout ${res.status}: Kan track niet ophalen.`
      return
    }
    track.value = await res.json()
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

  try {
    const res = await fetch(`${API}/api/download?url=${encodeURIComponent(trackUrl.value.trim())}`)
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      downloadError.value = data.detail || `Fout ${res.status}: Download mislukt.`
      return
    }

    const contentLength = res.headers.get('content-length')
    const totalBytes = contentLength ? parseInt(contentLength, 10) : 0
    const reader = res.body.getReader()

    // Probeer native File System Access API (Windows Verkenner dialoog)
    const useFSA = typeof window.showSaveFilePicker === 'function'
    const ext = (track.value.extension || (track.value.filename.includes('.') ? '.' + track.value.filename.split('.').pop() : '.mp3')).toLowerCase()
    let pickerTypes = [{ description: 'MP3-audiobestand', accept: { 'audio/mpeg': ['.mp3'] } }]
    if (ext === '.m4a') {
      pickerTypes = [{ description: 'M4A-audiobestand', accept: { 'audio/mp4': ['.m4a'] } }]
    } else if (ext === '.ogg') {
      pickerTypes = [{ description: 'OGG-audiobestand', accept: { 'audio/ogg': ['.ogg'] } }]
    }

    let fileHandle = null
    let writable = null
    const chunks = []

    if (useFSA) {
      try {
        fileHandle = await window.showSaveFilePicker({
          suggestedName: track.value.filename,
          types: pickerTypes,
        })
        writable = await fileHandle.createWritable()
      } catch (err) {
        // Gebruiker annuleerde dialoog
        if (err.name === 'AbortError') {
          progressText.value = 'Download geannuleerd.'
          return
        }
        // FSA niet ondersteund of mislukt → fallback
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
      downloadSuccess.value = `'${track.value.title}' is succesvol opgeslagen!`
    } else {
      // Fallback: <a download> in de browser
      const mime = track.value.media_type || (ext === '.m4a' ? 'audio/mp4' : (ext === '.ogg' ? 'audio/ogg' : 'audio/mpeg'))
      const blob = new Blob(chunks, { type: mime })
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = track.value.filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      progress.value = 100
      progressText.value = 'Download klaar!'
      downloadSuccess.value = `'${track.value.title}' is succesvol gedownload!`
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
.track-label { font-size: .68rem; font-weight: 700; letter-spacing: .07em; color: var(--accent); text-transform: uppercase; }
.track-title { font-size: 1.1rem; font-weight: 700; color: var(--text); line-height: 1.3; word-break: break-word; }
.track-artist { color: var(--muted); font-size: .875rem; }
.track-duration { color: var(--muted); font-size: .8rem; }
.track-filename { color: var(--muted); font-size: .78rem; word-break: break-all; }

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
