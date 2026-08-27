<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import ActionButton from '@/components/ActionButton.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import QuantityStepper from '@/components/QuantityStepper.vue'
import QualityTag from '@/components/QualityTag.vue'
import type { SlotInputEntry, SlotState } from '@/types'

const props = defineProps<{
  open: boolean
  slot: SlotState
  entry: SlotInputEntry | null
  actionKey: string
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'deposit', payload: { itemId: string; quality: number; count: number }): void
}>()

const PRESETS = [1, 5, 10]

const count = ref(1)

watch(
  () => [props.open, props.entry?.item_id, props.entry?.quality],
  () => (count.value = 1),
)

const room = computed(() => Math.max(0, props.slot.capacity - props.slot.units))
const perItem = computed(() => props.entry?.units || 0)
/** 槽里还装得下几个：投料是整笔拒绝的，所以上限要在按下之前就算清楚。 */
const fits = computed(() => (perItem.value ? Math.floor(room.value / perItem.value) : 0))
const maxCount = computed(() => Math.max(1, Math.min(props.entry?.quantity || 1, fits.value)))
const addedUnits = computed(() => perItem.value * count.value)

/** 投进去之后分数变成多少 —— 稀释与提纯的取舍必须是明示的。 */
const previewScore = computed(() => {
  if (!props.entry) return props.slot.quality_score
  const total = props.slot.units + addedUnits.value
  if (total <= 0) return 0
  return (props.slot.units * props.slot.quality_score + addedUnits.value * props.entry.unit_score) / total
})

const delta = computed(() => previewScore.value - props.slot.quality_score)

const subtitle = computed(() => {
  const entry = props.entry
  if (!entry) return ''
  return `仓库中有 ${entry.quantity} 个 · 每个顶 ${entry.units} 份、单位品质分 ${entry.unit_score}`
})

const blockedReason = computed(() => {
  if (!props.entry) return undefined
  if (addedUnits.value > room.value) return '槽里装不下这一批'
  return undefined
})

function preset(value: number) {
  count.value = Math.min(value, maxCount.value)
}

function deposit() {
  const entry = props.entry
  if (!entry) return
  emit('deposit', { itemId: entry.item_id, quality: entry.quality || 0, count: count.value })
}
</script>

<template>
  <ModalSheet
    :open="open && Boolean(entry)"
    :title="entry?.item.name || ''"
    :subtitle="subtitle"
    @close="emit('close')"
  >
    <div v-if="entry" class="deposit-body">
      <div class="deposit-line">
        <span>品质</span>
        <strong>
          <QualityTag v-if="entry.quality" :quality="entry.quality" :name="entry.quality_name" plain />
          <template v-else>无品质</template>
        </strong>
      </div>
      <div class="deposit-line">
        <span>投入后份数</span>
        <strong>{{ Math.floor(slot.units) }} → {{ Math.floor(slot.units + addedUnits) }} / {{ slot.capacity }}</strong>
      </div>
      <div class="deposit-line">
        <span>投入后品质分</span>
        <strong>
          {{ slot.quality_score.toFixed(1) }} → {{ previewScore.toFixed(1) }}
          <em :class="delta >= 0 ? 'up' : 'down'">{{ delta >= 0 ? '+' : '' }}{{ delta.toFixed(1) }}</em>
        </strong>
      </div>

      <div class="deposit-picker">
        <QuantityStepper v-model="count" :max="maxCount" />
        <button
          v-for="value in PRESETS"
          :key="value"
          class="deposit-preset"
          :class="{ active: count === value }"
          :disabled="value > maxCount"
          @click="preset(value)"
        >{{ value }}</button>
        <button class="deposit-preset" :disabled="maxCount <= 1" @click="preset(maxCount)">最多</button>
      </div>

      <p class="deposit-note">品质分是槽内存量的加权平均，消耗只扣份数、不改分数。</p>
    </div>

    <template #footer>
      <div class="deposit-footer">
        <p>
          <span>本次投入</span>
          <strong :class="{ short: Boolean(blockedReason) }">{{ addedUnits }} 份</strong>
        </p>
        <ActionButton
          :action-key="actionKey"
          :disabled="Boolean(blockedReason)"
          :reason="blockedReason"
          @click="deposit"
        >投入</ActionButton>
      </div>
    </template>
  </ModalSheet>
</template>

<style scoped>
.deposit-body { display: flex; flex-direction: column; gap: 11px; }
.deposit-line { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.deposit-line span { color: #849087; font-size: 13px; }
.deposit-line strong { display: inline-flex; align-items: center; gap: 7px; font-size: 14px; }
.deposit-line em { font-style: normal; font-size: 12px; }
.deposit-line em.up { color: var(--leaf-bright); }
.deposit-line em.down { color: #cf8c80; }

.deposit-picker { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 4px; }
.deposit-preset { min-width: 42px; height: 32px; padding: 0 10px; color: inherit; border: 1px solid var(--line); border-radius: 9px; background: #ffffff06; cursor: pointer; }
.deposit-preset.active { color: var(--leaf-bright); border-color: color-mix(in srgb, var(--leaf-bright) 40%, transparent); }
.deposit-preset:disabled { opacity: .4; cursor: not-allowed; }

.deposit-note { margin: 0; color: #7d887f; font-size: 11.5px; line-height: 1.7; }

.deposit-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; }
.deposit-footer p { display: flex; align-items: baseline; gap: 8px; margin: 0; }
.deposit-footer span { color: #849087; font-size: 12px; }
.deposit-footer strong { font-size: 18px; }
.deposit-footer strong.short { color: #cf8c80; }
</style>
