import { ref } from 'vue'

const isFocusMode = ref(false)

function _apply() {
  document.body.classList.toggle('focus-mode', isFocusMode.value)
}

export function toggleFocusMode() {
  isFocusMode.value = !isFocusMode.value
  _apply()
}

export function exitFocusMode() {
  if (!isFocusMode.value) return
  isFocusMode.value = false
  _apply()
}

export function useFocusMode() {
  return { isFocusMode, toggleFocusMode, exitFocusMode }
}
