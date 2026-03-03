import { ref, computed } from 'vue'

const overrideManual = ref(false)
const conductorEnabled = ref(false)

export function useAutoMode() {
  const isAutoMode = computed(() => conductorEnabled.value && !overrideManual.value)

  function enterManualMode() {
    overrideManual.value = true
  }

  function exitManualMode() {
    overrideManual.value = false
  }

  function setConductorEnabled(enabled: boolean) {
    conductorEnabled.value = enabled
  }

  return { isAutoMode, overrideManual, conductorEnabled, enterManualMode, exitManualMode, setConductorEnabled }
}
