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
      <p class="subtitle">Zoek op SoundCloud of voer een track-link in om direct te beluisteren en downloaden</p>
    </header>

    <!-- ── Invoerkaart ── -->
    <section class="card input-card" :class="{ 'has-results': searchResults.length > 0 }">
      <!-- Modus-schakelaar: Zoek op naam / Plak URL -->
      <div class="mode-switch">
        <button
          type="button"
          class="mode-btn"
          :class="{ active: inputMode === 'search' }"
          @click="setMode('search')"
        >
          🔍 Zoek op naam
        </button>
        <button
          type="button"
          class="mode-btn"
          :class="{ active: inputMode === 'url' }"
          @click="setMode('url')"
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
            v-model="searchQuery"
            class="url-input"
            type="text"
            placeholder="Artiest of titel (bijv. Flume, Odesza, Martin Garrix)..."
            @keyup.enter="performSearch"
            @paste="handleSearchPaste"
            :disabled="searching || loading || downloading"
            autocomplete="off"
            spellcheck="false"
          />
          <button
            class="btn btn-accent"
            @click="performSearch"
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
          <div v-if="searchResults.length > 0" class="search-results">
            <div class="search-results-header">
              <span class="field-label">ZOEKRESULTATEN ({{ searchResults.length }})</span>
              <button type="button" class="btn-text" @click="clearSearch" title="Resultaten wissen">
                ✕ Wissen
              </button>
            </div>

            <div class="search-list" :class="{ 'has-preview': track || playlist }">
              <div
                v-for="item in searchResults"
                :key="item.permalink_url"
                class="search-item"
                :class="{
                  'is-selected': trackUrl === item.permalink_url && track,
                  'is-drm': item.is_drm,
                }"
                @click="selectSearchResult(item)"
                role="button"
                tabindex="0"
                @keydown.enter="selectSearchResult(item)"
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
                    {{ trackUrl === item.permalink_url && track ? 'Geselecteerd' : 'Kies track' }}
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
                v-model="normalizeAudio"
                :disabled="downloading"
                class="toggle-checkbox"
              />
              <span class="toggle-slider"></span>
            </span>
          </label>
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

    <!-- ── Playlist / Album Kaart ── -->
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
              <span class="track-label">PLAYLIST / ALBUM</span>
              <span class="badge-playlist-count">📁 {{ playlist.tracks ? playlist.tracks.length : 0 }} nummers</span>
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
            @click="toggleSelectAll"
            :disabled="downloadingZip || downloadableTracksCount === 0"
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
            @click="!t.is_drm && toggleTrackSelection(t.url)"
          >
            <div class="playlist-item-check" @click.stop>
              <input
                type="checkbox"
                :checked="selectedTrackUrls.has(t.url)"
                :disabled="t.is_drm || downloadingZip"
                @change="toggleTrackSelection(t.url)"
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
                v-model="normalizeAudio"
                :disabled="downloadingZip"
                class="toggle-checkbox"
              />
              <span class="toggle-slider"></span>
            </span>
          </label>
        </div>

        <!-- Download knop -->
        <button
          class="btn btn-accent btn-full"
          @click="downloadPlaylistZip"
          :disabled="selectedTrackUrls.size === 0 || downloadingZip"
        >
          <span v-if="downloadingZip" class="spinner"></span>
          <span v-else>📦 Download selectie als .zip ({{ selectedTrackUrls.size }} {{ selectedTrackUrls.size === 1 ? 'track' : 'tracks' }})</span>
        </button>

        <p v-if="zipError" class="status error">❌ {{ zipError }}</p>
        <p v-if="zipSuccess" class="status success">✅ {{ zipSuccess }}</p>
      </section>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import AudioPlayer from './components/AudioPlayer.vue'

const API = 'http://localhost:8000'

const inputMode         = ref('search')
const searchQuery       = ref('')
const searching         = ref(false)
const searchResults     = ref([])
const searchError       = ref('')
const hasSearched       = ref(false)
const lastSearchedQuery = ref('')

const trackUrl          = ref('')
const track             = ref(null)
const playlist          = ref(null)
const selectedTrackUrls = ref(new Set())
const downloadingZip    = ref(false)
const zipProgressText   = ref('')
const zipError          = ref('')
const zipSuccess        = ref('')

const downloadableTracksCount = computed(() => {
  if (!playlist.value?.tracks) return 0
  return playlist.value.tracks.filter(t => !t.is_drm).length
})

const allSelected = computed(() => {
  const count = downloadableTracksCount.value
  return count > 0 && selectedTrackUrls.value.size >= count
})

const formatPlaylistTotalDuration = computed(() => {
  if (!playlist.value?.tracks) return ''
  const totalMs = playlist.value.tracks.reduce((acc, t) => acc + (t.duration_ms || 0), 0)
  return formatDuration(totalMs)
})

