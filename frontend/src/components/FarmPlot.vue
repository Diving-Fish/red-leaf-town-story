<script setup lang="ts">
import { computed } from 'vue'
import { Clock3, LockKeyhole, Sparkles } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import CostChip from '@/components/CostChip.vue'
import GameIcon from '@/components/GameIcon.vue'
import PartnerPicker from '@/components/PartnerPicker.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import QualityTag from '@/components/QualityTag.vue'
import StateBlock from '@/components/StateBlock.vue'
import { useCountdown } from '@/composables/useCountdown'
import { usePartnerRoster } from '@/composables/usePartnerRoster'
import { formatDuration } from '@/lib/format'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { CropDefinition, PlotState } from '@/types'

const props = defineProps<{ plot?: PlotState; lockedLevel?: number | null; crops?: CropDefinition[] }>()

const game = useGameStore()
const ui = useUiStore()
const { ability } = usePartnerRoster('farming')

const { progress, label, elapsed } = useCountdown(
  () => props.plot?.ready_at,
  () => props.plot?.task_snapshot?.final_duration || props.plot?.crop?.growth_seconds,
)

const ready = computed(() => Boolean(props.plot?.crop) && (props.plot?.ready || elapsed.value))
const assignedPartner = computed(() => props.plot?.assigned_partners[0] || null)
const pickerId = computed(() => `plot:${props.plot?.slot}`)
const pickerOpen = computed(() => ui.openPickerId === pickerId.value)

function estimatedDuration(crop: CropDefinition) {
  const baseAbility = game.state?.industry_rules.farming?.character_base_ability || 0
  const total = baseAbility + ability(assignedPartner.value)
  const efficiency = 1 + (2 * total) / (total + crop.time_difficulty)
  return Math.max(1, Math.ceil(crop.growth_seconds / efficiency))
}

function selectPartner(partnerId: string | null) {
  if (!props.plot) return
  game.assignPartner(props.plot.slot, partnerId)
}
</script>

<template>
  <StateBlock
    v-if="!plot"
    variant="tile"
    :icon="LockKeyhole"
    title="待开垦土地"
    :description="`等级 ${lockedLevel || '?'} 解锁`"
  />

  <article v-else-if="plot.empty" class="farm-plot farm-plot--empty" :class="{ 'picker-open': pickerOpen }">
    <div class="soil-lines" aria-hidden="true"><i /><i /><i /></div>
    <div class="plot-heading"><span>土地 {{ plot.slot + 1 }}</span><small>空闲</small></div>

    <PartnerPicker
      :picker-id="pickerId"
      industry="farming"
      :action-key="`plot:${plot.slot}:partner`"
      :assigned="assignedPartner"
      placeholder="安排伙伴"
      placeholder-hint="可缩短生产时间"
      solo-label="不安排伙伴"
      solo-hint="撤下当前伙伴"
      empty-hint="仓库里还没有具有农作倾向的伙伴。"
      @select="selectPartner"
    />

    <div v-if="crops?.length" class="seed-actions">
      <ActionButton
        v-for="crop in crops"
        :key="crop.id"
        variant="bare"
        class="seed-button"
        :action-key="`plot:${plot.slot}:plant:${crop.id}`"
        :group="`plot:${plot.slot}:plant`"
        :disabled="game.liveStamina < crop.stamina_cost"
        :reason="game.liveStamina < crop.stamina_cost ? '体力不足' : undefined"
        @click="game.plant(plot.slot, crop.id)"
      >
        <GameIcon :name="crop.id === 'wheat' ? 'wheat' : 'carrot'" :size="18" />
        <span>种{{ crop.name }}</span>
        <small>
          <CostChip kind="stamina" :amount="crop.stamina_cost" :affordable="game.liveStamina >= crop.stamina_cost" signed />
          · {{ formatDuration(estimatedDuration(crop)) }}
        </small>
      </ActionButton>
    </div>
    <p v-else class="plot-hint">仓库里没有可用种子</p>
  </article>

  <article
    v-else
    class="farm-plot farm-plot--growing"
    :class="{ 'farm-plot--ready': ready, 'picker-open': pickerOpen }"
    :style="{ '--crop-accent': plot.crop?.accent }"
  >
    <div class="crop-orb">
      <Sparkles v-if="ready" class="ready-sparkle" :size="18" />
      <GameIcon :name="plot.crop_id === 'wheat' ? 'wheat' : 'carrot'" :size="42" />
    </div>
    <div class="plot-heading"><strong>{{ plot.crop?.name }}</strong><small>土地 {{ plot.slot + 1 }}</small></div>

    <PartnerPicker
      :picker-id="pickerId"
      industry="farming"
      :action-key="`plot:${plot.slot}:partner`"
      :assigned="assignedPartner"
      placeholder="没有驻场伙伴"
      placeholder-hint="任务未使用伙伴"
      solo-label="撤下伙伴"
      solo-hint="只影响下一次任务"
      :locked="plot.assignment_locked"
      locked-label="任务中 · 已锁定"
      empty-hint="仓库里还没有具有农作倾向的伙伴。"
      @select="selectPartner"
    />

    <span v-if="plot.task_snapshot && !ready" class="task-boost">
      能力 {{ plot.task_snapshot.total_ability }} · 品质 Q{{ plot.task_snapshot.quality_parameters.ability }} · 效率
      {{ plot.task_snapshot.time_efficiency.toFixed(2) }}×
    </span>

    <template v-if="ready">
      <p class="ready-label">
        <template v-if="plot.task_result">
          <QualityTag :quality="plot.task_result.quality" /> {{ plot.task_result.quantity }} 个
        </template>
        <template v-else>已经成熟</template>
      </p>
      <ActionButton class="harvest-button" :action-key="`plot:${plot.slot}:harvest`" @click="game.harvest(plot.slot)">
        收获
      </ActionButton>
    </template>
    <template v-else>
      <ProgressBar class="plot-progress" :value="progress" :color="plot.crop?.accent" track="#111713" smooth />
      <span class="time-left"><Clock3 :size="14" /> {{ label }}</span>
    </template>
  </article>
</template>

<style scoped>
.farm-plot.picker-open { z-index: 12; overflow: visible; }
.task-boost { color: #91aa7d; font-size: 12px; margin-bottom: 7px; }
.plot-progress { width: 100%; margin-top: auto; }
.seed-button small { display: flex; align-items: center; gap: 4px; color: #829081; font-size: 12px; }
</style>
