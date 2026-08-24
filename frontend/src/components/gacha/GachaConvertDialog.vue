<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Flame, Leaf, Minus, Plus } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import { useGameStore } from '@/stores/game'
import type { GachaDrop } from '@/types'

const props = defineProps<{ open: boolean; count: 1 | 10 }>()
const emit = defineEmits<{ (event: 'close'): void; (event: 'pulled', results: GachaDrop[]): void }>()

const game = useGameStore()
const gacha = computed(() => game.state?.gacha)
const mapleFlame = computed(() => game.player?.maple_flame || 0)
const guideLeaves = computed(() => game.player?.guide_leaves || 0)
const rate = computed(() => gacha.value?.maple_flame_per_leaf || 1)

const shortfall = computed(() => Math.max(props.count - guideLeaves.value, 0))
const maxAffordable = computed(() => Math.floor(mapleFlame.value / rate.value))
const enough = computed(() => guideLeaves.value >= props.count)
const quantity = ref(0)

watch(
  () => [props.open, props.count] as const,
  ([isOpen]) => {
    if (isOpen) quantity.value = Math.min(Math.max(shortfall.value, 1), maxAffordable.value)
  },
  { immediate: true },
)

const canConvert = computed(() => quantity.value > 0 && quantity.value <= maxAffordable.value)
const converting = ref(false)
const pulling = ref(false)

function step(delta: number) {
  quantity.value = Math.min(Math.max(quantity.value + delta, 0), maxAffordable.value)
}

async function convert() {
  if (!canConvert.value || converting.value) return
  converting.value = true
  try {
    await game.convertMapleFlame(quantity.value)
  } finally {
    converting.value = false
  }
}

async function confirmPull() {
  if (!enough.value || pulling.value) return
  pulling.value = true
  try {
    const outcome = await game.recruit(props.count)
    if (outcome) emit('pulled', outcome.results)
  } finally {
    pulling.value = false
  }
}
</script>

<template>
  <ModalSheet
    :open="open"
    title="引路枫叶不足"
    :subtitle="`本次招募需要 ${count} 片，当前拥有 ${guideLeaves} 片`"
    @close="emit('close')"
  >
    <div class="convert-balances">
      <span><Flame :size="16" /><small>枫火</small><strong>{{ mapleFlame }}</strong></span>
      <span><Leaf :size="16" /><small>引路枫叶</small><strong>{{ guideLeaves }}</strong></span>
    </div>

    <div v-if="!enough" class="convert-stepper">
      <p class="convert-rate">{{ rate }} 枫火 兑换 1 片引路枫叶</p>
      <div class="stepper-row">
        <button type="button" class="stepper-btn" :disabled="quantity <= 0" @click="step(-1)"><Minus :size="14" /></button>
        <span class="stepper-value">{{ quantity }} 片</span>
        <button type="button" class="stepper-btn" :disabled="quantity >= maxAffordable" @click="step(1)"><Plus :size="14" /></button>
      </div>
      <p class="convert-preview">
        兑换后共有 {{ guideLeaves + quantity }} 片
        <span v-if="quantity && guideLeaves + quantity < count">，仍不够本次招募</span>
      </p>
      <ActionButton
        variant="secondary"
        :action-key="`gacha:convert:${quantity}`"
        :disabled="!canConvert || converting"
        reason="枫火不足"
        @click="convert"
      >兑换 {{ quantity }} 片 · 消耗 {{ quantity * rate }} 枫火</ActionButton>
    </div>

    <template #footer>
      <ActionButton
        :action-key="count === 1 ? 'gacha:single' : 'gacha:ten'"
        :disabled="!enough || pulling"
        reason="引路枫叶仍然不足"
        @click="confirmPull"
      >{{ enough ? `开始招募 · ${count === 1 ? '单次' : '十连'}` : '引路枫叶仍然不足' }}</ActionButton>
    </template>
  </ModalSheet>
</template>

<style scoped>
.convert-balances { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin-bottom: 16px; }
.convert-balances > span { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 7px; padding: 11px; border: 1px solid var(--line); border-radius: 11px; background: #ffffff04; }
.convert-balances svg { color: var(--gold); }
.convert-balances small { color: #849087; font-size: 12px; }
.convert-stepper { padding-top: 4px; }
.convert-rate { margin: 0 0 12px; color: #9ba69c; font-size: 12px; }
.stepper-row { display: flex; align-items: center; justify-content: center; gap: 16px; margin-bottom: 10px; }
.stepper-btn { width: 34px; height: 34px; display: grid; place-items: center; color: var(--cream); border: 1px solid var(--line); border-radius: 10px; background: #ffffff05; cursor: pointer; }
.stepper-btn:disabled { cursor: not-allowed; opacity: .4; }
.stepper-value { min-width: 64px; text-align: center; font: 700 17px Georgia, 'Noto Serif SC', serif; }
.convert-preview { margin: 0 0 14px; color: #8a9589; font-size: 12px; text-align: center; }
.convert-preview span { color: var(--danger); }
.convert-stepper :deep(button) { width: 100%; }
</style>
