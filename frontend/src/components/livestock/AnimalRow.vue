<script setup lang="ts">
import { computed } from 'vue'
import { HeartHandshake, Hourglass, PackageOpen, Sparkles } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import GameIcon from '@/components/GameIcon.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import QualityTag from '@/components/QualityTag.vue'
import { formatDuration } from '@/lib/format'
import { qualityName } from '@/lib/quality'
import { useGameStore } from '@/stores/game'
import type { AnimalState } from '@/types'

const props = defineProps<{
  animal: AnimalState
  cycleSeconds: number
  selectable: boolean
  selected: boolean
}>()

const emit = defineEmits<{ (event: 'toggle'): void; (event: 'sell'): void }>()

const game = useGameStore()

const STAGE_LABEL: Record<AnimalState['stage'], string> = {
  incubating: '孵化中',
  juvenile: '幼年',
  adult: '成年',
}

const growing = computed(() => props.animal.stage !== 'adult')
const affectionPercent = computed(() => (props.animal.affection / props.animal.affection_cap) * 100)
const pendingPercent = computed(() =>
  props.animal.overflow_cap ? (props.animal.pending_total / props.animal.overflow_cap) * 100 : 0,
)

const buckets = computed(() =>
  Object.entries(props.animal.pending_output)
    .map(([quality, amount]) => ({ quality: Number(quality), amount }))
    .sort((left, right) => right.quality - left.quality),
)

const careLeft = computed(() => Math.max(0, props.animal.care_daily_limit - props.animal.cared_today))

const careReason = computed(() => {
  if (props.animal.stage === 'incubating') return '还在壳里'
  if (!careLeft.value) return '今天已经照料过了'
  if ((game.player?.stamina || 0) < 1) return '体力不足'
  return undefined
})
</script>

<template>
  <li
    class="animal"
    :class="{ selectable, selected, growing }"
    @click="selectable ? emit('toggle') : undefined"
  >
    <div class="animal-head">
      <span class="animal-icon"><GameIcon :name="animal.icon" :size="22" /></span>
      <div class="animal-title">
        <strong>
          {{ animal.name }}
          <i v-if="animal.nickname" class="species">{{ animal.species_name }}</i>
          <i class="stage" :class="animal.stage">{{ STAGE_LABEL[animal.stage] }}</i>
        </strong>
        <small>
          品质基因 <b>{{ animal.quality_gene }}</b> · 产量基因 <b>{{ animal.yield_gene }}</b>
          <em>上限 {{ animal.gene_cap }}</em>
        </small>
      </div>
      <span v-if="animal.saturated" class="animal-flag"><PackageOpen :size="13" /> 已攒满</span>
    </div>

    <p v-if="growing" class="animal-growth">
      <Hourglass :size="14" />
      还要 {{ animal.remaining_stage_cycles }} 个周期长成，约 {{ formatDuration(animal.remaining_stage_seconds) }}
    </p>

    <template v-else>
      <div class="animal-meter">
        <div class="meter-line">
          <span>待收</span>
          <strong>{{ animal.pending_total }} / {{ animal.overflow_cap }}</strong>
          <em>每周期 {{ animal.yield_per_cycle.toFixed(2) }} 个</em>
        </div>
        <ProgressBar :value="pendingPercent" :color="animal.saturated ? '#cf8c80' : 'var(--gold)'" :height="7" />
        <div v-if="buckets.length || animal.pending_special" class="animal-buckets">
          <QualityTag
            v-for="bucket in buckets"
            :key="bucket.quality"
            :quality="bucket.quality"
            :name="`${qualityName(bucket.quality)}×${bucket.amount}`"
            plain
          />
          <span v-if="animal.pending_special" class="special"><Sparkles :size="12" /> 特殊产出 ×{{ animal.pending_special }}</span>
        </div>
      </div>

      <p class="animal-quality">品质分 Q{{ animal.quality_ability.toFixed(1) }}</p>

      <p v-if="animal.breeding_cooldown > 0" class="animal-cooldown">
        <Hourglass :size="13" /> 配种冷却还剩 {{ animal.breeding_cooldown }} 个周期
      </p>
    </template>

    <div v-if="animal.stage !== 'incubating'" class="animal-meter">
      <div class="meter-line">
        <span>亲密度</span>
        <strong>{{ animal.affection }} / {{ animal.affection_cap }}</strong>
        <em>品质 ×{{ animal.affection_multiplier.toFixed(2) }}</em>
      </div>
      <ProgressBar :value="affectionPercent" color="#d98aa0" :height="7" />
    </div>

    <div class="animal-actions" @click.stop>
      <ActionButton
        :action-key="`livestock:animal:${animal.animal_id}:care`"
        variant="secondary"
        :disabled="Boolean(careReason)"
        :reason="careReason"
        @click="game.careAnimal(animal.animal_id)"
      >
        <HeartHandshake :size="14" /> 照料 <i class="care-left">{{ careLeft }}/{{ animal.care_daily_limit }}</i>
      </ActionButton>
      <button class="animal-sell" @click="emit('sell')">出售</button>
    </div>
  </li>
