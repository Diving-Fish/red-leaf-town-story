import { watch } from 'vue'

import { useGameStore } from '@/stores/game'

export function useReadyWatch() {
  const game = useGameStore()
  let refreshedFor = 0

  watch(
    () => [game.serverNow, game.nextReadyAt] as const,
    ([now, target]) => {
      if (!target || target === refreshedFor) return
      if (now < target + 1) return
      refreshedFor = target
      game.refresh(true)
    },
  )
}
