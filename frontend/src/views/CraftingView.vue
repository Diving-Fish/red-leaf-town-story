<script setup lang="ts">
import { computed } from 'vue'
import { Hammer } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import { formatDuration } from '@/lib/format'
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
              @start="(taskItemId, quantity) => game.startProduction('crafting', entry.node.nodeId, recipe.id, taskItemId, quantity)"
            />
          </div>
        </template>

        <template #running>
          <div class="queue-status">
            <span>正在加工第 {{ entry.station.collected_count + entry.station.completed_count + 1 }} / {{ entry.station.queue_total || 1 }} 次</span>
            <small>待加工 {{ entry.station.queued_count || 0 }} 次 · 队列剩余约 {{ formatDuration(entry.station.queue_remaining_seconds) }}</small>
            <ActionButton
              v-if="entry.station.completed_count"
              :action-key="`crafting:${entry.node.nodeId}:collect`"
              @click="game.collectProduction('crafting', entry.node.nodeId)"
            >领取已完成的 {{ entry.station.completed_count }} 次产物</ActionButton>
          </div>
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
.queue-status { display: grid; gap: 8px; font-size: 13px; }
.queue-status small { color: #a3aca4; }
.station-list { display: grid; gap: 18px; }
.recipe-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
.consumed-list { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.consumed-list small { color: #7b867d; }
.consumed-list span { padding: 4px 7px; color: #a3aca4; font-size: 12px; border-radius: 5px; background: #ffffff05; }
@media (max-width: 720px) { .recipe-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
