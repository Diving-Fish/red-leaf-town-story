<script setup lang="ts">
import { computed } from 'vue'

import ActionButton from '@/components/ActionButton.vue'
import CostChip from '@/components/CostChip.vue'
import ItemTile from '@/components/ItemTile.vue'
import { formatDuration } from '@/lib/format'
import { useGameStore } from '@/stores/game'
import type { GatheringTaskDefinition, MiningTaskDefinition } from '@/types'

const props = defineProps<{
  task: GatheringTaskDefinition | MiningTaskDefinition
  actionKey: string
  group?: string
  accent?: string
  disabled?: boolean
  reason?: string
}>()

const emit = defineEmits<{ (event: 'start'): void }>()
const game = useGameStore()

const affordable = computed(() => game.liveStamina >= props.task.stamina_cost)
const blocked = computed(() => Boolean(props.disabled) || !affordable.value)
const reasonText = computed(() => props.reason || (affordable.value ? undefined : '体力不足'))
</script>

<template>
  <ActionButton
    variant="bare"
    class="task-button"
    :action-key="actionKey"
    :group="group"
    :disabled="blocked"
    :reason="reasonText"
    @click="emit('start')"
  >
    <ItemTile :icon="task.item.icon" :size="42" :accent="accent" />
    <span class="task-copy">
      <strong>{{ task.name }}</strong>
      <small>{{ task.yield_min }}—{{ task.yield_max }} 个 · {{ formatDuration(task.duration_seconds) }}</small>
    </span>
    <CostChip kind="stamina" :amount="task.stamina_cost" :affordable="affordable" signed />
  </ActionButton>
</template>

<style scoped>
.task-button {
  width: 100%;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 11px;
  text-align: left;
  color: #d2dad0;
  border: 1px solid #ffffff10;
  border-radius: 11px;
  background: #0c130f;
  cursor: pointer;
}
.task-button:disabled { opacity: .5; cursor: default; }
.task-copy { min-width: 0; }
.task-copy strong, .task-copy small { display: block; }
.task-copy small { margin-top: 4px; color: #808a82; }
</style>
