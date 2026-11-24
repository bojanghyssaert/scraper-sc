/**
 * Composable voor individuele track downloads en playlist ZIP downloads.
 */

import { computed, ref } from 'vue'
import {
  downloadPlaylistZipBlob,
  downloadTrackStream,
  saveFileWithPickerOrFallback,
} from '../services/api'

export function useDownload() {
  // Enkele track download state
  const downloading = ref(false)
  const downloadError = ref('')
  const downloadSuccess = ref('')
  const progress = ref(0)
  const progressText = ref('Wachten op download...')

  // Playlist ZIP download state
  const selectedTrackUrls = ref(new Set())
  const downloadingZip = ref(false)
  const zipProgressText = ref('')
  const zipError = ref('')
  const zipSuccess = ref('')

  function resetDownloadState() {
    downloadError.value = ''
    downloadSuccess.value = ''
    progress.value = 0
    progressText.value = 'Wachten op download...'
    zipError.value = ''
    zipSuccess.value = ''
    zipProgressText.value = ''
    selectedTrackUrls.value = new Set()
  }

  function initPlaylistSelection(playlist) {
    if (!playlist?.tracks) {
      selectedTrackUrls.value = new Set()
      return
    }
    const nonDrmUrls = playlist.tracks
      .filter(t => !t.is_drm && t.url)
      .map(t => t.url)
    selectedTrackUrls.value = new Set(nonDrmUrls)
  }

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

  function toggleSelectAll(playlist) {
    if (!playlist?.tracks) return
    const nonDrmTracks = playlist.tracks.filter(t => !t.is_drm).map(t => t.url).filter(Boolean)
    const isAll = nonDrmTracks.length > 0 && selectedTrackUrls.value.size >= nonDrmTracks.length
    if (isAll) {
      selectedTrackUrls.value = new Set()
    } else {
      selectedTrackUrls.value = new Set(nonDrmTracks)
    }
  }

  function isAllSelected(playlist) {
    if (!playlist?.tracks) return false
    const nonDrmCount = playlist.tracks.filter(t => !t.is_drm).length
    return nonDrmCount > 0 && selectedTrackUrls.value.size >= nonDrmCount
  }

  async function downloadSingleTrack({
    track,
    trackUrl,
    selectedFormatId,
    selectedFormat,
    currentFilename,
    normalizeAudio,
  }) {
    if (downloading.value || downloadingZip.value || !track) return
    downloading.value = true
    downloadError.value = ''
    downloadSuccess.value = ''
    progress.value = 0
    progressText.value = 'Verbinding maken...'

    try {
      const filename = currentFilename || 'track.mp3'
      const mediaType = selectedFormat?.media_type || track.media_type || 'audio/mpeg'

      const result = await downloadTrackStream({
        trackUrl,
        formatId: selectedFormatId,
        normalize: normalizeAudio,
        filename,
        mediaType,
        onProgress: ({ percent, text }) => {
          progress.value = percent
          progressText.value = text
        },
      })

      if (result.aborted) {
        progressText.value = 'Download geannuleerd.'
        return
      }

      progress.value = 100
      progressText.value = result.method === 'picker' ? 'Opgeslagen!' : 'Download klaar!'
      downloadSuccess.value = result.method === 'picker'
        ? `'${filename}' is succesvol opgeslagen!`
        : `'${filename}' is succesvol gedownload!`
    } catch (err) {
      downloadError.value = err.message || 'Onverwachte fout tijdens downloaden.'
    } finally {
      downloading.value = false
    }
  }

  async function downloadPlaylistZip({
    playlist,
    normalizeAudio,
  }) {
    if (downloadingZip.value || downloading.value || !playlist || selectedTrackUrls.value.size === 0) return

    downloadingZip.value = true
    zipError.value = ''
    zipSuccess.value = ''
    zipProgressText.value = 'Tracks downloaden en ZIP-archief samenstellen...'

    const urlsToDownload = Array.from(selectedTrackUrls.value)
    const safeTitle = (playlist.title || 'playlist').replace(/[/\\?%*:|"<>]/g, '_').trim() || 'playlist'
    const suggestedFilename = `${safeTitle}.zip`

    try {
      const blob = await downloadPlaylistZipBlob({
        playlistTitle: playlist.title,
        trackUrls: urlsToDownload,
        normalize: normalizeAudio,
      })

      zipProgressText.value = 'ZIP-archief ontvangen...'

      const saveResult = await saveFileWithPickerOrFallback({
        blob,
        suggestedFilename,
        pickerTypes: [
          {
            description: 'ZIP-archief',
            accept: { 'application/zip': ['.zip'] },
          },
        ],
      })

      if (saveResult.aborted) {
        zipProgressText.value = 'Download geannuleerd.'
        return
      }

      zipSuccess.value = saveResult.method === 'picker'
        ? `'${suggestedFilename}' is succesvol opgeslagen!`
        : `'${suggestedFilename}' is succesvol gedownload!`
      zipProgressText.value = 'Voltooid!'
    } catch (err) {
      zipError.value = err.message || 'Onverwachte fout bij het downloaden van de ZIP.'
    } finally {
      downloadingZip.value = false
    }
  }

  return {
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
  }
}
