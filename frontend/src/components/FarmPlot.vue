<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ChevronDown, Clock3, Lock, LockKeyhole, Sparkles, UserRound } from 'lucide-vue-next'

import CroppedImage from '@/components/CroppedImage.vue'
import GameIcon from '@/components/GameIcon.vue'
import { useGameStore } from '@/stores/game'
import type { CropDefinition, OwnedPartner, PlotState } from '@/types'

const props = defineProps<{
  plot?: PlotState
  lockedLevel?: number | null
  crops?: CropDefinition[]
  partners?: OwnedPartner[]
}>()

const game = useGameStore()
const tick = ref(Date.now())
const pickerOpen = ref(false)
let timer = 0

onMounted(() => {
  timer = window.setInterval(() => (tick.value = Date.now()), 1000)
})
onBeforeUnmount(() => window.clearInterval(timer))

const remaining = computed(() => {
  tick.value
  if (!props.plot?.ready_at) return 0
  return Math.max(0, props.plot.ready_at - game.effectiveNow())
})
const ready = computed(() => Boolean(props.plot?.crop && remaining.value <= 0))
const qualityNames = ['', '普通', '良品', '上品', '臻品', '奇迹']
const assignedPartner = computed(() => props.plot?.assigned_partners[0] || null)
const farmingPartners = computed(() => (props.partners || []).filter(
  (partner) => !partner.missing && partner.tendencies?.some((tendency) => tendency.industry === 'farming'),
))
const progress = computed(() => {
  if (!props.plot?.crop) return 0
  const duration = props.plot.task_snapshot?.final_duration || props.plot.crop.growth_seconds
  return Math.min(100, Math.max(3, 100 - (remaining.value / duration) * 100))
})
const timeLabel = computed(() => {
  const minutes = Math.floor(remaining.value / 60)
  const seconds = remaining.value % 60
  return minutes ? `${minutes}分 ${seconds}秒` : `${seconds}秒`
})

function farmingAbility(partner: OwnedPartner | null) {
  const tendency = partner?.tendencies?.find((entry) => entry.industry === 'farming')
  return tendency?.effective_ability ?? tendency?.current_ability ?? 0
}

function estimatedDuration(crop: CropDefinition) {
  const baseAbility = game.state?.industry_rules.farming?.character_base_ability || 0
  const ability = baseAbility + farmingAbility(assignedPartner.value)
  const efficiency = 1 + 2 * ability / (ability + crop.time_difficulty)
  return Math.max(1, Math.ceil(crop.growth_seconds / efficiency))
}

function durationLabel(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return minutes ? `${minutes}分${rest ? `${rest}秒` : ''}` : `${rest}秒`
}

async function choosePartner(partnerId: string | null) {
  if (!props.plot) return
  await game.assignPartner(props.plot.slot, partnerId)
  pickerOpen.value = false
}
</script>

