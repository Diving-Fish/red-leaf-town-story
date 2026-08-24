<script setup lang="ts">
import { computed } from 'vue'
import { Clock3 } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import ItemTile from '@/components/ItemTile.vue'
import PartnerPicker from '@/components/PartnerPicker.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import QualityTag from '@/components/QualityTag.vue'
import { useCountdown } from '@/composables/useCountdown'
import { industryMeta } from '@/lib/industries'
import { PRODUCTION_COPY, partnerAbility, type ProductionNode } from '@/lib/production'
import { useGameStore } from '@/stores/game'

const props = defineProps<{ node: ProductionNode }>()
const game = useGameStore()

const copy = computed(() => PRODUCTION_COPY[props.node.industry])
const meta = computed(() => industryMeta(props.node.industry))
const scope = computed(() => `${props.node.industry}:${props.node.nodeId}`)
const ability = computed(
  () =>
    (game.state?.industry_rules[props.node.industry]?.character_base_ability || 0)
    + partnerAbility(props.node.assignedPartner, props.node.industry),
)
const { progress, label } = useCountdown(
  () => props.node.taskSnapshot?.ready_at,
  () => props.node.taskSnapshot?.final_duration,
)
const activeItems = computed(() => (game.state?.task_items || []).filter((item) => (
  item.timing === 'active'
  && (!item.eligible_industries.length || item.eligible_industries.includes(props.node.industry))
)))
</script>

<template>
  <article class="surface-card industry-card" :class="{ ready: node.ready }" :style="{ '--industry-accent': node.accent }">
    <header class="industry-card-heading">
      <ItemTile :size="47" :accent="node.accent"><component :is="meta.icon" :size="25" /></ItemTile>
      <div><h2>{{ node.name }}</h2></div>
    </header>

    <PartnerPicker
      :industry="node.industry"
      :action-key="`${scope}:partner`"
      :assigned="node.assignedPartner"
      :placeholder="copy.soloLabel"
      :solo-label="copy.soloLabel"
      :locked="node.assignmentLocked"
      :locked-label="copy.lockedLabel"
      dialog-title="选择驻场伙伴"
      @select="(partnerId) => game.assignProductionPartner(node.industry, node.nodeId, partnerId)"
    />

    <template v-if="node.empty">
      <div class="production-tasks"><slot name="tasks" :ability="ability" /></div>
    </template>

    <div v-else-if="node.ready" class="production-status">
      <ItemTile :icon="node.activeItemIcon" :size="46" :accent="node.accent" />
      <div>
        <strong>{{ copy.readyTitle }}</strong>
        <div v-if="node.taskResults.length" class="result-list">
          <small v-for="result in node.taskResults" :key="`${result.item_id}:${result.quality}`">
            <QualityTag :quality="result.quality" /> {{ result.quantity }} 个{{ result.item?.name || node.activeItemName }}
          </small>
        </div>
      </div>
      <ActionButton
        :action-key="`${scope}:collect`"
        @click="game.collectProduction(node.industry, node.nodeId)"
      >{{ copy.collectLabel }}</ActionButton>
    </div>

    <div v-else class="production-running">
      <div class="production-status">
        <ItemTile :icon="node.activeItemIcon" :size="46" :accent="node.accent" />
        <div>
          <strong>{{ node.activeName }}</strong>
          <small>品质 Q{{ node.taskSnapshot?.quality_parameters.ability }} · 剩余 {{ label }}</small>
        </div>
        <Clock3 :size="17" />
      </div>
      <slot name="running" />
      <ActionButton
        v-for="item in activeItems"
        :key="item.id"
        variant="secondary"
        :action-key="`${scope}:item:${item.id}`"
        :disabled="(node.taskSnapshot?.ready_at || 0) - game.serverNow > item.value"
        reason="剩余时间还太长"
        @click="game.useActiveTaskItem(node.industry, node.nodeId, item.id)"
      >{{ item.name }} ×{{ item.quantity }}</ActionButton>
      <ProgressBar class="running-progress" :value="progress" :color="node.accent" smooth />
    </div>
  </article>
</template>

<style scoped>
.production-tasks { display: grid; gap: 8px; margin-top: 4px; }
.result-list { display: grid; gap: 3px; margin-top: 4px; }
.result-list small { color: #aab5aa; }
.running-progress { margin-top: 12px; }
</style>
