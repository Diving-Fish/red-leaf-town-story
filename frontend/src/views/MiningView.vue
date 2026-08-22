<script setup lang="ts">
import { computed } from 'vue'
import { Gem, Lock, Pickaxe } from 'lucide-vue-next'

import ProductionCard from '@/components/ProductionCard.vue'
import StateBlock from '@/components/StateBlock.vue'
import TaskButton from '@/components/TaskButton.vue'
import TipCard from '@/components/TipCard.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { fromMiningSite } from '@/lib/production'
import { useGameStore } from '@/stores/game'

const game = useGameStore()

const sites = computed(() => (game.state?.mining_sites || []).map((site) => ({ site, node: fromMiningSite(site) })))
</script>

<template>
  <section v-if="game.state" class="view-section">
    <ViewHeader
      eyebrow="MOUNTAIN MINING"
      title="山地矿产"
      description="前往矿脉开采带品质的矿石。玩家可以独自采矿，也可以邀请具有矿产倾向的伙伴协助。"
    >
      <template #chip><Pickaxe :size="18" /> 矿产编制 {{ game.state.industry_rules.mining?.partner_capacity || 0 }}</template>
    </ViewHeader>

    <TipCard :icon="Gem" text="协助伙伴会缩短开采时间并提高品质能力；任务开始后，该伙伴会锁定到结算完成。" />

    <StateBlock
      v-if="!sites.length"
      title="通往矿山的道路尚未开放"
      :description="`居民等级 ${game.state.next_mining_site_level || 2} 解锁矿产产业。`"
    />

    <div v-else class="industry-grid">
      <ProductionCard v-for="entry in sites" :key="entry.node.nodeId" :node="entry.node">
        <template #tasks>
          <TaskButton
            v-for="task in entry.site.available_tasks"
            :key="task.id"
            :task="task"
            :accent="entry.node.accent"
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
