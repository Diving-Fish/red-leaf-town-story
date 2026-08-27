import { ref } from 'vue'
import { defineStore } from 'pinia'

export interface ConfirmOptions {
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'default' | 'danger'
}

export const useUiStore = defineStore('ui', () => {
  const navOpen = ref(false)
  const accountOpen = ref(false)
  const mailOpen = ref(false)
  const achievementOpen = ref(false)
  const confirmRequest = ref<ConfirmOptions | null>(null)
  let resolveConfirm: ((accepted: boolean) => void) | null = null

  function confirm(options: ConfirmOptions) {
    resolveConfirm?.(false)
    confirmRequest.value = options
    return new Promise<boolean>((resolve) => {
      resolveConfirm = resolve
    })
  }

  function settleConfirm(accepted: boolean) {
    confirmRequest.value = null
    resolveConfirm?.(accepted)
    resolveConfirm = null
  }

  return { navOpen, accountOpen, mailOpen, achievementOpen, confirmRequest, confirm, settleConfirm }
})