const selectedFormatId  = ref('')
const loading           = ref(false)
const fetchError        = ref('')
const drmInfo           = ref(null)
const downloading       = ref(false)
const downloadError     = ref('')
const downloadSuccess   = ref('')
const progress          = ref(0)
const progressText      = ref('Wachten op download...')
const audioPlayerRef    = ref(null)

const STORAGE_KEY_NORMALIZE = 'sc_normalize_volume'
const getSavedNormalize = () => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY_NORMALIZE)
    if (saved !== null) {
      return saved === 'true'
    }
  } catch {
    // Negeer localStorage fouten
  }
  return false
}
const normalizeAudio    = ref(getSavedNormalize())

watch(normalizeAudio, (newVal) => {
  try {
    localStorage.setItem(STORAGE_KEY_NORMALIZE, String(newVal))
  } catch {
    // Negeer localStorage fouten
  }
})

const previewAudioUrl = computed(() => {
  if (!track.value || !trackUrl.value.trim()) return ''
  let url = `${API}/api/preview?url=${encodeURIComponent(trackUrl.value.trim())}`
  if (selectedFormatId.value) {
    url += `&format_id=${encodeURIComponent(selectedFormatId.value)}`
  }
  return url
})

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

// ── Modus-beheer ──
function setMode(mode) {
  inputMode.value = mode
  searchError.value = ''
  fetchError.value = ''
}

