<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Coins, FlaskConical } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import { useGameStore } from '@/stores/game'

type Source = 'potion' | 'flame'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (event: 'close'): void }>()

const game = useGameStore()
const selected = ref<Source>('potion')

const supply = computed(() => game.state?.stamina_supply || null)
const stamina = computed(() => game.liveStamina)
const cap = computed(() => game.player?.stamina_cap || 0)

const potionBlocked = computed(() => (supply.value && supply.value.potion_owned < 1 ? '没有绯恩特调' : ''))
const flameBlocked = computed(() => {
  const entry = supply.value
  if (!entry) return ''
  if (entry.purchase_next_price === null) return '今日已买满'
  if ((game.player?.maple_flame || 0) < entry.purchase_next_price) return '枫火不足'
  return ''
})

const blocked = computed(() => (selected.value === 'potion' ? potionBlocked.value : flameBlocked.value))
const actionKey = computed(() => (selected.value === 'potion' ? 'stamina:potion' : 'stamina:purchase'))
const cost = computed(() => {
  const entry = supply.value
  if (!entry) return ''
  if (selected.value === 'potion') return `绯恩特调 ×1`
  return entry.purchase_next_price === null ? '—' : `${entry.purchase_next_price} 枫火`
})

// 打开时落在能用的那一项上，别让玩家先撞一次灰按钮。
watch(
  () => props.open,
  (value) => {
    if (!value) return
    selected.value = potionBlocked.value && !flameBlocked.value ? 'flame' : 'potion'
  },
  { immediate: true },
)

async function confirm() {
  if (blocked.value) return
  const done = selected.value === 'potion' ? await game.useStaminaPotion() : await game.buyStamina()
  if (done) emit('close')
}
</script>

<template>
  <ModalSheet :open="open" title="补充体力" :subtitle="`${stamina} / ${cap}`" @close="emit('close')">
    <div v-if="supply" class="supply" role="radiogroup" aria-label="补充方式">
      <div class="supply-grid">
        <button
          class="supply-option"
          :class="{ selected: selected === 'potion', blocked: Boolean(potionBlocked) }"
          role="radio"
          :aria-checked="selected === 'potion'"
          @click="selected = 'potion'"
        >
          <span class="supply-icon tonic"><FlaskConical :size="26" stroke-width="1.7" /></span>
          <strong>绯恩特调</strong>
          <em>+{{ supply.potion_restore }}</em>
          <small :class="{ short: Boolean(potionBlocked) }">{{ potionBlocked || `持有 ${supply.potion_owned}` }}</small>
        </button>

        <button
          class="supply-option"
          :class="{ selected: selected === 'flame', blocked: Boolean(flameBlocked) }"
          role="radio"
          :aria-checked="selected === 'flame'"
          @click="selected = 'flame'"
        >
          <span class="supply-icon flame"><Coins :size="26" stroke-width="1.7" /></span>
          <strong>枫火兑换</strong>
          <em>+{{ supply.purchase_restore }}</em>
          <small :class="{ short: Boolean(flameBlocked) }">
            {{ flameBlocked || `${supply.purchase_next_price} 枫火` }}
          </small>
        </button>
      </div>

      <ol class="supply-ladder" :class="{ dimmed: selected !== 'flame' }">
        <li
          v-for="(price, index) in supply.purchase_prices"
          :key="index"
          :class="{ spent: index < supply.purchase_used_today, next: index === supply.purchase_used_today }"
        >
          <span>{{ price }}</span>
          <small>{{ index + 1 }}</small>
        </li>
      </ol>
    </div>

    <template #footer>
      <div class="supply-footer">
        <p><span>消耗</span><strong :class="{ short: Boolean(blocked) }">{{ cost }}</strong></p>
        <ActionButton
          :action-key="actionKey"
          group="stamina:"
          :disabled="Boolean(blocked)"
          :reason="blocked || undefined"
          @click="confirm"
        >{{ blocked || '确认兑换' }}</ActionButton>
      </div>
    </template>
  </ModalSheet>
</template>

<style scoped>
.supply { display: grid; gap: 12px; }
.supply-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.supply-option {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 4px;
  padding: 18px 12px 15px;
  color: var(--cream);
  text-align: center;
  border: 1px solid var(--line);
  border-radius: 16px 5px 16px 5px;
  background: #ffffff05;
  cursor: pointer;
  transition: border-color .16s ease, background .16s ease;
}
.supply-option:hover { background: #ffffff0b; }
.supply-option:focus-visible { outline: 2px solid var(--leaf); outline-offset: 2px; }
.supply-option.selected { border-color: var(--leaf-bright); background: linear-gradient(150deg, rgba(119, 153, 91, .2), #ffffff05); }
.supply-option.selected::after {
  content: '';
  position: absolute;
  inset: -1px;
  border: 1px solid var(--leaf-bright);
  border-radius: inherit;
  pointer-events: none;
}
.supply-option.blocked { opacity: .55; }
.supply-option.blocked.selected { opacity: .8; border-color: var(--danger); }
.supply-option.blocked.selected::after { border-color: var(--danger); }
.supply-icon { display: grid; place-items: center; width: 52px; height: 52px; margin-bottom: 4px; border-radius: 15px 5px 15px 5px; }
.supply-icon.tonic { color: #9fd6c4; background: rgba(159, 214, 196, .12); }
.supply-icon.flame { color: var(--gold); background: rgba(215, 173, 88, .12); }
.supply-option strong { font-size: 14px; }
.supply-option em { color: var(--leaf-bright); font: 700 15px/1 inherit; font-style: normal; font-variant-numeric: tabular-nums; }
.supply-option small { color: #8b968c; font-size: 12px; font-variant-numeric: tabular-nums; }
.supply-option small.short { color: var(--danger); }

.supply-ladder { display: flex; gap: 6px; margin: 0; padding: 0; list-style: none; transition: opacity .16s ease; }
.supply-ladder.dimmed { opacity: .38; }
.supply-ladder li { flex: 1; display: grid; justify-items: center; gap: 1px; padding: 7px 4px; color: #93a094; border: 1px solid var(--line); border-radius: 10px 3px 10px 3px; background: #ffffff04; }
.supply-ladder li span { font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; }
.supply-ladder li small { font-size: 10px; color: #6f7a71; }
.supply-ladder li.spent { opacity: .4; }
.supply-ladder li.spent span { text-decoration: line-through; }
.supply-ladder li.next { color: var(--gold); border-color: color-mix(in srgb, var(--gold) 45%, transparent); background: rgba(215, 173, 88, .08); }

.supply-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.supply-footer p { display: flex; align-items: baseline; gap: 8px; margin: 0; color: #8b968c; font-size: 13px; }
.supply-footer strong { color: var(--gold); font-size: 15px; font-variant-numeric: tabular-nums; }
.supply-footer strong.short { color: var(--danger); }

@media (max-width: 400px) {
  .supply-option { grid-template-columns: 52px 1fr auto; justify-items: start; text-align: left; padding: 12px; column-gap: 12px; align-items: center; }
  .supply-icon { grid-row: span 2; margin-bottom: 0; }
  .supply-option strong { grid-column: 2; }
  .supply-option em { grid-column: 3; grid-row: 1; justify-self: end; }
  .supply-option small { grid-column: 2 / -1; }
}
</style>
