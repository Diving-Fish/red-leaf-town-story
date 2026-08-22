import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { formatDuration } from '@/lib/format'
import { useGameStore } from '@/stores/game'

export function useCountdown(
  readyAt: MaybeRefOrGetter<number | null | undefined>,
  duration: MaybeRefOrGetter<number | null | undefined>,
) {
  const game = useGameStore()

  const remaining = computed(() => {
    const target = toValue(readyAt)
    if (!target) return 0
    return Math.max(0, target - game.serverNow)
  })

  const progress = computed(() => {
    const span = toValue(duration)
    if (!span) return 0
    return Math.min(100, Math.max(3, 100 - (remaining.value / span) * 100))
  })

  const label = computed(() => formatDuration(remaining.value))
  const elapsed = computed(() => Boolean(toValue(readyAt)) && remaining.value <= 0)

  return { remaining, progress, label, elapsed }
}