// ── SoundCloud Zoeken ──
async function performSearch() {
  const query = searchQuery.value.trim()
  if (!query) return

  // Als er een geldige SoundCloud URL wordt ingevoerd in het zoekveld
  if (isSoundCloudUrl(query)) {
    inputMode.value = 'url'
    trackUrl.value = query
    fetchTrack()
    return
  }

  searching.value = true
  searchError.value = ''
  hasSearched.value = true
  lastSearchedQuery.value = query

  try {
    const res = await fetch(`${API}/api/search?q=${encodeURIComponent(query)}&limit=8`)
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      searchError.value = data.detail || `Fout ${res.status}: Kan zoekresultaten niet ophalen.`
      searchResults.value = []
      return
    }
    const data = await res.json()
    searchResults.value = Array.isArray(data.results) ? data.results : []
  } catch (err) {
    searchError.value = 'Verbindingsfout: controleer of de backend actief is op poort 8000.'
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

function clearSearch() {
  searchResults.value = []
  searchQuery.value = ''
  hasSearched.value = false
  searchError.value = ''
}

function selectSearchResult(item) {
  trackUrl.value = item.permalink_url
  fetchTrack()
}

function handleSearchPaste(event) {
  const pastedText = (event.clipboardData || window.clipboardData)?.getData('text') || ''
  const trimmed = pastedText.trim()
  if (isSoundCloudUrl(trimmed)) {
    event.preventDefault()
    inputMode.value = 'url'
    trackUrl.value = trimmed
    fetchTrack()
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

// ── Reset speler bij wijziging van URL ──
watch(trackUrl, () => {
  if (audioPlayerRef.value) {
    audioPlayerRef.value.reset()
  }
  playlist.value = null
  selectedTrackUrls.value = new Set()
  zipError.value = ''
  zipSuccess.value = ''
  zipProgressText.value = ''
})

// ── Playlist selectie beheer ──
function toggleTrackSelection(url) {
  if (!url) return
  const newSet = new Set(selectedTrackUrls.value)
  if (newSet.has(url)) {
    newSet.delete(url)
  } else {
    newSet.add(url)
  }
  selectedTrackUrls.value = newSet
}

function toggleSelectAll() {
  if (!playlist.value?.tracks) return
  if (allSelected.value) {
    selectedTrackUrls.value = new Set()
  } else {
    const allNonDrm = playlist.value.tracks.filter(t => !t.is_drm).map(t => t.url).filter(Boolean)
    selectedTrackUrls.value = new Set(allNonDrm)
  }
}

// ── Track of playlist ophalen ──
async function fetchTrack() {
  if (!trackUrl.value.trim()) return
  if (audioPlayerRef.value) {
    audioPlayerRef.value.reset()
  }
  loading.value = true
  fetchError.value = ''
  drmInfo.value = null
  track.value = null
  playlist.value = null
  selectedTrackUrls.value = new Set()
  zipError.value = ''
  zipSuccess.value = ''
  zipProgressText.value = ''
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
    if (trackData.type === 'playlist') {
      playlist.value = trackData
      track.value = null
      // Standaard alle niet-DRM nummers aangevinkt
      const nonDrmUrls = (trackData.tracks || [])
        .filter(t => !t.is_drm && t.url)
        .map(t => t.url)
      selectedTrackUrls.value = new Set(nonDrmUrls)
    } else {
      track.value = trackData
      playlist.value = null
      if (trackData.formats && trackData.formats.length > 0) {
        selectedFormatId.value = trackData.formats[0].id
      }
    }
  } catch (err) {
    fetchError.value = 'Verbindingsfout: controleer of de backend actief is op poort 8000.'
  } finally {
    loading.value = false
  }
}

// ── Batch download als .zip ──
async function downloadPlaylistZip() {
  if (!playlist.value || selectedTrackUrls.value.size === 0) return

  downloadingZip.value = true
  zipError.value = ''
  zipSuccess.value = ''
  zipProgressText.value = 'Tracks downloaden en ZIP-archief samenstellen...'

  const urlsToDownload = Array.from(selectedTrackUrls.value)
  const safeTitle = (playlist.value.title || 'playlist').replace(/[/\\?%*:|"<>]/g, '_').trim() || 'playlist'
  const suggestedFilename = `${safeTitle}.zip`

  try {
    const res = await fetch(`${API}/api/download-zip`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        playlist_title: playlist.value.title,
        track_urls: urlsToDownload,
        normalize: normalizeAudio.value,
      }),
    })

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      zipError.value = data.detail || `Fout ${res.status}: Download van ZIP mislukt.`
      return
    }

    zipProgressText.value = 'ZIP-archief ontvangen...'
    const blob = await res.blob()

    // Probeer native File System Access API (window.showSaveFilePicker)
    const useFSA = typeof window.showSaveFilePicker === 'function'
    let fileHandle = null

    if (useFSA) {
      try {
        fileHandle = await window.showSaveFilePicker({
          suggestedName: suggestedFilename,
          types: [
            {
              description: 'ZIP-archief',
              accept: { 'application/zip': ['.zip'] },
            },
          ],
        })
        const writable = await fileHandle.createWritable()
        await writable.write(blob)
        await writable.close()
        zipSuccess.value = `'${suggestedFilename}' is succesvol opgeslagen!`
        zipProgressText.value = 'Voltooid!'
        return
      } catch (err) {
        if (err.name === 'AbortError') {
          zipProgressText.value = 'Download geannuleerd.'
          return
        }
        fileHandle = null
      }
    }

    // Fallback: programmatisch <a> download element
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = suggestedFilename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    zipSuccess.value = `'${suggestedFilename}' is succesvol gedownload!`
    zipProgressText.value = 'Download voltooid!'
  } catch (err) {
    zipError.value = `Onverwachte fout: ${err.message}`
  } finally {
    downloadingZip.value = false
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
  const normalizeQuery = `&normalize=${normalizeAudio.value}`

  try {
    const res = await fetch(`${API}/api/download?url=${encodeURIComponent(targetUrl)}${formatQuery}${normalizeQuery}`)
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
  height: 100%;
  max-height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  gap: 12px;
}

/* Header */
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

/* Card */
.card {
  background: var(--card);
  border-radius: var(--radius);
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.input-card {
  flex-shrink: 0;
}

.input-card.has-results {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* Modus-schakelaar */
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

/* Zoekresultaten */
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
  transition: color 0.15s;
}
.btn-text:hover {
  color: var(--text);
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
.search-list.has-preview {
  flex: 0 1 auto;
  max-height: min(150px, calc(100vh - 540px));
  max-height: min(150px, calc(100dvh - 540px));
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

/* Labels */
.field-label {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: var(--accent);
  flex-shrink: 0;
}

/* Input row */
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
.preview-card {
  gap: 14px;
  flex-shrink: 0;
  min-height: 0;
  padding: 16px 20px;
}
.preview {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  flex-shrink: 0;
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

/* Player */
.player-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
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

/* Playlist card & tracklist */
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
  flex-shrink: 0;
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
.btn-sm {
  padding: 6px 12px;
  font-size: 0.78rem;
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
.playlist-card .progress-block {
  flex-shrink: 0;
}
.playlist-card .btn-full {
  flex-shrink: 0;
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

/* Volume-normalisatie toggle */
.normalize-block {
  background: #242424;
  border: 1px solid #3D3D3D;
  border-radius: 8px;
  padding: 10px 14px;
  flex-shrink: 0;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.normalize-block:hover {
  border-color: #555555;
}

.toggle-control {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  cursor: pointer;
  user-select: none;
}

.toggle-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toggle-icon {
  font-size: 1.05rem;
}

.toggle-label {
  font-size: 0.88rem;
  font-weight: 500;
  color: var(--text);
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
}

.toggle-checkbox {
  opacity: 0;
  width: 0;
  height: 0;
  position: absolute;
}

.toggle-slider {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #3D3D3D;
  border-radius: 24px;
  transition: 0.25s ease;
}

.toggle-slider::before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: #FFFFFF;
  border-radius: 50%;
  transition: 0.25s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
}

.toggle-checkbox:checked + .toggle-slider {
  background-color: #FF5500;
}

.toggle-checkbox:checked + .toggle-slider::before {
  transform: translateX(20px);
}

.toggle-checkbox:focus-visible + .toggle-slider {
  outline: 2px solid #FF5500;
  outline-offset: 2px;
}

.toggle-checkbox:disabled + .toggle-slider {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Status */
.status { font-size: .875rem; padding: 2px 0; }
.error   { color: var(--error); }
.success { color: var(--success); }

/* Transition */
.fade-enter-active, .fade-leave-active { transition: opacity .3s, transform .3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(8px); }
</style>