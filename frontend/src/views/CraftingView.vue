<script setup lang="ts">
import { computed } from 'vue'
import { Hammer } from 'lucide-vue-next'

import ProductionCard from '@/components/ProductionCard.vue'
import RecipeCard from '@/components/RecipeCard.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { qualityName } from '@/lib/quality'
import { fromCraftingStation } from '@/lib/production'
import { useGameStore } from '@/stores/game'
import type { CraftingStationState } from '@/types'

const game = useGameStore()

const stations = computed(() =>
  (game.state?.crafting_stations || []).map((station) => ({ station, node: fromCraftingStation(station) })),
)

function inputName(station: CraftingStationState, itemId: string) {
  return station.recipe?.inputs.find((input) => input.item_id === itemId)?.item.name || itemId
}
</script>

<template>
  <section v-if="game.state" class="view-section">
    <ViewHeader eyebrow="TOWN WORKSHOP" title="加工工坊">
      <template #chip><Hammer :size="18" /> 加工编制 {{ game.state.industry_rules.crafting?.partner_capacity || 0 }}</template>
    </ViewHeader>

    <StateBlock
      v-if="!stations.length"
      title="镇民工坊尚未开放"
      :description="`居民等级 ${game.state.next_crafting_station_level || 3} 解锁加工产业。`"
    />

    <div v-else class="station-list">
      <ProductionCard v-for="entry in stations" :key="entry.node.nodeId" :node="entry.node">
        <template #tasks="{ ability }">
          <div class="recipe-grid">
            <RecipeCard
              v-for="recipe in entry.station.recipes"
              :key="recipe.id"
              :recipe="recipe"
              :accent="entry.node.accent"
              :ability="ability"
              industry="crafting"
              :action-key="`crafting:${entry.node.nodeId}:start:${recipe.id}`"
              :group="`crafting:${entry.node.nodeId}:start`"
              @start="(taskItemId) => game.startProduction('crafting', entry.node.nodeId, recipe.id, taskItemId)"
            />
          </div>
        </template>

        <template #running>
          <div class="consumed-list">
            <small>已投入</small>
            <span
              v-for="input in entry.node.taskSnapshot?.consumed_inputs"
              :key="`${input.item_id}:${input.quality}`"
            >{{ qualityName(input.quality, '无品质') }}{{ inputName(entry.station, input.item_id) }} ×{{ input.quantity }}</span>
          </div>
        </template>
      </ProductionCard>
    </div>
  </section>
</template>

<style scoped>
.station-list { display: grid; gap: 18px; }
.recipe-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.consumed-list { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 12px; }
.consumed-list small { color: #7b867d; }
.consumed-list span { padding: 4px 7px; color: #a3aca4; font-size: 12px; border-radius: 5px; background: #ffffff05; }
@media (max-width: 720px) { .recipe-grid { grid-template-columns: 1fr; } }
</style>
