import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchPanel from '../components/SearchPanel.vue'

describe('components/SearchPanel.vue', () => {
  it('rendert de zoekmodus standaard met zoekinvoer en knop', () => {
    const wrapper = mount(SearchPanel, {
      props: {
        inputMode: 'search',
        searchQuery: 'Flume',
        searching: false,
        searchResults: [],
      },
    })

    expect(wrapper.find('#search-input').exists()).toBe(true)
    expect(wrapper.find('button.btn-accent').text()).toBe('Zoeken')
    expect(wrapper.find('.mode-btn.active').text()).toContain('Zoek op naam')
  })

  it('schakelt naar URL-invoermodus', async () => {
    const wrapper = mount(SearchPanel, {
      props: {
        inputMode: 'search',
        searchQuery: '',
      },
    })

    const urlModeBtn = wrapper.findAll('.mode-btn')[1]
    await urlModeBtn.trigger('click')
    expect(wrapper.emitted('update:inputMode')).toBeTruthy()
    expect(wrapper.emitted('update:inputMode')[0]).toEqual(['url'])
  })

  it('toont zoekresultaten en vuurt select-result af bij klik', async () => {
    const mockResults = [
      {
        permalink_url: 'https://soundcloud.com/artist/hit',
        title: 'Hit Song',
        artist: 'Popular Artist',
        duration_ms: 200000,
        is_drm: false,
        artwork_url: '',
      },
    ]

    const wrapper = mount(SearchPanel, {
      props: {
        inputMode: 'search',
        searchQuery: 'Hit',
        searchResults: mockResults,
        hasActiveItem: false,
      },
    })

    expect(wrapper.text()).toContain('Hit Song')
    expect(wrapper.text()).toContain('Popular Artist')

    const item = wrapper.find('.search-item')
    await item.trigger('click')
    expect(wrapper.emitted('select-result')).toBeTruthy()
    expect(wrapper.emitted('select-result')[0]).toEqual([mockResults[0]])
  })

  it('vuurt clear-search af bij wissen van resultaten', async () => {
    const wrapper = mount(SearchPanel, {
      props: {
        inputMode: 'search',
        searchResults: [{ permalink_url: 'https://sc.com/1', title: 'T1' }],
        hasActiveItem: false,
      },
    })

    const clearBtn = wrapper.find('.btn-text')
    await clearBtn.trigger('click')
    expect(wrapper.emitted('clear-search')).toBeTruthy()
  })
})
