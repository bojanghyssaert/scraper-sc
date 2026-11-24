import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  isSoundCloudUrl,
  formatDuration,
  getTrackInfo,
  searchSoundCloud,
  getPreviewAudioUrl,
  downloadPlaylistZipBlob,
} from '../services/api'

describe('services/api.js', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  describe('isSoundCloudUrl', () => {
    it('herkent geldige SoundCloud URLs', () => {
      expect(isSoundCloudUrl('https://soundcloud.com/artist/track')).toBe(true)
      expect(isSoundCloudUrl('http://soundcloud.com/artist/track')).toBe(true)
      expect(isSoundCloudUrl('https://m.soundcloud.com/artist/track')).toBe(true)
      expect(isSoundCloudUrl('https://on.soundcloud.com/abc123xyz')).toBe(true)
      expect(isSoundCloudUrl('soundcloud.com/artist/track')).toBe(true)
    })

    it('weigert ongeldige of vreemde URLs', () => {
      expect(isSoundCloudUrl('')).toBe(false)
      expect(isSoundCloudUrl(null)).toBe(false)
      expect(isSoundCloudUrl('https://spotify.com/track/123')).toBe(false)
      expect(isSoundCloudUrl('https://soundcloud.com/')).toBe(false)
      expect(isSoundCloudUrl('soundcloud.com')).toBe(false)
      expect(isSoundCloudUrl('willekeurige tekst')).toBe(false)
    })
  })

  describe('formatDuration', () => {
    it('formatteert milliseconden naar mm:ss', () => {
      expect(formatDuration(0)).toBe('0:00')
      expect(formatDuration(null)).toBe('0:00')
      expect(formatDuration(65000)).toBe('1:05')
      expect(formatDuration(180000)).toBe('3:00')
      expect(formatDuration(3600000)).toBe('60:00')
    })
  })

  describe('getTrackInfo', () => {
    it('haalt succesvol track metadata op', async () => {
      const mockData = {
        type: 'track',
        title: 'Test Track',
        artist: 'Test Artist',
        formats: [{ id: 'mp3', label: 'MP3' }],
      }
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => mockData,
      })

      const result = await getTrackInfo('https://soundcloud.com/artist/test-track')
      expect(result.title).toBe('Test Track')
      expect(global.fetch).toHaveBeenCalledTimes(1)
      expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/track?url='))
    })

    it('werpt fout op bij HTTP fouten', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Track niet gevonden' }),
      })

      await expect(getTrackInfo('https://soundcloud.com/artist/missing')).rejects.toThrow('Track niet gevonden')
    })

    it('herkent DRM-foutstatus (403)', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({ detail: 'DRM-beveiligd door SoundCloud' }),
      })

      try {
        await getTrackInfo('https://soundcloud.com/artist/drm-track')
        expect.unreachable()
      } catch (err) {
        expect(err.isDrm).toBe(true)
        expect(err.message).toContain('DRM')
      }
    })
  })

  describe('searchSoundCloud', () => {
    it('geeft een lege lijst terug bij een lege query', async () => {
      const results = await searchSoundCloud('')
      expect(results).toEqual([])
    })

    it('haalt zoekresultaten op', async () => {
      const mockResults = [{ id: 1, title: 'Result 1' }, { id: 2, title: 'Result 2' }]
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ results: mockResults }),
      })

      const results = await searchSoundCloud('ODESZA', 8)
      expect(results).toHaveLength(2)
      expect(results[0].title).toBe('Result 1')
    })

    it('werpt een fout op bij serverfout', async () => {
      global.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'Zoekfout' }),
      })

      await expect(searchSoundCloud('test')).rejects.toThrow('Zoekfout')
    })
  })

  describe('getPreviewAudioUrl', () => {
    it('bouwt een correcte preview-URL met format_id', () => {
      const url = getPreviewAudioUrl('https://soundcloud.com/artist/track', 'm4a')
      expect(url).toContain('/api/preview?url=')
      expect(url).toContain('&format_id=m4a')
    })

    it('geeft lege string terug bij lege trackUrl', () => {
      expect(getPreviewAudioUrl('')).toBe('')
      expect(getPreviewAudioUrl(null)).toBe('')
    })
  })

  describe('downloadPlaylistZipBlob', () => {
    it('stuurt POST-verzoek en geeft een blob terug', async () => {
      const mockBlob = new Blob(['mock zip content'], { type: 'application/zip' })
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        blob: async () => mockBlob,
      })

      const blob = await downloadPlaylistZipBlob({
        playlistTitle: 'Summer Vibes',
        trackUrls: ['https://soundcloud.com/a/1'],
        normalize: true,
      })

      expect(blob).toBeInstanceOf(Blob)
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/download-zip'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            playlist_title: 'Summer Vibes',
            track_urls: ['https://soundcloud.com/a/1'],
            normalize: true,
          }),
        })
      )
    })
  })
})
