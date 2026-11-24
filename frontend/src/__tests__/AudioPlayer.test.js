import { describe, it, expect, vi, beforeAll } from 'vitest'
import { mount } from '@vue/test-utils'
import AudioPlayer from '../components/AudioPlayer.vue'

describe('components/AudioPlayer.vue', () => {
  beforeAll(() => {
    window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue()
    window.HTMLMediaElement.prototype.pause = vi.fn()
  })
  it('rendert de audiospeler met initiële pauzestatus', () => {
    const wrapper = mount(AudioPlayer, {
      props: {
        src: 'http://localhost:8000/api/preview?url=test',
        durationMs: 180000,
      },
    })

    expect(wrapper.find('.audio-player').exists()).toBe(true)
    expect(wrapper.find('.play-btn').exists()).toBe(true)
    expect(wrapper.text()).toContain('3:00')
    expect(wrapper.text()).toContain('0:00')
  })

  it('reset afspeelstatus via de geëxposeerde reset() methode', async () => {
    const wrapper = mount(AudioPlayer, {
      props: {
        src: 'http://localhost:8000/api/preview?url=test',
        durationMs: 120000,
      },
    })

    expect(wrapper.vm.reset).toBeDefined()
    wrapper.vm.reset()
    expect(wrapper.vm.currentTime).toBe(0)
    expect(wrapper.vm.isPlaying).toBe(false)
  })
})
