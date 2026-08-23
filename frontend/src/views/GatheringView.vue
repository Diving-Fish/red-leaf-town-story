<script setup lang="ts">
import { computed } from 'vue'
import { Lock, UsersRound } from 'lucide-vue-next'

import ProductionCard from '@/components/ProductionCard.vue'
import StateBlock from '@/components/StateBlock.vue'
import TaskButton from '@/components/TaskButton.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { fromGatheringSite } from '@/lib/production'
import { useGameStore } from '@/stores/game'

const game = useGameStore()

const sites = computed(() => (game.state?.gathering_sites || []).map((site) => ({ site, node: fromGatheringSite(site) })))
</script>

<template>
  <section v-if="game.state" class="view-section">
    <ViewHeader eyebrow="WOODLAND FORAGING" title="林野采集">
      <template #chip><UsersRound :size="18" /> 采集编制 {{ game.state.industry_rules.gathering?.partner_capacity || 0 }}</template>
    </ViewHeader>

    <div class="industry-grid">
      <ProductionCard v-for="entry in sites" :key="entry.node.nodeId" :node="entry.node">
        <template #tasks="{ ability }">
          <TaskButton
            v-for="task in entry.site.available_tasks"
            :key="task.id"
            :task="task"
            :accent="entry.node.accent"
            :ability="ability"
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
