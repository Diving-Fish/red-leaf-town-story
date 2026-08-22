<script setup lang="ts">
import { computed } from 'vue'
import { Compass, Lock, UsersRound } from 'lucide-vue-next'

import ProductionCard from '@/components/ProductionCard.vue'
import StateBlock from '@/components/StateBlock.vue'
import TaskButton from '@/components/TaskButton.vue'
import TipCard from '@/components/TipCard.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { usePartnerRoster } from '@/composables/usePartnerRoster'
import { fromGatheringSite } from '@/lib/production'
import { useGameStore } from '@/stores/game'

const game = useGameStore()
const { partners } = usePartnerRoster('gathering')

const sites = computed(() => (game.state?.gathering_sites || []).map((site) => ({ site, node: fromGatheringSite(site) })))
</script>

<template>
  <section v-if="game.state" class="view-section">
    <ViewHeader
      eyebrow="WOODLAND FORAGING"
      title="林野采集"
      description="玩家无法亲自完成采集。派遣具有采集倾向的伙伴，让他们从镇外带回带品质的素材。"
    >
      <template #chip><UsersRound :size="18" /> 采集编制 {{ game.state.industry_rules.gathering?.partner_capacity || 0 }}</template>
    </ViewHeader>

    <TipCard
      v-if="!partners.length"
      :icon="Compass"
      text="伙伴仓库中还没有具有采集倾向的伙伴，因此暂时无法开始采集。"
      to="/partners"
      action-label="查看伙伴"
    />

    <div class="industry-grid">
      <ProductionCard v-for="entry in sites" :key="entry.node.nodeId" :node="entry.node">
        <template #tasks>
          <TaskButton
            v-for="task in entry.site.available_tasks"
            :key="task.id"
            :task="task"
            :accent="entry.node.accent"
            :action-key="`gathering:${entry.node.nodeId}:start:${task.id}`"
            :group="`gathering:${entry.node.nodeId}:start`"
            :disabled="!entry.node.assignedPartnerId"
            :reason="entry.node.assignedPartnerId ? undefined : '必须先派一名采集伙伴前往'"
            @start="game.startProduction('gathering', entry.node.nodeId, task.id)"
          />
        </template>
      </ProductionCard>

      <StateBlock
        v-if="game.state.next_gathering_site_level"
        variant="card"
        :icon="Lock"
        title="新的采集区域"
        :description="`等级 ${game.state.next_gathering_site_level} 解锁`"
      />
    </div>
  </section>
</template>
