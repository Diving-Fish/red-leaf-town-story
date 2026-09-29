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
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ node: ProductionNode }>()
const game = useGameStore()
const ui = useUiStore()

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

async function cancelTask() {
  const accepted = await ui.confirm({
    title: copy.value.cancelConfirmTitle,
    description: copy.value.cancelConfirmDescription,
    confirmLabel: copy.value.cancelLabel,
    tone: 'danger',
  })
  if (accepted) game.cancelTask(props.node.industry, props.node.nodeId)
}
</script>

<template>
  <article class="surface-card industry-card" :class="{ ready: node.ready }" :style="{ '--industry-accent': node.accent }">
    <header class="industry-card-heading">
      <ItemTile :size="47" :accent="node.accent"><component :is="meta.icon" :size="25" /></ItemTile>
      <div class="industry-card-title">
        <h2>{{ node.name }}</h2>
        <span v-if="node.eventClosed" class="card-badge">活动已关闭</span>
        <span v-else-if="node.eventBadge" class="card-badge">{{ node.eventBadge }}</span>
      </div>
    </header>

    <!-- 活动采集点的收益说明：文案由后端 event_note 提供，只在有内容时显示（蓝色与探索路线的领队备注一致） -->
    <p v-if="node.eventNote" class="card-note">{{ node.eventNote }}</p>

    <p v-if="node.eventClosed" class="card-note">可完成并领取已有任务，或撤回驻场伙伴。</p>

    <PartnerPicker
      :candidates="node.eventClosed ? [] : undefined"
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
      <ActionButton
        variant="secondary"
        :action-key="`${scope}:cancel`"
        @click="cancelTask"
      >{{ copy.cancelLabel }}</ActionButton>
      <ProgressBar class="running-progress" :value="progress" :color="node.accent" smooth />
    </div>
  </article>
</template>

<style scoped>
.production-tasks { display: grid; gap: 8px; margin-top: 4px; }
.result-list { display: grid; gap: 3px; margin-top: 4px; }
.result-list small { color: #aab5aa; }
.production-running { display: flex; flex-direction: column; gap: 12px; }
.industry-card-title { display: flex; align-items: center; gap: 8px; }
.card-badge { flex-shrink: 0; padding: 2px 9px; border-radius: 99px; background: color-mix(in srgb, var(--industry-accent) 24%, transparent); color: var(--industry-accent); font-size: 12px; }
.card-note { margin: 6px 0 12px; color: #8ab4f8; font-size: 13px; font-weight: 600; letter-spacing: 0.02em; line-height: 1.55; }
</style>
