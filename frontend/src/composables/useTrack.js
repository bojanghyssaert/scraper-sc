/**
 * Composable voor track- en playlist-metadata, actieve formaten en previews.
 */

import { computed, ref, watch } from 'vue'
import { formatDuration, getPreviewAudioUrl, getTrackInfo } from '../services/api'

export function useTrack({ onResetPlayer = () => {}, onResetDownload = () => {} } = {}) {
  const trackUrl = ref('')
  const track = ref(null)
  const playlist = ref(null)
  const loading = ref(false)
  const fetchError = ref('')
  const drmInfo = ref(null)
  const selectedFormatId = ref('')

  // Gekozen formaatobject
  const selectedFormat = computed(() => {
    if (!track.value?.formats?.length) return null
    return track.value.formats.find(f => f.id === selectedFormatId.value) || track.value.formats[0]
  })

  // Dynamische bestandsnaam met juiste extensie
  const currentFilename = computed(() => {
    if (!track.value) return ''
    const baseName = track.value.filename.replace(/\.[a-zA-Z0-9]+$/, '')
    const ext = selectedFormat.value?.extension || track.value.extension || '.mp3'
    return `${baseName}${ext}`
  })

  // Tekst op downloadknop
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

  // Preview URL voor AudioPlayer
  const previewAudioUrl = computed(() => {
    if (!track.value || !trackUrl.value.trim()) return ''
    return getPreviewAudioUrl(trackUrl.value, selectedFormatId.value)
  })

  // Aantal downloadbare tracks in de playlist
  const downloadableTracksCount = computed(() => {
    if (!playlist.value?.tracks) return 0
    return playlist.value.tracks.filter(t => !t.is_drm).length
  })

  // Totale duur van playlist opgemaakt als mm:ss
  const formatPlaylistTotalDuration = computed(() => {
    if (!playlist.value?.tracks) return ''
    const totalMs = playlist.value.tracks.reduce((acc, t) => acc + (t.duration_ms || 0), 0)
    return formatDuration(totalMs)
  })

  function closePreview() {
    onResetPlayer()
    onResetDownload()
    track.value = null
    playlist.value = null
    trackUrl.value = ''
    fetchError.value = ''
    drmInfo.value = null
    selectedFormatId.value = ''
  }

  // Reset speler bij wijziging van URL
  watch(trackUrl, () => {
    onResetPlayer()
    onResetDownload()
    playlist.value = null
  })

  async function fetchTrack(targetUrl = '') {
    const url = targetUrl || trackUrl.value.trim()
    if (!url) return

    trackUrl.value = url
    onResetPlayer()
    onResetDownload()
    loading.value = true
    fetchError.value = ''
    drmInfo.value = null
    track.value = null
    playlist.value = null
    selectedFormatId.value = ''

    try {
      const data = await getTrackInfo(url)
      if (data.type === 'playlist') {
        playlist.value = data
        track.value = null
      } else {
        track.value = data
        playlist.value = null
        if (data.formats && data.formats.length > 0) {
          selectedFormatId.value = data.formats[0].id
        }
      }
      return data
    } catch (err) {
      if (err.isDrm) {
        drmInfo.value = {
          message: err.message || 'Dit nummer is DRM-beveiligd door SoundCloud en kan niet worden gedownload.',
          url: err.targetUrl || url,
        }
      } else {
        fetchError.value = err.message || 'Fout bij het ophalen van de track.'
      }
    } finally {
      loading.value = false
    }
  }

  return {
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
  }
}
