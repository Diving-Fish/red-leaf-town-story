<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Clock3, LockKeyhole, Sparkles } from 'lucide-vue-next'

import GameIcon from '@/components/GameIcon.vue'
import { useGameStore } from '@/stores/game'
import type { CropDefinition, PlotState } from '@/types'

const props = defineProps<{
  plot?: PlotState
  lockedLevel?: number | null
  crops?: CropDefinition[]
}>()

const game = useGameStore()
const tick = ref(Date.now())
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
const progress = computed(() => {
  if (!props.plot?.crop) return 0
  return Math.min(100, Math.max(3, 100 - (remaining.value / props.plot.crop.growth_seconds) * 100))
})
const timeLabel = computed(() => {
  const minutes = Math.floor(remaining.value / 60)
  const seconds = remaining.value % 60
  return minutes ? `${minutes}分 ${seconds}秒` : `${seconds}秒`
})
</script>

<template>
  <article v-if="!plot" class="farm-plot farm-plot--locked">
    <LockKeyhole :size="28" />
    <strong>待开垦土地</strong>
    <span>等级 {{ lockedLevel || '?' }} 解锁</span>
  </article>

  <article v-else-if="plot.empty" class="farm-plot farm-plot--empty">
    <div class="soil-lines" aria-hidden="true"><i /><i /><i /></div>
    <div class="plot-heading">
      <span>土地 {{ plot.slot + 1 }}</span>
      <small>空闲</small>
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
        <small>-{{ crop.stamina_cost }} 体力</small>
      </button>
    </div>
    <p v-else class="plot-hint">仓库里没有可用种子</p>
  </article>

  <article
    v-else
    class="farm-plot farm-plot--growing"
    :class="{ 'farm-plot--ready': ready }"
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
    <template v-if="ready">
      <p class="ready-label">已经成熟</p>
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
