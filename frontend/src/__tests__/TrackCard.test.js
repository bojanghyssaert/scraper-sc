import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TrackCard from '../components/TrackCard.vue'

describe('components/TrackCard.vue', () => {
  const mockTrack = {
    title: 'Awesome Track',
    artist: 'Great Artist',
    artwork_url: 'https://i1.sndcdn.com/artworks-sample.jpg',
    duration_ms: 215000,
    filename: 'Great Artist - Awesome Track.mp3',
    formats: [
      { id: 'mp3', label: 'MP3 (Standaard)', extension: '.mp3' },
      { id: 'm4a', label: 'MP3 (via M4A)', extension: '.mp3' },
    ],
  }

  it('rendert track metadata correct', () => {
    const wrapper = mount(TrackCard, {
      props: {
        track: mockTrack,
        selectedFormatId: 'mp3',
        selectedFormat: mockTrack.formats[0],
        currentFilename: 'Great Artist - Awesome Track.mp3',
        downloadButtonFormat: 'MP3',
        previewAudioUrl: 'http://localhost:8000/api/preview?url=test',
        normalizeAudio: false,
      },
    })

    expect(wrapper.text()).toContain('Awesome Track')
    expect(wrapper.text()).toContain('Great Artist')
    expect(wrapper.text()).toContain('3:35')
    expect(wrapper.text()).toContain('Great Artist - Awesome Track.mp3')
    expect(wrapper.find('select.format-select').exists()).toBe(true)
  })

  it('vuurt download event af bij klikken op downloadknop', async () => {
    const wrapper = mount(TrackCard, {
      props: {
        track: mockTrack,
        selectedFormatId: 'mp3',
        selectedFormat: mockTrack.formats[0],
        currentFilename: 'Great Artist - Awesome Track.mp3',
        downloadButtonFormat: 'MP3',
        previewAudioUrl: 'http://localhost:8000/api/preview?url=test',
        normalizeAudio: false,
        downloading: false,
      },
    })

    const downloadBtn = wrapper.find('button.btn-accent.btn-full')
    await downloadBtn.trigger('click')
    expect(wrapper.emitted('download')).toBeTruthy()
  })

  it('vuurt close event af bij klikken op sluitknop', async () => {
    const wrapper = mount(TrackCard, {
      props: {
        track: mockTrack,
        selectedFormatId: 'mp3',
        selectedFormat: mockTrack.formats[0],
        currentFilename: 'Great Artist - Awesome Track.mp3',
        downloadButtonFormat: 'MP3',
        previewAudioUrl: 'http://localhost:8000/api/preview?url=test',
        normalizeAudio: false,
      },
    })

    const closeBtn = wrapper.find('.btn-close-preview')
    await closeBtn.trigger('click')
    expect(wrapper.emitted('close')).toBeTruthy()
  })

  it('vuurt update:normalizeAudio af bij schakelen van toggle', async () => {
    const wrapper = mount(TrackCard, {
      props: {
        track: mockTrack,
        selectedFormatId: 'mp3',
        selectedFormat: mockTrack.formats[0],
        currentFilename: 'Great Artist - Awesome Track.mp3',
        downloadButtonFormat: 'MP3',
        previewAudioUrl: 'http://localhost:8000/api/preview?url=test',
        normalizeAudio: false,
      },
    })

    const toggle = wrapper.find('#normalize-toggle-track')
    await toggle.setChecked(true)
    expect(wrapper.emitted('update:normalizeAudio')).toBeTruthy()
    expect(wrapper.emitted('update:normalizeAudio')[0]).toEqual([true])
  })
})
