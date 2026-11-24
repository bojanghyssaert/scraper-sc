/**
 * SoundCloud Scraper API service.
 * Bevat alle netwerkinteracties naar de FastAPI-backend en bestandsopslaglogica.
 */

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/**
 * Valideert of een string een geldige SoundCloud track- of playlist-URL is.
 */
export function isSoundCloudUrl(url) {
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

/**
 * Formatteert milliseconden naar een leesbare mm:ss string.
 */
export function formatDuration(ms) {
  if (!ms || typeof ms !== 'number') return '0:00'
  const totalSec = Math.floor(ms / 1000)
  const min = Math.floor(totalSec / 60)
  const sec = String(totalSec % 60).padStart(2, '0')
  return `${min}:${sec}`
}

/**
 * Haalt metadata op van een SoundCloud-track of playlist.
 */
export async function getTrackInfo(url) {
  const targetUrl = url.trim()
  const res = await fetch(`${API_BASE}/api/track?url=${encodeURIComponent(targetUrl)}`)
  const data = await res.json().catch(() => ({}))

  if (!res.ok) {
    const detailMsg = typeof data.detail === 'string' ? data.detail : ''
    const isDrm = res.status === 403 || detailMsg.toLowerCase().includes('drm')
    const error = new Error(detailMsg || `Fout ${res.status}: Kan track niet ophalen.`)
    error.status = res.status
    error.isDrm = isDrm
    error.detail = detailMsg
    error.targetUrl = targetUrl
    throw error
  }

  return data
}

/**
 * Zoekt tracks op SoundCloud op basis van een zoekopdracht.
 */
export async function searchSoundCloud(query, limit = 8) {
  const cleanQuery = query.trim()
  if (!cleanQuery) return []

  const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(cleanQuery)}&limit=${limit}`)
  const data = await res.json().catch(() => ({}))

  if (!res.ok) {
    const detailMsg = typeof data.detail === 'string' ? data.detail : ''
    const error = new Error(detailMsg || `Fout ${res.status}: Kan zoekresultaten niet ophalen.`)
    error.status = res.status
    throw error
  }

  return Array.isArray(data.results) ? data.results : []
}

/**
 * Genereert de volledige audio preview-URL voor weergave in de audiospeler.
 */
export function getPreviewAudioUrl(trackUrl, formatId = '') {
  if (!trackUrl || !trackUrl.trim()) return ''
  let url = `${API_BASE}/api/preview?url=${encodeURIComponent(trackUrl.trim())}`
  if (formatId) {
    url += `&format_id=${encodeURIComponent(formatId)}`
  }
  return url
}

/**
 * Slaat een blob of reeks chunks op via de File System Access API met fallback naar <a> download.
 */
export async function saveFileWithPickerOrFallback({
  blob,
  suggestedFilename,
  pickerTypes = [],
}) {
  const useFSA = typeof window.showSaveFilePicker === 'function'
  let fileHandle = null

  if (useFSA) {
    try {
      fileHandle = await window.showSaveFilePicker({
        suggestedName: suggestedFilename,
        types: pickerTypes,
      })
      const writable = await fileHandle.createWritable()
      await writable.write(blob)
      await writable.close()
      return { success: true, method: 'picker' }
    } catch (err) {
      if (err.name === 'AbortError') {
        return { success: false, aborted: true }
      }
      fileHandle = null
    }
  }

  // Fallback naar <a download>
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = suggestedFilename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  return { success: true, method: 'fallback' }
}

/**
 * Downloadt een track via chunked streaming en roept optioneel de progress-callback aan.
 */
export async function downloadTrackStream({
  trackUrl,
  formatId,
  normalize = false,
  filename = 'track.mp3',
  mediaType = 'audio/mpeg',
  onProgress = () => {},
}) {
  const targetUrl = trackUrl.trim()
  const formatQuery = formatId ? `&format_id=${encodeURIComponent(formatId)}` : ''
  const normalizeQuery = `&normalize=${normalize}`

  const res = await fetch(`${API_BASE}/api/download?url=${encodeURIComponent(targetUrl)}${formatQuery}${normalizeQuery}`)
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const detailMsg = typeof data.detail === 'string' ? data.detail : ''
    const isDrm = res.status === 403 || detailMsg.toLowerCase().includes('drm')
    const error = new Error(detailMsg || `Fout ${res.status}: Download mislukt.`)
    error.status = res.status
    error.isDrm = isDrm
    error.targetUrl = targetUrl
    throw error
  }

  const contentLength = res.headers.get('content-length')
  const totalBytes = contentLength ? parseInt(contentLength, 10) : 0
  const reader = res.body.getReader()

  const ext = (filename.includes('.') ? '.' + filename.split('.').pop() : '.mp3').toLowerCase()
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
        suggestedName: filename,
        types: pickerTypes,
      })
      writable = await fileHandle.createWritable()
    } catch (err) {
      if (err.name === 'AbortError') {
        return { aborted: true }
      }
      fileHandle = null
    }
  }

  let downloaded = 0
  onProgress({ downloaded: 0, totalBytes, percent: 0, text: 'Downloaden...' })

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
      const mb = (downloaded / 1048576).toFixed(1)
      const tot = (totalBytes / 1048576).toFixed(1)
      onProgress({
        downloaded,
        totalBytes,
        percent: pct,
        text: `${mb} MB / ${tot} MB (${Math.round(pct)}%)`,
      })
    } else {
      const mb = (downloaded / 1048576).toFixed(1)
      onProgress({
        downloaded,
        totalBytes,
        percent: 0,
        text: `${mb} MB gedownload...`,
      })
    }
  }

  if (writable) {
    await writable.close()
    return { success: true, method: 'picker' }
  }

  const blob = new Blob(chunks, { type: mediaType || 'audio/mpeg' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  return { success: true, method: 'fallback' }
}

/**
 * Downloadt een selectie van tracks als één .zip-archief.
 */
export async function downloadPlaylistZipBlob({
  playlistTitle,
  trackUrls,
  normalize = false,
}) {
  const res = await fetch(`${API_BASE}/api/download-zip`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      playlist_title: playlistTitle,
      track_urls: trackUrls,
      normalize,
    }),
  })

  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const detailMsg = data.detail || `Fout ${res.status}: Download van ZIP mislukt.`
    const error = new Error(detailMsg)
    error.status = res.status
    throw error
  }

  return await res.blob()
}