</template>

<style scoped>
.animal { display: flex; flex-direction: column; gap: 10px; padding: 13px 14px; border: 1px solid var(--line); border-radius: 14px; background: #ffffff05; list-style: none; }
.animal.selectable { cursor: pointer; }
.animal.selected { border-color: color-mix(in srgb, var(--gold) 55%, transparent); background: color-mix(in srgb, var(--gold) 8%, transparent); }

.animal-head { display: flex; align-items: center; gap: 10px; }
.animal-icon { display: grid; place-items: center; width: 38px; height: 38px; border: 1px solid var(--line); border-radius: 12px 4px 12px 4px; background: var(--surface); }
.animal-title { min-width: 0; flex: 1; }
.animal-title strong { display: flex; align-items: center; gap: 7px; font-size: 14px; }
.animal-title small { display: block; margin-top: 3px; color: #7d887f; font-size: 11.5px; }
.animal-title small b { color: var(--cream); font-weight: 600; }
.animal-title small em { margin-left: 6px; font-style: normal; color: #6f7a72; }

.species { font-style: normal; font-size: 11px; color: #7d887f; }
.stage { font-style: normal; font-size: 10.5px; padding: 1px 7px; border-radius: 999px; border: 1px solid currentColor; }
.stage.incubating { color: #b9a06a; }
.stage.juvenile { color: #8fb1c9; }
.stage.adult { color: var(--leaf-bright); }

.animal-flag { display: inline-flex; align-items: center; gap: 4px; color: #cf8c80; font-size: 11px; white-space: nowrap; }

.animal-growth { display: flex; align-items: center; gap: 7px; margin: 0; color: #7d887f; font-size: 12px; }

.meter-line { display: flex; align-items: baseline; gap: 7px; margin-bottom: 5px; font-size: 12px; }
.meter-line span { color: #849087; }
.meter-line strong { font-size: 13px; }
.meter-line em { margin-left: auto; font-style: normal; color: #6f7a72; font-size: 11px; }

.animal-buckets { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }
.special { display: inline-flex; align-items: center; gap: 4px; color: var(--gold); font-size: 11px; }

.animal-quality { margin: 0; color: #7d887f; font-size: 11.5px; }
.animal-cooldown { display: flex; align-items: center; gap: 6px; margin: 0; color: #a4936a; font-size: 11.5px; }

.animal-actions { display: flex; align-items: center; gap: 8px; }
.care-left { font-style: normal; opacity: .7; font-size: 11px; }
.animal-sell { margin-left: auto; min-height: 30px; padding: 0 11px; color: #9aa39b; border: 1px solid var(--line); border-radius: 9px; background: transparent; cursor: pointer; font-size: 12px; }
.animal-sell:hover { color: #cf8c80; border-color: rgba(207, 140, 128, .3); }
</style>
