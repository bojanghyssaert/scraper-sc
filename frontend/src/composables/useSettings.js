/**
 * Composable voor gebruikersinstellingen (volume-normalisatie, localStorage).
 */

import { ref, watch } from 'vue'

const STORAGE_KEY_NORMALIZE = 'sc_normalize_volume'

function getSavedNormalize() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY_NORMALIZE)
    if (saved !== null) {
      return saved === 'true'
    }
  } catch {
    // Negeer localStorage fouten
  }
  return false
}

export function useSettings() {
  const normalizeAudio = ref(getSavedNormalize())

  watch(normalizeAudio, (newVal) => {
    try {
      localStorage.setItem(STORAGE_KEY_NORMALIZE, String(newVal))
    } catch {
      // Negeer localStorage fouten
    }
  })

  return {
    normalizeAudio,
  }
}
