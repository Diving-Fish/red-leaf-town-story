<script setup lang="ts">
import { computed } from 'vue'
import { Lock, Pickaxe } from 'lucide-vue-next'

import ProductionCard from '@/components/ProductionCard.vue'
import StateBlock from '@/components/StateBlock.vue'
import TaskButton from '@/components/TaskButton.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { fromMiningSite } from '@/lib/production'
import { useGameStore } from '@/stores/game'

const game = useGameStore()

const sites = computed(() => (game.state?.mining_sites || []).map((site) => ({ site, node: fromMiningSite(site) })))
</script>

<template>
  <section v-if="game.state" class="view-section">
    <ViewHeader eyebrow="MOUNTAIN MINING" title="山地矿产">
      <template #chip><Pickaxe :size="18" /> 矿产编制 {{ game.state.industry_rules.mining?.partner_capacity || 0 }}</template>
    </ViewHeader>

    <StateBlock
      v-if="!sites.length"
      title="通往矿山的道路尚未开放"
      :description="`居民等级 ${game.state.next_mining_site_level || 2} 解锁矿产产业。`"
    />

    <div v-else class="industry-grid">
      <ProductionCard v-for="entry in sites" :key="entry.node.nodeId" :node="entry.node">
        <template #tasks="{ ability }">
          <TaskButton
            v-for="task in entry.site.available_tasks"
            :key="task.id"
            :task="task"
            :accent="entry.node.accent"
            :ability="ability"
            :action-key="`mining:${entry.node.nodeId}:start:${task.id}`"
            :group="`mining:${entry.node.nodeId}:start`"
            @start="game.startProduction('mining', entry.node.nodeId, task.id)"
          />
        </template>
      </ProductionCard>

      <StateBlock
        v-if="game.state.next_mining_site_level"
        variant="card"
        :icon="Lock"
        title="更深的矿脉"
        :description="`等级 ${game.state.next_mining_site_level} 解锁`"
      />
    </div>
  </section>
</template>
