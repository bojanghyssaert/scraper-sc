<template>
  <div class="app">
    <!-- Header -->
    <AppHeader />

    <!-- Invoerkaart (Zoeken / URL plakken) -->
    <SearchPanel
      v-model:input-mode="inputMode"
      v-model:search-query="searchQuery"
      v-model:track-url="trackUrl"
      :searching="searching"
      :search-results="searchResults"
      :search-error="searchError"
      :has-searched="hasSearched"
      :last-searched-query="lastSearchedQuery"
      :loading="loading"
      :downloading="downloading || downloadingZip"
      :fetch-error="fetchError"
      :drm-info="drmInfo"
      :has-active-item="Boolean(track || playlist)"
      @search="performSearch"
      @clear-search="clearSearch"
      @select-result="onSelectResult"
      @search-paste="handleSearchPaste"
      @fetch-track="onFetchTrack"
      @url-paste="onUrlPaste"
      @paste-clipboard="onPasteClipboard"
    />

    <!-- Track Preview Kaart -->
    <TrackCard
      ref="trackCardRef"
      :track="track"
      v-model:selected-format-id="selectedFormatId"
      v-model:normalize-audio="normalizeAudio"
      :selected-format="selectedFormat"
      :current-filename="currentFilename"
      :download-button-format="downloadButtonFormat"
      :preview-audio-url="previewAudioUrl"
      :downloading="downloading"
      :downloading-zip="downloadingZip"
      :download-error="downloadError"
      :download-success="downloadSuccess"
      :progress="progress"
      :progress-text="progressText"
      :is-search-mode="inputMode === 'search'"
      :has-search-results="searchResults.length > 0"
      @close="closePreview"
      @download="onDownloadTrack"
    />

    <!-- Playlist / Album Kaart -->
    <PlaylistPanel
      :playlist="playlist"
      :selected-track-urls="selectedTrackUrls"
      :downloadable-tracks-count="downloadableTracksCount"
      :format-playlist-total-duration="formatPlaylistTotalDuration"
      :all-selected="isAllSelected(playlist)"
      v-model:normalize-audio="normalizeAudio"
      :downloading="downloading"
      :downloading-zip="downloadingZip"
      :zip-progress-text="zipProgressText"
      :zip-error="zipError"
      :zip-success="zipSuccess"
      :is-search-mode="inputMode === 'search'"
      :has-search-results="searchResults.length > 0"
      @close="closePreview"
      @toggle-track="toggleTrackSelection"
      @toggle-select-all="toggleSelectAll(playlist)"
      @download-zip="onDownloadPlaylistZip"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AppHeader from './components/AppHeader.vue'
import SearchPanel from './components/SearchPanel.vue'
import TrackCard from './components/TrackCard.vue'
import PlaylistPanel from './components/PlaylistPanel.vue'
import { useSettings } from './composables/useSettings'
import { useSearch } from './composables/useSearch'
import { useTrack } from './composables/useTrack'
import { useDownload } from './composables/useDownload'
import { isSoundCloudUrl } from './services/api'

const trackCardRef = ref(null)

// 1. Instellingen (localStorage persistentie)
const { normalizeAudio } = useSettings()

// 2. Download functionaliteit
const {
  downloading,
  downloadError,
  downloadSuccess,
  progress,
  progressText,
  selectedTrackUrls,
  downloadingZip,
  zipProgressText,
  zipError,
  zipSuccess,
  resetDownloadState,
  initPlaylistSelection,
  toggleTrackSelection,
  toggleSelectAll,
  isAllSelected,
  downloadSingleTrack,
  downloadPlaylistZip,
} = useDownload()

// 3. Track & Playlist state
const {
  trackUrl,
  track,
  playlist,
  loading,
  fetchError,
  drmInfo,
  selectedFormatId,
  selectedFormat,
  currentFilename,
  downloadButtonFormat,
  previewAudioUrl,
  downloadableTracksCount,
  formatPlaylistTotalDuration,
  closePreview,
  fetchTrack,
} = useTrack({
  onResetPlayer: () => trackCardRef.value?.resetAudioPlayer?.(),
  onResetDownload: resetDownloadState,
})

// 4. Zoek functionaliteit
const {
  inputMode,
  searchQuery,
  searching,
  searchResults,
  searchError,
  hasSearched,
  lastSearchedQuery,
  clearSearch,
  performSearch,
  handleSearchPaste,
} = useSearch({
  onSelectTrack: async (url) => {
    trackUrl.value = url
    const data = await fetchTrack(url)
    if (data?.type === 'playlist') {
      initPlaylistSelection(data)
    }
  },
  onUrlPasted: async (url) => {
    trackUrl.value = url
    const data = await fetchTrack(url)
    if (data?.type === 'playlist') {
      initPlaylistSelection(data)
    }
  },
})

async function onFetchTrack() {
  const data = await fetchTrack()
  if (data?.type === 'playlist') {
    initPlaylistSelection(data)
  }
}

function onUrlPaste(event) {
  const pastedText = (event.clipboardData || window.clipboardData)?.getData('text') || ''
  const trimmed = pastedText.trim()
  if (isSoundCloudUrl(trimmed)) {
    event.preventDefault()
    trackUrl.value = trimmed
    fetchTrack(trimmed).then((data) => {
      if (data?.type === 'playlist') {
        initPlaylistSelection(data)
      }
    })
  }
}

async function onPasteClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    const trimmed = text.trim()
    trackUrl.value = trimmed
    if (isSoundCloudUrl(trimmed)) {
      const data = await fetchTrack(trimmed)
      if (data?.type === 'playlist') {
        initPlaylistSelection(data)
      }
    }
  } catch {
    alert('Klembord-toegang niet beschikbaar. Plak de URL handmatig.')
  }
}

async function onSelectResult(item) {
  trackUrl.value = item.permalink_url
  const data = await fetchTrack(item.permalink_url)
  if (data?.type === 'playlist') {
    initPlaylistSelection(data)
  }
}

function onDownloadTrack() {
  downloadSingleTrack({
    track: track.value,
    trackUrl: trackUrl.value,
    selectedFormatId: selectedFormatId.value,
    selectedFormat: selectedFormat.value,
    currentFilename: currentFilename.value,
    normalizeAudio: normalizeAudio.value,
  })
}

function onDownloadPlaylistZip() {
  downloadPlaylistZip({
    playlist: playlist.value,
    normalizeAudio: normalizeAudio.value,
  })
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
</style>
