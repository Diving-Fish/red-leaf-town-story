<script setup lang="ts">
import { computed } from 'vue'
import { Check, PackageCheck, RotateCcw } from 'lucide-vue-next'
import ModalSheet from '@/components/ModalSheet.vue'
import { qualityName } from '@/lib/quality'
import type { ProductionOutcome } from '@/stores/game'

const props = defineProps<{ outcome: ProductionOutcome | null }>()
const emit = defineEmits<{ (event: 'close'): void }>()
const outcome = computed(() => props.outcome)
type Drop = NonNullable<ProductionOutcome['drops']>[number] & { trait_name?: string }

function groupItems(items: Drop[] = []) {
  const groups = new Map<string, Drop>()
  for (const item of items) {
    const key = JSON.stringify([item.item_id, item.quality, item.trait_name || ''])
    const previous = groups.get(key)
    if (previous) previous.quantity += item.quantity
    else groups.set(key, { ...item })
  }
  return Array.from(groups, ([key, item]) => ({ ...item, key }))
}

const drops = computed(() => groupItems(outcome.value?.drops))
const refunds = computed(() => groupItems(outcome.value?.refunded_inputs))
const total = computed(() => drops.value.reduce((sum, item) => sum + item.quantity, 0) || outcome.value?.quantity || 0)
</script>

<template>
  <ModalSheet
    :open="!!outcome"
    title="加工收获"
    :subtitle="`${outcome?.completed_count ? `已领取 ${outcome.completed_count} 份加工` : '成品已领取'} · 共 ${total} 件`"
    presentation="dialog"
    :close-on-backdrop="false"
    elevated
    @close="emit('close')"
  >
    <template #icon><span class="success-icon"><Check :size="24" /></span></template>
    <template v-if="outcome" #default>
          <section aria-label="获得成品">
            <h3><PackageCheck :size="16" />获得成品</h3>
            <ul class="item-list">
              <li v-for="item in drops" :key="item.key" class="result-item">
                <span class="item-copy"><strong>{{ item.item?.name || item.item_id }}</strong><small :style="{ color: `var(--quality-${item.quality}, var(--muted))` }">{{ item.quality_name || qualityName(item.quality) }}</small></span>
                <span class="quantity">×{{ item.quantity }}</span>
              </li>
              <li v-if="!drops.length" class="result-item"><span>加工成品</span><span class="quantity">×{{ total }}</span></li>
            </ul>
          </section>

          <section v-if="refunds.length || outcome.refunded_stamina" class="refund-section" aria-label="特性返还">
            <h3><RotateCcw :size="16" />特性返还</h3>
            <ul class="item-list">
              <li v-for="item in refunds" :key="item.key" class="result-item">
                <span class="item-copy"><strong>{{ item.item?.name || item.item_id }}</strong><small><span :style="{ color: `var(--quality-${item.quality}, var(--muted))` }">{{ item.quality_name || qualityName(item.quality) }}</span><span v-if="item.trait_name"> · {{ item.trait_name }}</span></small></span>
                <span class="quantity">+{{ item.quantity }}</span>
              </li>
              <li v-if="outcome.refunded_stamina" class="result-item"><span class="item-copy"><strong>体力</strong><small>物尽其用</small></span><span class="quantity">+{{ outcome.refunded_stamina }}</span></li>
            </ul>
          </section>
    </template>
    <template v-if="outcome" #footer>
      <div class="outcome-footer"><span>物品已放入仓库</span><span v-if="outcome.experience">经验 +{{ outcome.experience }}</span><small>查看完毕后，点击右上角 × 关闭</small></div>
    </template>
  </ModalSheet>
</template>

<style scoped>
.success-icon { display: grid; place-items: center; width: 40px; height: 40px; border-radius: 12px; background: #87a96b1f; color: var(--leaf-bright); }
h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; color: var(--muted); font-size: 12px; font-weight: 500; }
.item-list { margin: 0; padding: 0; list-style: none; border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
.result-item { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 14px; background: #ffffff03; }
.result-item + .result-item { border-top: 1px solid var(--line); }
.item-copy { min-width: 0; display: grid; gap: 4px; overflow-wrap: anywhere; }
.item-copy strong { font-size: 14px; font-weight: 500; }
.item-copy small { color: var(--muted); font-size: 12px; }
.quantity { flex-shrink: 0; font-size: 17px; font-weight: 600; font-variant-numeric: tabular-nums; }
.refund-section { margin-top: 22px; }
.refund-section h3, .refund-section .quantity { color: var(--leaf-bright); }
.outcome-footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; color: var(--muted); font-size: 12px; }
.outcome-footer small { flex-basis: 100%; font-size: 11px; color: #849185; }
</style>
