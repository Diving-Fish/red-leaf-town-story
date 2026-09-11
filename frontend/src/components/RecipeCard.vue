<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Lock } from 'lucide-vue-next'

import ModalSheet from '@/components/ModalSheet.vue'
import QuantityStepper from '@/components/QuantityStepper.vue'
import ActionButton from '@/components/ActionButton.vue'
import CostChip from '@/components/CostChip.vue'
import GameIcon from '@/components/GameIcon.vue'
import ItemTile from '@/components/ItemTile.vue'
import TaskItemSelect from '@/components/TaskItemSelect.vue'
import { formatDuration } from '@/lib/format'
import { estimateDuration, taskItemDurationMultiplier } from '@/lib/production'
import { useGameStore } from '@/stores/game'
import type { RecipeState } from '@/types'

const props = defineProps<{ recipe: RecipeState; actionKey: string; group?: string; accent?: string; ability?: number; industry: string }>()
const emit = defineEmits<{ (event: 'start', taskItemId: string, quantity: number): void }>()
const game = useGameStore()
const taskItemId = ref('')
const open = ref(false)
const quantity = ref(1)
const maxQuantity = computed(() => Math.max(1, Math.min(99,
  props.recipe.stamina_cost ? Math.floor(game.liveStamina / props.recipe.stamina_cost) : 99,
  ...props.recipe.inputs.map(input => Math.floor(input.owned_quantity / input.quantity)),
)))
watch(maxQuantity, max => { quantity.value = Math.min(quantity.value, max) })
const ingredientsAvailable = computed(() => props.recipe.inputs.every(input => input.owned_quantity >= input.quantity * quantity.value))
function showDetails() {
  quantity.value = 1
  taskItemId.value = ''
  open.value = true
}

const affordable = computed(() => game.liveStamina >= props.recipe.stamina_cost * quantity.value)
const selectedTaskItem = computed(() => game.state?.task_items.find(item => item.id === taskItemId.value))
const taskItemCount = computed(() => Math.min(quantity.value, selectedTaskItem.value?.quantity || 0))
const duration = computed(() => {
  const singleDuration = (multiplier: number) => estimateDuration(
    props.recipe.duration_seconds, props.recipe.time_difficulty, props.ability || 0, 1, multiplier,
  )
  return singleDuration(taskItemDurationMultiplier(game.state?.task_items, taskItemId.value)) * taskItemCount.value
    + singleDuration(1) * (quantity.value - taskItemCount.value)
})
const label = computed(() => {
  if (!props.recipe.unlocked) return '配方未解锁'
  if (!ingredientsAvailable.value) return '原料不足'
  if (!affordable.value) return '体力不足'
  return '开始加工'
})
const reason = computed(() =>
  props.recipe.unlocked
    ? props.recipe.inputs.map((input) => `${input.item.name} ${input.owned_quantity}/${input.quantity * quantity.value}`).join(' · ')
    : props.recipe.unlock_description,
)
</script>

<template>
  <button class="recipe-trigger" :class="{ locked: !recipe.unlocked }" @click="showDetails">
    <ItemTile :icon="recipe.item.icon" :size="32" :accent="accent" />
    <span class="recipe-name">{{ recipe.item.name }}</span>
    <Lock v-if="!recipe.unlocked" :size="12" aria-label="未解锁" />
  </button>
  <ModalSheet :open="open" :title="recipe.item.name" subtitle="预留整批材料和体力，按队列逐次加工，完成一份即可领取。" @close="open = false">
  <article class="recipe-card" :class="{ locked: !recipe.unlocked }">
    <div class="recipe-output">
      <ItemTile :icon="recipe.item.icon" :size="40" :accent="accent" />
      <div><h3>{{ recipe.name }}</h3><small>基础产出 {{ recipe.produce_quantity * quantity }} 个{{ recipe.item.name }}</small></div>
      <Lock v-if="!recipe.unlocked" :size="15" />
    </div>
    <div class="recipe-inputs">
      <span
        v-for="input in recipe.inputs"
        :key="input.item_id"
        :class="{ missing: input.owned_quantity < input.quantity * quantity }"
      >
        <GameIcon :name="input.item.icon" :size="14" />{{ input.item.name }} {{ input.owned_quantity }}/{{ input.quantity * quantity }}
      </span>
    </div>
    <p v-if="!recipe.unlocked" class="unlock-copy">{{ recipe.unlock_description }}</p>
    <p v-else class="recipe-meta">
      约 {{ formatDuration(duration) }}
      <CostChip kind="stamina" :amount="recipe.stamina_cost * quantity" :affordable="affordable" signed />
    </p>
    <div v-if="recipe.unlocked" class="batch-picker">
      <span>加工次数</span>
      <QuantityStepper v-model="quantity" :max="maxQuantity" />
      <button class="text-button" @click="quantity = maxQuantity">最多 {{ maxQuantity }} 次</button>
    </div>
    <TaskItemSelect v-model="taskItemId" :industry="industry" elevated />
    <p v-if="taskItemId" class="task-item-hint" :class="{ shortage: taskItemCount < quantity }">
      每次加工消耗 1 件特殊道具，本次预留 {{ taskItemCount }} 件。
      <template v-if="taskItemCount < quantity">道具不足：仅前 {{ taskItemCount }} 次生效，后 {{ quantity - taskItemCount }} 次不使用道具。</template>
      <template v-else>全部 {{ quantity }} 次加工均使用道具。</template>
    </p>
    <p class="queue-hint">取消时退回未开始部分的材料、体力和道具；当前加工投入不退，已完成产物保留。</p>
  </article>
  <template #footer>
    <div class="recipe-footer">
    <ActionButton
      variant="secondary"
      :action-key="actionKey"
      :group="group"
      :disabled="!recipe.unlocked || !ingredientsAvailable || !affordable"
      :reason="reason"
      @click="emit('start', taskItemId, quantity)"
    >{{ label }}</ActionButton>
    </div>
  </template>
  </ModalSheet>
</template>

<style scoped>
.recipe-card { padding: 13px; border-radius: 13px; background: #0c130f99; }
.recipe-card.locked { opacity: .58; }
.recipe-output { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 9px; }
.recipe-output h3 { margin: 0; font-size: 14px; }
.recipe-output small { color: #78827a; }
.recipe-inputs { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 11px; }
.recipe-inputs span { display: flex; align-items: center; gap: 4px; padding: 5px 7px; color: #9eaa9f; border-radius: 6px; background: #ffffff05; }
.recipe-inputs span.missing { color: var(--danger); }
.recipe-meta { display: flex; align-items: center; gap: 7px; }
.recipe-card > p { min-height: 16px; margin: 9px 0; color: #7c877e; font-size: 12px; }
.recipe-card .task-item-hint, .recipe-card .queue-hint { line-height: 1.6; }
.recipe-card .shortage { color: var(--gold); }
.recipe-card .unlock-copy { color: #ae9163; }
.recipe-trigger { display: flex; align-items: center; gap: 8px; padding: 9px; border: 1px solid var(--line); border-radius: 10px; background: #0c130f99; color: inherit; text-align: left; cursor: pointer; }
.recipe-trigger:hover { border-color: var(--gold); }
.recipe-trigger .recipe-name { flex: 1; min-width: 0; font-size: 13px; }
.recipe-footer { display: flex; justify-content: flex-end; }
.recipe-trigger.locked { opacity: .58; }
.batch-picker { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 16px 0; font-size: 13px; }
</style>
