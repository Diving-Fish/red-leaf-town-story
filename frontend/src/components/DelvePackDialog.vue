<script setup lang="ts">
import { computed } from 'vue'

import GameIcon from '@/components/GameIcon.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import QualityTag from '@/components/QualityTag.vue'
import QuantityStepper from '@/components/QuantityStepper.vue'
import type { InventoryItem } from '@/types'

/** 出发前编携带包：格数有限，进副本后只能用带上的这些。 */
const props = defineProps<{
  open: boolean
  items: InventoryItem[]
  counts: Record<string, number>
  slots: number
}>()

const emit = defineEmits<{
  (event: 'update', payload: { key: string; count: number }): void
  (event: 'close'): void
}>()

const used = computed(() => Object.values(props.counts).reduce((total, count) => total + count, 0))
const room = computed(() => Math.max(0, props.slots - used.value))

function countFor(item: InventoryItem) {
  return props.counts[item.inventory_key] || 0
}

function maxFor(item: InventoryItem) {
  return Math.max(countFor(item), Math.min(item.quantity, countFor(item) + room.value))
}

function healText(item: InventoryItem) {
  const use = item.delve_use
  if (!use) return ''
  const flat = use.flat + Math.max(0, (item.quality || 1) - 1) * use.quality_bonus
  return `恢复 ${use.dice}${flat ? ` +${flat}` : ''}`
}
</script>

<template>
  <ModalSheet
    :open="open"
    title="携带包"
    :subtitle="`最多 ${slots} 份 · 出发时从仓库扣除，没用完的随撤离退回`"
    @close="emit('close')"
  >
    <div class="pack-list">
      <div v-for="item in items" :key="item.inventory_key" class="pack-row" :class="{ packed: countFor(item) > 0 }">
        <span class="pack-icon"><GameIcon :name="item.icon" :size="22" /></span>
        <span class="pack-copy">
          <strong>
            {{ item.name }}
            <QualityTag v-if="item.quality" :quality="item.quality" :name="item.quality_name" plain />
          </strong>
          <small>{{ healText(item) }} · 仓库 {{ item.quantity }}</small>
        </span>
        <QuantityStepper
          :model-value="countFor(item)"
          :min="0"
          :max="maxFor(item)"
          @update:model-value="(count) => emit('update', { key: item.inventory_key, count })"
        />
      </div>

      <p v-if="!items.length" class="pack-empty">仓库里没有能带进副本的道具。秋露药膏可以在加工台做。</p>
    </div>

    <template #footer>
      <div class="pack-footer">
        <p><span>已装</span><strong :class="{ full: room === 0 }">{{ used }} / {{ slots }}</strong></p>
        <button class="primary-button" @click="emit('close')">完成</button>
      </div>
    </template>
  </ModalSheet>
</template>

<style scoped>
.pack-list { display: grid; gap: 6px; }
.pack-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 11px;
  padding: 9px 11px;
  border: 1px solid var(--line);
  border-radius: 13px 4px 13px 4px;
  background: #ffffff05;
}
.pack-row.packed { border-color: color-mix(in srgb, var(--leaf-bright) 40%, transparent); background: #a8c98514; }
.pack-icon { width: 40px; height: 40px; display: grid; place-items: center; color: var(--gold); border-radius: 12px 4px 12px 4px; background: #d7ad5814; }
.pack-copy { display: grid; gap: 3px; min-width: 0; }
.pack-copy strong { display: inline-flex; align-items: center; gap: 6px; font-size: var(--font-body); }
.pack-copy small { color: #849087; font-size: var(--font-caption); }
.pack-empty { margin: 18px 0; color: #78857b; font-size: var(--font-copy); text-align: center; line-height: 1.7; }
.pack-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; }
.pack-footer p { display: flex; align-items: baseline; gap: 8px; margin: 0; }
.pack-footer span { color: #849087; font-size: var(--font-caption); }
.pack-footer strong { font-size: 18px; }
.pack-footer strong.full { color: var(--gold); }
</style>
