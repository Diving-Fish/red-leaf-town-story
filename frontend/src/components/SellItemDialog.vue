<script setup lang="ts">
import { computed, reactive, watch } from 'vue'

import ActionButton from '@/components/ActionButton.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import QualityTag from '@/components/QualityTag.vue'
import QuantityStepper from '@/components/QuantityStepper.vue'
import { itemKindName, type InventoryGroup } from '@/lib/items'
import { useGameStore } from '@/stores/game'
import type { InventoryItem } from '@/types'

const props = defineProps<{ open: boolean; group: InventoryGroup | null }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'use', bucket: InventoryItem): void }>()

const game = useGameStore()

/** Requested amount per quality bucket, keyed by inventory_key; missing means "all of it". */
const drafts = reactive<Record<string, number>>({})

watch(
  () => [props.open, props.group?.itemId],
  () => {
    for (const key of Object.keys(drafts)) delete drafts[key]
  },
)

const subtitle = computed(() => {
  const group = props.group
  if (!group) return ''
  return `${itemKindName(group.kind)} · ${group.buckets.length} 种品质 · 共 ${group.quantity} 个`
})

function usable(bucket: InventoryItem) {
  return bucket.tags?.includes('usable') || false
}

function draftOf(bucket: InventoryItem) {
  const raw = drafts[bucket.inventory_key] ?? bucket.quantity
  return Math.min(bucket.quantity, Math.max(1, raw))
}

function setDraft(bucket: InventoryItem, value: number) {
  drafts[bucket.inventory_key] = value
}

function bucketTotal(bucket: InventoryItem) {
  return bucket.sell_price * draftOf(bucket)
}

async function sell(bucket: InventoryItem) {
  // 弹窗里已经逐档列出了数量和金额，本身就是确认步骤，不再叠一层确认框。
  await game.sell(bucket.item_id, draftOf(bucket), bucket.quality)
  delete drafts[bucket.inventory_key]
  if (!props.group?.quantity) emit('close')
}
</script>

<template>
  <ModalSheet :open="open && Boolean(group)" :title="group?.name || ''" :subtitle="subtitle" @close="emit('close')">
    <div v-if="group" class="sell-rows">
      <article v-for="bucket in group.buckets" :key="bucket.inventory_key" class="sell-row" :class="`quality-${bucket.quality || 1}`">
        <header>
          <QualityTag :quality="bucket.quality" :name="bucket.quality_name" />
          <span v-if="!bucket.quality" class="row-plain">无品质</span>
          <strong class="row-count">×{{ bucket.quantity }}</strong>
        </header>

        <p v-if="!bucket.sell_price" class="row-note">{{ bucket.kind === 'seed' ? '种植用种子，商店不收购' : '这个物品商店不收购' }}</p>
        <template v-else>
          <p class="row-price">
            收购价 <em>{{ bucket.sell_price }}</em> 金币/个
            <span v-if="bucket.quality_sale_multiplier > 1" class="row-multiplier">品质 {{ bucket.quality_sale_multiplier }}×</span>
          </p>
          <div class="row-actions">
            <QuantityStepper
              :model-value="draftOf(bucket)"
              :max="bucket.quantity"
              @update:model-value="setDraft(bucket, $event)"
            />
            <span class="row-total">{{ bucketTotal(bucket) }} 金币</span>
            <ActionButton
              :action-key="`inventory:${bucket.item_id}:${bucket.quality || 0}:${draftOf(bucket)}`"
              :group="`inventory:${bucket.item_id}:${bucket.quality || 0}`"
              @click="sell(bucket)"
            >出售</ActionButton>
          </div>
        </template>
        <div v-if="usable(bucket)" class="row-actions row-actions--use">
          <ActionButton
            variant="secondary"
            :action-key="`inventory:${bucket.item_id}:use`"
            @click="emit('use', bucket)"
          >使用</ActionButton>
        </div>
      </article>
    </div>

    <template #footer>
      <p class="sell-footer">
        <span>全部收购价</span>
        <strong>{{ group?.value || 0 }} 金币</strong>
      </p>
    </template>
  </ModalSheet>
</template>

<style scoped>
.sell-rows { display: grid; gap: 9px; }
.sell-row {
  display: grid;
  gap: 7px;
  padding: 12px 13px;
  border: 1px solid var(--line);
  border-radius: 13px 4px 13px 4px;
  background: #ffffff05;
}
.sell-row.quality-2 { border-color: color-mix(in srgb, var(--quality-2) 30%, transparent); }
.sell-row.quality-3 { border-color: color-mix(in srgb, var(--quality-3) 34%, transparent); }
.sell-row.quality-4 { border-color: color-mix(in srgb, var(--quality-4) 38%, transparent); }
.sell-row.quality-5 { border-color: color-mix(in srgb, var(--quality-5) 46%, transparent); }
.sell-row header { display: flex; align-items: center; gap: 8px; }
.row-plain { color: #9baa9d; font-size: 12px; }
.row-count { margin-left: auto; color: var(--cream); font-size: 14px; }
.row-price { margin: 0; color: #8b968c; font-size: 12px; }
.row-price em { color: var(--cream); font-style: normal; font-weight: 700; }
.row-multiplier { margin-left: 7px; padding: 1px 7px; color: var(--gold); border: 1px solid color-mix(in srgb, var(--gold) 32%, transparent); border-radius: 999px; }
.row-note { margin: 0; color: #7f8a80; font-size: 12px; }
.row-actions { display: flex; align-items: center; gap: 9px; }
.row-actions--use { justify-content: flex-end; }
.row-total { flex: 1; min-width: 0; color: var(--gold); font-weight: 700; font-size: 13px; text-align: right; }
.sell-footer { display: flex; align-items: center; justify-content: space-between; margin: 0; color: #8b968c; font-size: 13px; }
.sell-footer strong { color: var(--gold); }
</style>
