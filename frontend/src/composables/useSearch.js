/**
 * Composable voor SoundCloud zoekfunctionaliteit en invoermodus.
 */

import { ref } from 'vue'
import { isSoundCloudUrl, searchSoundCloud } from '../services/api'

export function useSearch({ onSelectTrack = () => {}, onUrlPasted = () => {} } = {}) {
  const inputMode = ref('search')
  const searchQuery = ref('')
  const searching = ref(false)
  const searchResults = ref([])
  const searchError = ref('')
  const hasSearched = ref(false)
  const lastSearchedQuery = ref('')

  function setMode(mode) {
    inputMode.value = mode
    searchError.value = ''
  }

  function clearSearch() {
    searchResults.value = []
    searchQuery.value = ''
    hasSearched.value = false
    searchError.value = ''
  }

  async function performSearch() {
    const query = searchQuery.value.trim()
    if (!query) return

    // Als er direct een SoundCloud URL wordt ingegeven in het zoekveld
    if (isSoundCloudUrl(query)) {
      inputMode.value = 'url'
      onUrlPasted(query)
      return
    }

    searching.value = true
    searchError.value = ''
    hasSearched.value = true
    lastSearchedQuery.value = query

    try {
      const results = await searchSoundCloud(query, 8)
      searchResults.value = results
    } catch (err) {
      searchError.value = err.message || 'Verbindingsfout: controleer of de backend actief is op poort 8000.'
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }

  function selectSearchResult(item) {
    if (item && item.permalink_url) {
      onSelectTrack(item.permalink_url)
    }
  }

  function handleSearchPaste(event) {
    const pastedText = (event.clipboardData || window.clipboardData)?.getData('text') || ''
    const trimmed = pastedText.trim()
    if (isSoundCloudUrl(trimmed)) {
      event.preventDefault()
      clearSearch()
      inputMode.value = 'url'
      onUrlPasted(trimmed)
    }
  }

  return {
    inputMode,
    searchQuery,
    searching,
    searchResults,
    searchError,
    hasSearched,
    lastSearchedQuery,
    setMode,
    clearSearch,
    performSearch,
    selectSearchResult,
    handleSearchPaste,
  }
}
