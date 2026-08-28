<script setup lang="ts">
import { computed } from 'vue'
import { BatteryCharging, Coins, Plus } from 'lucide-vue-next'

import { formatClock } from '@/lib/format'
import { useGameStore } from '@/stores/game'

const props = defineProps<{ kind: 'coins' | 'stamina' }>()
const emit = defineEmits<{ (event: 'supply'): void }>()
const game = useGameStore()

const value = computed(() => {
  if (!game.player) return ''
  return props.kind === 'coins' ? String(game.player.coins) : `${game.liveStamina}/${game.player.stamina_cap}`
})
const hint = computed(() => (props.kind === 'stamina' && game.staminaNextIn ? formatClock(game.staminaNextIn) : ''))
const title = computed(() => (hint.value ? `距离下一点体力 ${hint.value}` : ''))
const overflowing = computed(() => props.kind === 'stamina' && game.liveStamina > (game.player?.stamina_cap || 0))
</script>

<template>
  <span class="resource-pill" :class="[kind, { overflowing }]" :title="title || undefined">
    <component :is="kind === 'coins' ? Coins : BatteryCharging" :size="17" />
    <strong>{{ value }}</strong>
    <small v-if="hint" class="pill-hint">+1 {{ hint }}</small>
    <small v-else class="pill-label">{{ kind === 'coins' ? '金币' : '体力' }}</small>
    <button
      v-if="kind === 'stamina'"
      class="pill-supply"
      type="button"
      aria-label="补充体力"
      @click="emit('supply')"
    ><Plus :size="14" stroke-width="2.6" /></button>
  </span>
</template>

<style scoped>
.pill-hint { color: #93a08f; font-variant-numeric: tabular-nums; white-space: nowrap; }
.resource-pill.stamina { padding-right: 4px; }
.resource-pill.overflowing strong { color: var(--gold); }
.pill-supply {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  margin-left: 8px;
  padding: 0;
  color: var(--leaf-bright);
  border: 1px solid color-mix(in srgb, var(--leaf) 42%, transparent);
  border-radius: 8px 3px 8px 3px;
  background: rgba(119, 153, 91, .14);
  cursor: pointer;
  transition: background .16s ease, color .16s ease;
}
.pill-supply:hover { color: #16210f; background: var(--leaf-bright); }
.pill-supply:focus-visible { outline: 2px solid var(--leaf); outline-offset: 1px; }
</style>
