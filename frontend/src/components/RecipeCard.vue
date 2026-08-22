<script setup lang="ts">
import { computed } from 'vue'
import { Lock } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import CostChip from '@/components/CostChip.vue'
import GameIcon from '@/components/GameIcon.vue'
import ItemTile from '@/components/ItemTile.vue'
import { formatDuration } from '@/lib/format'
import { useGameStore } from '@/stores/game'
import type { RecipeState } from '@/types'

const props = defineProps<{ recipe: RecipeState; actionKey: string; group?: string; accent?: string }>()
const emit = defineEmits<{ (event: 'start'): void }>()
const game = useGameStore()

const affordable = computed(() => game.liveStamina >= props.recipe.stamina_cost)
const label = computed(() => {
  if (!props.recipe.unlocked) return '配方未解锁'
  if (!props.recipe.ingredients_available) return '原料不足'
  if (!affordable.value) return '体力不足'
  return '开始加工'
})
const reason = computed(() =>
  props.recipe.unlocked
    ? props.recipe.inputs.map((input) => `${input.item.name} ${input.owned_quantity}/${input.quantity}`).join(' · ')
    : props.recipe.unlock_description,
)
</script>

<template>
  <article class="recipe-card" :class="{ locked: !recipe.unlocked }">
    <div class="recipe-output">
      <ItemTile :icon="recipe.item.icon" :size="40" :accent="accent" />
      <div><h3>{{ recipe.name }}</h3><small>产出 {{ recipe.produce_quantity }} 个{{ recipe.item.name }}</small></div>
      <Lock v-if="!recipe.unlocked" :size="15" />
    </div>
    <div class="recipe-inputs">
      <span
        v-for="input in recipe.inputs"
        :key="input.item_id"
        :class="{ missing: input.owned_quantity < input.quantity }"
      >
        <GameIcon :name="input.item.icon" :size="14" />{{ input.item.name }} {{ input.owned_quantity }}/{{ input.quantity }}
      </span>
    </div>
    <p v-if="!recipe.unlocked" class="unlock-copy">{{ recipe.unlock_description }}</p>
    <p v-else class="recipe-meta">
      {{ formatDuration(recipe.duration_seconds) }} · 品质加工
      <CostChip kind="stamina" :amount="recipe.stamina_cost" :affordable="affordable" signed />
    </p>
    <ActionButton
      variant="secondary"
      :action-key="actionKey"
      :group="group"
      :disabled="!recipe.unlocked || !recipe.ingredients_available || !affordable"
      :reason="reason"
      @click="emit('start')"
    >{{ label }}</ActionButton>
  </article>
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
.recipe-card .unlock-copy { color: #ae9163; }
.recipe-card :deep(button) { width: 100%; }
</style>
