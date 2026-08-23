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
const gatheringTask = computed(() => ('outputs' in props.task ? props.task : null))
const singleOutputTask = computed<MiningTaskDefinition | null>(() => (
  'yield_min' in props.task ? props.task as MiningTaskDefinition : null
))
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
      <small v-if="gatheringTask">
        {{ gatheringTask.outputs.length }} 种可能材料 · {{ formatDuration(gatheringTask.duration_seconds) }} · 最短
        {{ formatDuration(gatheringTask.minimum_duration_seconds) }}
      </small>
      <span v-if="gatheringTask" class="loot-preview">
        <i v-for="output in gatheringTask.outputs" :key="output.item_id">
          {{ output.item.name }} {{ Math.round(output.chance * 100) }}%
        </i>
      </span>
      <small v-else-if="singleOutputTask">
        {{ singleOutputTask.yield_min }}—{{ singleOutputTask.yield_max }} 个 · {{ formatDuration(singleOutputTask.duration_seconds) }}
      </small>
    </span>
    <CostChip v-if="task.stamina_cost" kind="stamina" :amount="task.stamina_cost" :affordable="affordable" signed />
    <span v-else class="free-cost">无需体力</span>
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
.loot-preview { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.loot-preview i { padding: 2px 5px; color: #96a497; font-size: 10px; font-style: normal; border-radius: 5px; background: #ffffff08; }
.free-cost { color: var(--leaf-bright); font-size: 12px; white-space: nowrap; }
</style>
