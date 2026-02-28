/**
 * useToast — lightweight client-side toast notifications.
 */
import { ref, readonly } from 'vue'

export interface ToastItem {
  id: number
  message: string
  level: 'success' | 'warning' | 'danger' | 'info'
}

let _nextId = 0
const toasts = ref<ToastItem[]>([])

function show(message: string, level: ToastItem['level'] = 'info', duration = 4000) {
  const id = ++_nextId
  toasts.value.push({ id, message, level })
  if (duration > 0) {
    setTimeout(() => dismiss(id), duration)
  }
}

function dismiss(id: number) {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

export function useToast() {
  return {
    toasts: readonly(toasts),
    success: (msg: string) => show(msg, 'success'),
    warning: (msg: string) => show(msg, 'warning'),
    danger: (msg: string) => show(msg, 'danger'),
    info: (msg: string) => show(msg, 'info'),
    dismiss,
  }
}
