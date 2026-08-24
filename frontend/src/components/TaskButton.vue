<script setup lang="ts">
import { computed, ref } from 'vue'

import ActionButton from '@/components/ActionButton.vue'
import CostChip from '@/components/CostChip.vue'
import ItemTile from '@/components/ItemTile.vue'
import TaskItemSelect from '@/components/TaskItemSelect.vue'
import { formatDuration } from '@/lib/format'
import { estimateDrawCount, estimateDuration } from '@/lib/production'
import { useGameStore } from '@/stores/game'
import type { GatheringTaskDefinition, MiningTaskDefinition } from '@/types'

const props = defineProps<{
  task: GatheringTaskDefinition | MiningTaskDefinition
  actionKey: string
  group?: string
  accent?: string
  disabled?: boolean
  reason?: string
  ability?: number
  industry: string
}>()

const emit = defineEmits<{ (event: 'start', taskItemId: string): void }>()
const game = useGameStore()
const taskItemId = ref('')

const affordable = computed(() => game.liveStamina >= props.task.stamina_cost)
const blocked = computed(() => Boolean(props.disabled) || !affordable.value)
const reasonText = computed(() => props.reason || (affordable.value ? undefined : '体力不足'))
const gatheringTask = computed(() => ('outputs' in props.task ? props.task : null))
const singleOutputTask = computed<MiningTaskDefinition | null>(() => (
  'yield_min' in props.task ? props.task as MiningTaskDefinition : null
))
const drawCount = computed(() => estimateDrawCount(gatheringTask.value?.draws, props.ability || 0))
const poolWeight = computed(() => (gatheringTask.value?.outputs || []).reduce((total, entry) => total + entry.weight, 0))
const duration = computed(() => 'yield_difficulty' in props.task
  ? props.task.duration_seconds
  : estimateDuration(
      props.task.duration_seconds,
      props.task.time_difficulty,
      props.ability || 0,
      'minimum_duration_seconds' in props.task ? props.task.minimum_duration_seconds : 1,
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
    @click="emit('start', taskItemId)"
  >
    <ItemTile :icon="task.item.icon" :size="42" :accent="accent" />
    <span class="task-copy">
      <strong>{{ task.name }}</strong>
      <small v-if="gatheringTask">
        抽取 {{ drawCount }} 次 · {{ gatheringTask.outputs.length }} 种材料 · 约 {{ formatDuration(duration) }}
      </small>
      <span v-if="gatheringTask" class="loot-preview">
        <i v-for="output in gatheringTask.outputs" :key="output.item_id">
          {{ output.item.name }} {{ Math.round((output.weight / poolWeight) * 100) }}%
        </i>
      </span>
      <small v-else-if="singleOutputTask">
        {{ singleOutputTask.yield_min }}—{{ singleOutputTask.yield_max }} 个 · 约 {{ formatDuration(duration) }}
      </small>
      <TaskItemSelect v-model="taskItemId" :industry="industry" />
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
