import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useSettings } from '../composables/useSettings'
import { useSearch } from '../composables/useSearch'
import { useDownload } from '../composables/useDownload'

describe('Composables', () => {
  describe('useSettings', () => {
    beforeEach(() => {
      localStorage.clear()
    })

    it('leest de standaardwaarde (false) indien leeg in localStorage', () => {
      const { normalizeAudio } = useSettings()
      expect(normalizeAudio.value).toBe(false)
    })

    it('leest opgeslagen waarde true uit localStorage', () => {
      localStorage.setItem('sc_normalize_volume', 'true')
      const { normalizeAudio } = useSettings()
      expect(normalizeAudio.value).toBe(true)
    })
  })

  describe('useSearch', () => {
    it('wisselt invoermodus correct', () => {
      const { inputMode, setMode } = useSearch()
      expect(inputMode.value).toBe('search')
      setMode('url')
      expect(inputMode.value).toBe('url')
    })

    it('wist zoekresultaten en query via clearSearch()', () => {
      const { searchQuery, searchResults, hasSearched, clearSearch } = useSearch()
      searchQuery.value = 'test'
      searchResults.value = [{ title: 'Track 1' }]
      hasSearched.value = true

      clearSearch()
      expect(searchQuery.value).toBe('')
      expect(searchResults.value).toEqual([])
      expect(hasSearched.value).toBe(false)
    })

    it('roept onSelectTrack aan bij selectSearchResult', () => {
      const onSelect = vi.fn()
      const { selectSearchResult } = useSearch({ onSelectTrack: onSelect })

      selectSearchResult({ permalink_url: 'https://soundcloud.com/artist/track' })
      expect(onSelect).toHaveBeenCalledWith('https://soundcloud.com/artist/track')
    })
  })

  describe('useDownload', () => {
    it('initialiseert playlistselectie met niet-DRM tracks', () => {
      const { selectedTrackUrls, initPlaylistSelection } = useDownload()
      const mockPlaylist = {
        tracks: [
          { url: 'https://soundcloud.com/a/1', is_drm: false },
          { url: 'https://soundcloud.com/a/2', is_drm: true },
          { url: 'https://soundcloud.com/a/3', is_drm: false },
        ],
      }

      initPlaylistSelection(mockPlaylist)
      expect(selectedTrackUrls.value.size).toBe(2)
      expect(selectedTrackUrls.value.has('https://soundcloud.com/a/1')).toBe(true)
      expect(selectedTrackUrls.value.has('https://soundcloud.com/a/2')).toBe(false)
    })

    it('schakelt trackselectie in en uit via toggleTrackSelection', () => {
      const { selectedTrackUrls, toggleTrackSelection } = useDownload()

      toggleTrackSelection('https://soundcloud.com/a/1')
      expect(selectedTrackUrls.value.has('https://soundcloud.com/a/1')).toBe(true)

      toggleTrackSelection('https://soundcloud.com/a/1')
      expect(selectedTrackUrls.value.has('https://soundcloud.com/a/1')).toBe(false)
    })

    it('selecteert en deselecteert alles via toggleSelectAll', () => {
      const { selectedTrackUrls, toggleSelectAll, isAllSelected } = useDownload()
      const mockPlaylist = {
        tracks: [
          { url: 'https://soundcloud.com/a/1', is_drm: false },
          { url: 'https://soundcloud.com/a/2', is_drm: false },
        ],
      }

      // Alles selecteren
      toggleSelectAll(mockPlaylist)
      expect(selectedTrackUrls.value.size).toBe(2)
      expect(isAllSelected(mockPlaylist)).toBe(true)

      // Alles deselecteren
      toggleSelectAll(mockPlaylist)
      expect(selectedTrackUrls.value.size).toBe(0)
      expect(isAllSelected(mockPlaylist)).toBe(false)
    })
  })
})
