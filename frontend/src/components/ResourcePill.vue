<script setup lang="ts">
import { computed } from 'vue'
import { BatteryCharging, Coins } from 'lucide-vue-next'

import { formatClock } from '@/lib/format'
import { useGameStore } from '@/stores/game'

const props = defineProps<{ kind: 'coins' | 'stamina' }>()
const game = useGameStore()

const value = computed(() => {
  if (!game.player) return ''
  return props.kind === 'coins' ? String(game.player.coins) : `${game.liveStamina}/${game.player.stamina_cap}`
})
const hint = computed(() => (props.kind === 'stamina' && game.staminaNextIn ? formatClock(game.staminaNextIn) : ''))
const title = computed(() => (hint.value ? `距离下一点体力 ${hint.value}` : ''))
</script>

<template>
  <span class="resource-pill" :class="kind" :title="title || undefined">
    <component :is="kind === 'coins' ? Coins : BatteryCharging" :size="17" />
    <strong>{{ value }}</strong>
    <small v-if="hint" class="pill-hint">+1 {{ hint }}</small>
    <small v-else class="pill-label">{{ kind === 'coins' ? '金币' : '体力' }}</small>
  </span>
</template>

<style scoped>
.pill-hint { color: #93a08f; font-variant-numeric: tabular-nums; white-space: nowrap; }
</style>
