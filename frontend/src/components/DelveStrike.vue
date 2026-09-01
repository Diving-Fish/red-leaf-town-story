<script setup lang="ts">
import { computed } from 'vue'

import type { DelveBattleLog } from '@/types'

/** 战报刻印：一次行动的骰面、算式与结果。战斗里所有数学都在这里露出来。 */
const props = defineProps<{ log: DelveBattleLog; friendly: boolean }>()

// 自然 1 是这套系统里唯一的“必失”，值得和普通没打中区分开。
const fumble = computed(() => props.log.roll === 1 && props.log.hit === false)

const verdict = computed(() => {
  if (props.log.action === 'item') return '恢复'
  if (props.log.action === 'advantage') return '备战'
  if (props.log.action === 'flee') return props.log.hit ? '脱离' : '被缠住'
  if (props.log.critical) return '会心'
  if (fumble.value) return '失手'
  return props.log.hit ? '命中' : '未命中'
})

const tone = computed(() => {
  if (props.log.critical) return 'crit'
  if (fumble.value) return 'fumble'
  if (props.log.action === 'item') return 'heal'
  if (props.log.action === 'advantage') return 'ready'
  if (props.log.hit === false) return 'miss'
  return props.friendly ? 'hit' : 'hurt'
})

const amount = computed(() => props.log.damage || props.log.healing || 0)
const amountPrefix = computed(() => (props.log.healing ? '+' : '−'))
const dice = computed(() => (props.log.rolls.length > 1 ? props.log.rolls : []))
</script>

<template>
  <article class="strike" :class="tone">
    <span v-if="log.roll !== null" class="strike-die">
      <b>{{ log.roll }}</b>
      <small>d20</small>
    </span>
    <span v-else class="strike-die blank"><b>·</b><small>{{ log.action === 'item' ? '道具' : '准备' }}</small></span>

    <div class="strike-copy">
      <p class="strike-line">
        <em>{{ log.actor_name }}</em>
        <template v-if="log.target_name"><i>→</i><em>{{ log.target_name }}</em></template>
      </p>
      <h3 class="strike-verdict">{{ verdict }}</h3>
      <p v-if="log.total !== null" class="strike-math">
        {{ log.roll }}
        <template v-if="log.modifier"> {{ log.modifier >= 0 ? '+' : '−' }} {{ Math.abs(log.modifier) }}</template>
        = <b>{{ log.total }}</b>
        <span v-if="dice.length" class="strike-dice">双骰 {{ dice.join(' / ') }}</span>
      </p>
      <p class="strike-text">{{ log.text }}</p>
    </div>

    <span v-if="amount" class="strike-amount">{{ amountPrefix }}{{ amount }}</span>
  </article>
</template>

<style scoped>
.strike {
  --strike-tone: var(--leaf-bright);
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid color-mix(in srgb, var(--strike-tone) 34%, transparent);
  border-left: 3px solid var(--strike-tone);
  border-radius: 4px 16px 4px 16px;
  background: linear-gradient(105deg, color-mix(in srgb, var(--strike-tone) 13%, transparent), #0e1510 62%);
  animation: strike-in .26s cubic-bezier(.2, .9, .3, 1.2);
}
.strike.hurt { --strike-tone: var(--autumn); }
.strike.crit { --strike-tone: var(--gold); }
.strike.miss { --strike-tone: #6f7c72; }
.strike.fumble { --strike-tone: var(--danger); }
.strike.heal { --strike-tone: var(--quality-2); }
.strike.ready { --strike-tone: var(--quality-3); }

.strike-die {
  display: grid;
  width: 54px;
  height: 54px;
  place-items: center;
  gap: 1px;
  color: var(--strike-tone);
  border: 1px solid color-mix(in srgb, var(--strike-tone) 46%, transparent);
  border-radius: 16px 5px 16px 5px;
  background: #0b120e;
}
.strike-die b { font: 700 23px/1 var(--font-display); }
.strike-die small { color: #7d8a80; font-size: 10px; letter-spacing: .1em; }
.strike-die.blank b { color: #6f7c72; }

.strike-copy { min-width: 0; }
.strike-line { display: flex; align-items: center; gap: 6px; margin: 0; color: #8b978c; font-size: var(--font-caption); }
.strike-line em { overflow: hidden; color: #c3ccc1; font-style: normal; white-space: nowrap; text-overflow: ellipsis; }
.strike-line i { color: #6f7c72; font-style: normal; }
.strike-verdict { margin: 2px 0 3px; color: var(--strike-tone); font: 700 var(--font-section-title)/1.2 var(--font-display); letter-spacing: .06em; }
.strike-math { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; margin: 0 0 4px; color: #93a094; font-size: var(--font-caption); font-variant-numeric: tabular-nums; }
.strike-math b { color: var(--cream); }
.strike-dice { color: #7d8a80; }
.strike-text { margin: 0; color: #93a094; font-size: var(--font-copy); line-height: 1.6; }

.strike-amount {
  color: var(--strike-tone);
  font: 700 34px/1 var(--font-display);
  font-variant-numeric: tabular-nums;
  animation: strike-slam .3s cubic-bezier(.2, .9, .3, 1.3);
}

@keyframes strike-in {
  from { opacity: 0; transform: translateX(-8px); }
  to { opacity: 1; transform: none; }
}
@keyframes strike-slam {
  0% { opacity: 0; transform: scale(1.5); }
  60% { opacity: 1; transform: scale(.94); }
  100% { transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  .strike, .strike-amount { animation: none; }
}
@media (max-width: 620px) {
  .strike { gap: 11px; padding: 12px; }
  .strike-die { width: 46px; height: 46px; }
  .strike-die b { font-size: 20px; }
  .strike-amount { font-size: 27px; }
}
</style>
