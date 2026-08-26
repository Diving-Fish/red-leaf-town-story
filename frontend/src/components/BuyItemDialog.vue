<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { LockKeyhole } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import QuantityStepper from '@/components/QuantityStepper.vue'
import { itemKindName } from '@/lib/items'
import { useGameStore } from '@/stores/game'
import type { ShopEntry } from '@/types'

const props = defineProps<{ open: boolean; entry: ShopEntry | null }>()
const emit = defineEmits<{ (event: 'close'): void }>()

const MAX_BATCH = 99
const PRESETS = [1, 5, 10]

const game = useGameStore()
const quantity = ref(1)

watch(
  () => [props.open, props.entry?.id],
  () => (quantity.value = 1),
)

const coins = computed(() => game.player?.coins || 0)
const price = computed(() => props.entry?.price || 0)
const owned = computed(() => (props.entry ? game.inventoryMap.get(props.entry.item_id)?.quantity || 0 : 0))
const total = computed(() => price.value * quantity.value)
const affordableMax = computed(() => Math.min(MAX_BATCH, price.value ? Math.floor(coins.value / price.value) : MAX_BATCH))
const maxQuantity = computed(() => Math.max(1, affordableMax.value))

const subtitle = computed(() => {
  const entry = props.entry
  if (!entry) return ''
  return `${itemKindName(entry.item.kind)} · 仓库中有 ${owned.value} 个`
})

const blockedReason = computed(() => {
  if (!props.entry) return undefined
  if (props.entry.locked) return `等级 ${props.entry.min_level} 解锁`
  if (total.value > coins.value) return '金币不足'
  return undefined
})

function preset(value: number) {
  quantity.value = Math.min(value, maxQuantity.value)
}

async function buy() {
  const entry = props.entry
  if (!entry) return
  const result = await game.buy(entry.id, quantity.value)
  if (result) quantity.value = 1
}
</script>

<template>
  <ModalSheet :open="open && Boolean(entry)" :title="entry?.item.name || ''" :subtitle="subtitle" @close="emit('close')">
    <div v-if="entry" class="buy-body">
      <p v-if="entry.locked" class="buy-locked"><LockKeyhole :size="14" />等级 {{ entry.min_level }} 才能购买这件商品</p>

      <div class="buy-line">
        <span>单价</span>
        <strong>{{ entry.price }} 金币</strong>
      </div>
      <div class="buy-line">
        <span>回收价</span>
        <strong class="muted">{{ entry.item.sell_price }} 金币</strong>
      </div>

      <div class="buy-picker">
        <QuantityStepper v-model="quantity" :max="maxQuantity" :disabled="entry.locked" />
        <button
          v-for="value in PRESETS"
          :key="value"
          class="buy-preset"
          :class="{ active: quantity === value }"
          :disabled="entry.locked || value > maxQuantity"
          @click="preset(value)"
        >{{ value }}</button>
        <button class="buy-preset" :disabled="entry.locked || maxQuantity <= 1" @click="preset(maxQuantity)">最多</button>
      </div>
    </div>

    <template #footer>
      <div class="buy-footer">
        <p>
          <span>合计</span>
          <strong :class="{ short: total > coins }">{{ total }} 金币</strong>
          <small>持有 {{ coins }}</small>
        </p>
        <ActionButton
          v-if="entry"
          :action-key="`shop:${entry.id}:${quantity}`"
          :group="`shop:${entry.id}`"
          :disabled="Boolean(blockedReason)"
          :reason="blockedReason"
          @click="buy"
        >购买</ActionButton>
      </div>
    </template>
  </ModalSheet>
</template>

<style scoped>
.buy-body { display: grid; gap: 10px; }
.buy-locked { display: flex; align-items: center; gap: 7px; margin: 0; padding: 10px 12px; color: #d8c79c; border: 1px solid color-mix(in srgb, var(--gold) 26%, transparent); border-radius: 11px 4px 11px 4px; background: #ffffff05; font-size: 12px; }
.buy-line { display: flex; align-items: center; justify-content: space-between; padding: 10px 13px; border: 1px solid var(--line); border-radius: 11px 4px 11px 4px; background: #ffffff05; font-size: 13px; }
.buy-line span { color: #8b968c; }
.buy-line strong { color: var(--gold); }
.buy-line strong.muted { color: #9baa9d; }
.buy-picker { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; }
.buy-preset { min-height: 32px; padding: 0 13px; color: #93a094; border: 1px solid var(--line); border-radius: 9px; background: #ffffff05; cursor: pointer; }
.buy-preset.active { color: #16210f; font-weight: 700; border-color: transparent; background: var(--leaf-bright); }
.buy-preset:disabled { opacity: .45; cursor: default; }
.buy-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.buy-footer p { display: flex; align-items: baseline; gap: 8px; margin: 0; color: #8b968c; font-size: 13px; }
.buy-footer strong { color: var(--gold); font-size: 15px; }
.buy-footer strong.short { color: var(--danger); }
.buy-footer small { color: #6f7a71; font-size: 12px; }
</style>
