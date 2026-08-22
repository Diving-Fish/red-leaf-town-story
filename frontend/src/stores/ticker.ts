import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useTickerStore = defineStore('ticker', () => {
  const now = ref(Date.now())
  let timer = 0

  if (typeof window !== 'undefined') {
    timer = window.setInterval(() => (now.value = Date.now()), 1000)
    window.addEventListener('visibilitychange', () => {
      if (!document.hidden) now.value = Date.now()
    })
  }

  function stop() {
    window.clearInterval(timer)
    timer = 0
  }

  return { now, stop }
})
