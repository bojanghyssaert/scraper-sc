import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PlaylistPanel from '../components/PlaylistPanel.vue'

describe('components/PlaylistPanel.vue', () => {
  const mockPlaylist = {
    title: 'Festival Set',
    artist: 'DJ Martin',
    artwork_url: '',
    tracks: [
      {
        url: 'https://soundcloud.com/dj/track1',
        title: 'Opening Track',
        artist: 'DJ Martin',
        duration_ms: 180000,
        is_drm: false,
      },
      {
        url: 'https://soundcloud.com/dj/track2',
        title: 'VIP Remix',
        artist: 'DJ Martin',
        duration_ms: 240000,
        is_drm: true,
      },
    ],
  }

  it('rendert playlist informatie en tracks', () => {
    const wrapper = mount(PlaylistPanel, {
      props: {
        playlist: mockPlaylist,
        selectedTrackUrls: new Set(['https://soundcloud.com/dj/track1']),
        downloadableTracksCount: 1,
        formatPlaylistTotalDuration: '7:00',
        allSelected: true,
        normalizeAudio: false,
      },
    })

    expect(wrapper.text()).toContain('Festival Set')
    expect(wrapper.text()).toContain('DJ Martin')
    expect(wrapper.text()).toContain('Opening Track')
    expect(wrapper.text()).toContain('VIP Remix')
    expect(wrapper.text()).toContain('DRM')
  })

  it('vuurt toggle-select-all af bij klikken op selectieknop', async () => {
    const wrapper = mount(PlaylistPanel, {
      props: {
        playlist: mockPlaylist,
        selectedTrackUrls: new Set(),
        downloadableTracksCount: 1,
        allSelected: false,
      },
    })

    const selectAllBtn = wrapper.find('.playlist-toolbar button')
    await selectAllBtn.trigger('click')
    expect(wrapper.emitted('toggle-select-all')).toBeTruthy()
  })

  it('vuurt download-zip af bij klikken op zip-downloadknop', async () => {
    const wrapper = mount(PlaylistPanel, {
      props: {
        playlist: mockPlaylist,
        selectedTrackUrls: new Set(['https://soundcloud.com/dj/track1']),
        downloadableTracksCount: 1,
        allSelected: true,
        downloadingZip: false,
      },
    })

    const zipBtn = wrapper.find('button.btn-accent.btn-full')
    await zipBtn.trigger('click')
    expect(wrapper.emitted('download-zip')).toBeTruthy()
  })
})