<template>
  <article v-if="!plot" class="farm-plot farm-plot--locked">
    <LockKeyhole :size="28" />
    <strong>待开垦土地</strong>
    <span>等级 {{ lockedLevel || '?' }} 解锁</span>
  </article>

  <article v-else-if="plot.empty" class="farm-plot farm-plot--empty" :class="{ 'picker-open': pickerOpen }">
    <div class="soil-lines" aria-hidden="true"><i /><i /><i /></div>
    <div class="plot-heading">
      <span>土地 {{ plot.slot + 1 }}</span>
      <small>空闲</small>
    </div>
    <button class="partner-slot" :class="{ assigned: assignedPartner }" :disabled="game.busy" @click="pickerOpen = !pickerOpen">
      <span class="partner-slot-avatar">
        <CroppedImage v-if="assignedPartner?.artwork?.url && assignedPartner.avatar_crop" :image-url="assignedPartner.artwork.url" :image-width="assignedPartner.artwork.width" :image-height="assignedPartner.artwork.height" :crop="assignedPartner.avatar_crop" :alt="`${assignedPartner.name}头像`" />
        <UserRound v-else :size="16" />
      </span>
      <span><strong>{{ assignedPartner?.name || '安排伙伴' }}</strong><small>{{ assignedPartner ? `农作能力 ${farmingAbility(assignedPartner)}` : '可缩短生产时间' }}</small></span>
      <ChevronDown :size="14" />
    </button>
    <div v-if="pickerOpen" class="partner-picker">
      <button v-if="assignedPartner" @click="choosePartner(null)"><span class="picker-empty"><UserRound :size="15" /></span><span><strong>不安排伙伴</strong><small>撤下当前伙伴</small></span></button>
      <button v-for="partner in farmingPartners" :key="partner.partner_id" :disabled="partner.locked && partner.partner_id !== assignedPartner?.partner_id" @click="choosePartner(partner.partner_id)">
        <span class="picker-avatar"><CroppedImage v-if="partner.artwork?.url && partner.avatar_crop" :image-url="partner.artwork.url" :image-width="partner.artwork.width" :image-height="partner.artwork.height" :crop="partner.avatar_crop" :alt="`${partner.name}头像`" /><UserRound v-else :size="15" /></span>
        <span><strong>{{ partner.name }}</strong><small>农作 {{ farmingAbility(partner) }}{{ partner.assigned_plot_slot !== null ? ` · 土地 ${partner.assigned_plot_slot + 1}` : '' }}</small></span>
        <Lock v-if="partner.locked" :size="12" />
      </button>
      <p v-if="!farmingPartners.length">仓库里还没有具有农作倾向的伙伴。</p>
    </div>
    <div class="seed-actions" v-if="crops?.length">
      <button
        v-for="crop in crops"
        :key="crop.id"
        class="seed-button"
        :disabled="game.busy"
        @click="game.plant(plot.slot, crop.id)"
      >
        <GameIcon :name="crop.id === 'wheat' ? 'wheat' : 'carrot'" :size="18" />
        <span>种{{ crop.name }}</span>
        <small>-{{ crop.stamina_cost }} 体力 · {{ durationLabel(estimatedDuration(crop)) }}</small>
      </button>
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
    <div class="plot-heading">
      <strong>{{ plot.crop?.name }}</strong>
      <small>土地 {{ plot.slot + 1 }}</small>
    </div>
    <button class="partner-slot partner-slot--growing" :class="{ assigned: assignedPartner }" :disabled="game.busy || plot.assignment_locked" @click="pickerOpen = !pickerOpen">
      <span class="partner-slot-avatar">
        <CroppedImage v-if="assignedPartner?.artwork?.url && assignedPartner.avatar_crop" :image-url="assignedPartner.artwork.url" :image-width="assignedPartner.artwork.width" :image-height="assignedPartner.artwork.height" :crop="assignedPartner.avatar_crop" :alt="`${assignedPartner.name}头像`" />
        <UserRound v-else :size="15" />
      </span>
      <span><strong>{{ assignedPartner?.name || '没有驻场伙伴' }}</strong><small v-if="plot.assignment_locked"><Lock :size="10" />任务中已锁定</small><small v-else>{{ assignedPartner ? '已解除任务锁定' : '任务未使用伙伴' }}</small></span>
      <ChevronDown v-if="!plot.assignment_locked" :size="13" />
    </button>
    <div v-if="pickerOpen && !plot.assignment_locked" class="partner-picker partner-picker--growing">
      <button v-if="assignedPartner" @click="choosePartner(null)"><span class="picker-empty"><UserRound :size="15" /></span><span><strong>撤下伙伴</strong><small>只影响下一次任务</small></span></button>
      <button v-for="partner in farmingPartners" :key="partner.partner_id" :disabled="partner.locked && partner.partner_id !== assignedPartner?.partner_id" @click="choosePartner(partner.partner_id)">
        <span class="picker-avatar"><CroppedImage v-if="partner.artwork?.url && partner.avatar_crop" :image-url="partner.artwork.url" :image-width="partner.artwork.width" :image-height="partner.artwork.height" :crop="partner.avatar_crop" :alt="`${partner.name}头像`" /><UserRound v-else :size="15" /></span>
        <span><strong>{{ partner.name }}</strong><small>农作 {{ farmingAbility(partner) }}</small></span><Lock v-if="partner.locked" :size="12" />
      </button>
    </div>
    <span v-if="plot.task_snapshot && !ready" class="task-boost">能力 {{ plot.task_snapshot.total_ability }} · 品质 Q{{ plot.task_snapshot.quality_parameters.ability }} · 效率 {{ plot.task_snapshot.time_efficiency.toFixed(2) }}×</span>
    <template v-if="ready">
      <p class="ready-label">{{ plot.task_result ? `${qualityNames[plot.task_result.quality]}品质 · ${plot.task_result.quantity} 个` : '已经成熟' }}</p>
      <button class="primary-button harvest-button" :disabled="game.busy" @click="game.harvest(plot.slot)">
        收获
      </button>
    </template>
    <template v-else>
      <div class="progress-track"><i :style="{ width: `${progress}%` }" /></div>
      <span class="time-left"><Clock3 :size="14" /> {{ timeLabel }}</span>
    </template>
  </article>
</template>

<style scoped>
.farm-plot.picker-open { z-index: 12; overflow: visible; }
.partner-slot { position: relative; width: 100%; min-height: 47px; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 8px; padding: 6px 8px; margin-top: 9px; text-align: left; color: #8c998f; border: 1px dashed #ffffff12; border-radius: 9px; background: #0d141086; cursor: pointer; }.partner-slot.assigned { color: #d9e2d6; border-style: solid; border-color: #8ead7130; background: #8ead710b; }.partner-slot-avatar,.picker-avatar,.picker-empty { width: 31px; height: 31px; overflow: hidden; display: grid; place-items: center; color: #9fbc86; border-radius: 9px 3px; background: #243128; }.partner-slot strong,.partner-slot small,.partner-picker strong,.partner-picker small { display: block; }.partner-slot strong { font-size: 12px; }.partner-slot small { margin-top: 2px; color: #718078; font-size: 12px; }.partner-slot small svg { display: inline; vertical-align: -1px; margin-right: 2px; }.partner-slot--growing { margin: 10px 0 8px; }
.partner-picker { position: absolute; left: 12px; right: 12px; top: 145px; z-index: 8; max-height: 220px; overflow: auto; padding: 7px; border: 1px solid #ffffff18; border-radius: 12px; background: #111a15; box-shadow: 0 18px 45px #0009; }.partner-picker--growing { top: 176px; }.partner-picker > button { width: 100%; min-height: 43px; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 8px; padding: 5px 7px; text-align: left; color: #d9e1d7; border: 0; border-radius: 8px; background: transparent; cursor: pointer; }.partner-picker > button:hover { background: #ffffff08; }.partner-picker > button:disabled { opacity: .42; }.partner-picker strong { font-size: 12px; }.partner-picker small { margin-top: 2px; color: #6f7c73; font-size: 12px; }.partner-picker > p { padding: 14px 8px; margin: 0; color: #6f7b72; font-size: 12px; line-height: 1.5; }.picker-empty { color: #718078; background: #1a241e; }.task-boost { color: #91aa7d; font-size: 12px; margin-bottom: 7px; }
</style>
