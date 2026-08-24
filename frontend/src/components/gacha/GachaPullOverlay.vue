<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Sparkles } from 'lucide-vue-next'

import GachaResultCard, { type GachaResultMeta } from '@/components/gacha/GachaResultCard.vue'
import { normalizeRarity } from '@/lib/rarity'
import type { GachaCatalogPartner, GachaDrop, TaskItemState } from '@/types'

const props = defineProps<{
  open: boolean
  results: GachaDrop[]
  catalog: GachaCatalogPartner[]
  taskItems: Array<Omit<TaskItemState, 'quantity'>>
}>()
const emit = defineEmits<{ (event: 'close'): void }>()

const phase = ref<'gate' | 'revealing' | 'done'>('gate')
const revealCount = ref(0)
const chargingIndex = ref(-1)
const instantAll = ref(false)
const omenOn = ref(false)
const gateBurst = ref(false)
const flashKey = ref(0)
const flashTier = ref(5)
let timers: number[] = []

const metas = computed<GachaResultMeta[]>(() =>
  props.results.map((drop) => {
    if (drop.kind === 'partner') {
      const entry = props.catalog.find((item) => item.partner_id === drop.content_id)
      return { name: entry?.name || drop.content_id, rarity: drop.rarity ?? entry?.rarity ?? null, artwork: entry?.artwork, crop: entry?.avatar_crop }
    }
    const entry = props.taskItems.find((item) => item.id === drop.content_id)
    return { name: entry?.name || drop.content_id, rarity: null }
  }),
)

/* 本次抽卡的最高星级——裂隙在开门前用它「预告」颜色（金 / 紫 / 绿） */
const omenTier = computed(() => {
  let best = 3
  props.results.forEach((drop, index) => {
    if (drop.kind !== 'partner') return
    best = Math.max(best, normalizeRarity(metas.value[index]?.rarity))
  })
  return best
})
const omenText = computed(() => {
  if (!omenOn.value) return '裂隙正在回应……'
  if (omenTier.value >= 5) return '金红之风穿过了裂隙！'
  if (omenTier.value === 4) return '有微光在门后凝聚……'
  return '有人循着光走来了'
})

const summaryTiers = computed(() => {
  const counts = new Map<number, number>()
  for (const drop of props.results) {
    if (drop.kind !== 'partner' || !drop.rarity) continue
    counts.set(drop.rarity, (counts.get(drop.rarity) || 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[0] - a[0]).map(([rarity, count]) => ({ rarity, count }))
})
const itemCount = computed(() => props.results.filter((drop) => drop.kind === 'task_item').reduce((total, drop) => total + drop.quantity, 0))

/* 常驻飘落的枫叶 / 火星，整个覆盖层期间都在 */
const leaves = Array.from({ length: 18 }, (_, i) => ({
  left: `${(i * 37) % 100}%`,
  delay: `${((i * 13) % 45) / 10}s`,
  duration: `${4.4 + ((i * 7) % 32) / 10}s`,
  size: `${8 + (i % 4) * 3}px`,
  drift: `${(((i * 17) % 9) - 4) * 18}px`,
  spin: `${(i % 2 ? 1 : -1) * (200 + i * 15)}deg`,
  opacity: `${0.22 + (i % 5) * 0.09}`,
}))
const embers = Array.from({ length: 10 }, (_, i) => ({
  left: `${(i * 53 + 9) % 100}%`,
  delay: `${((i * 19) % 38) / 10}s`,
  duration: `${3 + ((i * 11) % 22) / 10}s`,
}))

function clearTimers() {
  timers.forEach((id) => window.clearTimeout(id))
  timers = []
}
function later(fn: () => void, ms: number) {
  timers.push(window.setTimeout(fn, ms))
}

function tierAt(index: number) {
  const drop = props.results[index]
  if (!drop || drop.kind !== 'partner') return 0
  return normalizeRarity(metas.value[index]?.rarity)
}

function fireFlash(tier: number) {
  flashTier.value = tier
  flashKey.value += 1
}

function finish() {
  chargingIndex.value = -1
  phase.value = 'done'
}

/* 逐张：先「冲光」（卡背透出星级颜色），再翻面，星级越高蓄力与停顿越长 */
function scheduleNext(index: number) {
  if (index >= props.results.length) {
    finish()
    return
  }
  const tier = tierAt(index)
  const charge = tier >= 5 ? 620 : tier === 4 ? 320 : 130
  const hold = tier >= 5 ? 680 : tier === 4 ? 430 : 250
  chargingIndex.value = index
  later(() => {
    chargingIndex.value = -1
    revealCount.value = index + 1
    if (tier >= 4) fireFlash(tier)
    later(() => scheduleNext(index + 1), hold)
  }, charge)
}

function startSequence() {
  clearTimers()
  phase.value = 'gate'
  revealCount.value = 0
  chargingIndex.value = -1
  instantAll.value = false
  omenOn.value = false
  gateBurst.value = false
  flashKey.value = 0

  later(() => { omenOn.value = true }, 620)
  later(() => {
    gateBurst.value = true
    fireFlash(omenTier.value)
  }, 1180)
  later(() => {
    phase.value = 'revealing'
    later(() => scheduleNext(0), 300)
  }, 1380)
}

/* 点某张未翻开的卡：立刻揭示到这张，然后接着往下走 */
function revealUpTo(index: number) {
  if (phase.value !== 'revealing' || index < revealCount.value) return
  clearTimers()
  chargingIndex.value = -1
  let best = 0
  for (let i = revealCount.value; i <= index; i += 1) best = Math.max(best, tierAt(i))
  revealCount.value = index + 1
  if (best >= 4) fireFlash(best)
  later(() => scheduleNext(index + 1), 260)
}

function skip() {
  /* 门还没开就跳过 → 卡片尚未入场，直接静态呈现；否则让它们一起翻，仍有一次成片翻牌的爽感 */
  if (phase.value === 'gate') instantAll.value = true
  clearTimers()
  chargingIndex.value = -1
  revealCount.value = props.results.length
  if (!instantAll.value && omenTier.value >= 4) fireFlash(omenTier.value)
  phase.value = 'done'
}

function handleBackdrop() {
  if (phase.value === 'done') emit('close')
  else skip()
}

watch(
  () => props.open,
  (value) => {
    if (value) startSequence()
    else clearTimers()
  },
  { immediate: true },
)
onBeforeUnmount(clearTimers)
</script>

<template>
  <Teleport to="body">
    <Transition name="pull-overlay">
      <div v-if="open" class="pull-overlay-backdrop" @click.self="handleBackdrop">
        <div class="pull-ambient" :class="{ dim: phase !== 'gate' }" aria-hidden="true">
          <span
            v-for="(leaf, i) in leaves"
            :key="`leaf${i}`"
            class="pull-leaf"
            :style="{ left: leaf.left, '--size': leaf.size, '--delay': leaf.delay, '--dur': leaf.duration, '--drift': leaf.drift, '--spin': leaf.spin, '--op': leaf.opacity }"
          />
          <span
            v-for="(ember, i) in embers"
            :key="`ember${i}`"
            class="pull-ember"
            :style="{ left: ember.left, '--delay': ember.delay, '--dur': ember.duration }"
          />
        </div>

        <div v-if="flashKey > 0" :key="flashKey" class="pull-overlay-flash" :class="`flash-${flashTier}`" />

        <div v-if="phase === 'gate'" class="pull-gate" :class="omenOn ? `omen omen-${omenTier}` : ''">
          <span class="pull-gate-halo" />
          <span class="pull-gate-ring r1" />
          <span class="pull-gate-ring r2" />
          <span class="pull-gate-ring r3" />
          <span class="pull-rift" />
          <span v-if="gateBurst" class="pull-gate-burst" />
          <Sparkles class="pull-gate-icon" :size="38" />
          <Transition name="pull-omen-text" mode="out-in">
            <p :key="omenText" class="pull-gate-text">{{ omenText }}</p>
          </Transition>
          <button type="button" class="pull-skip pull-skip--gate" @click="skip">跳过动画</button>
        </div>

        <template v-else>
          <header class="pull-overlay-header">
            <span>{{ phase === 'done' ? '招募结果' : '正在揭示……' }}</span>
            <small v-if="phase !== 'done'" class="pull-progress">{{ revealCount }} / {{ results.length }}</small>
            <button v-if="phase !== 'done'" type="button" class="pull-skip" @click="skip">跳过动画</button>
          </header>

          <div class="pull-overlay-grid" :class="{ single: results.length === 1 }">
            <GachaResultCard
              v-for="(drop, index) in results"
              :key="`${index}:${drop.content_id}`"
              :drop="drop"
              :meta="metas[index]"
              :revealed="index < revealCount"
              :instant="instantAll"
              :charging="index === chargingIndex"
              :deal-delay="instantAll ? 0 : index * 42"
              :interactive="phase === 'revealing'"
              :big="results.length === 1"
              @reveal="revealUpTo(index)"
            />
          </div>

          <p v-if="phase === 'revealing'" class="pull-tap-hint">点击卡片可立即揭示</p>

          <Transition name="pull-summary">
            <footer v-if="phase === 'done'" class="pull-overlay-footer">
              <div class="pull-summary">
                <span v-for="(tier, i) in summaryTiers" :key="tier.rarity" :class="`rarity-${tier.rarity}`" :style="{ '--i': i }">{{ tier.rarity }}★ ×{{ tier.count }}</span>
                <span v-if="itemCount" class="pull-summary-item" :style="{ '--i': summaryTiers.length }">特殊道具 ×{{ itemCount }}</span>
              </div>
              <button type="button" class="primary-button pull-continue" @click="emit('close')">收下，继续前路</button>
            </footer>
          </Transition>
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.pull-overlay-backdrop {
  position: fixed;
  inset: 0;
  z-index: 200;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: clamp(16px, 4vw, 40px);
  background:
    radial-gradient(circle at 50% 34%, rgba(215, 173, 88, .12), transparent 55%),
    radial-gradient(circle at 50% 120%, rgba(220, 116, 69, .1), transparent 45%),
    rgba(6, 9, 7, .9);
  backdrop-filter: blur(7px);
  -webkit-backdrop-filter: blur(7px);
}

/* ── 常驻氛围：飘落的枫叶与上升的火星 ── */
.pull-ambient { position: absolute; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; transition: opacity .6s ease; }
.pull-ambient.dim { opacity: .45; }
.pull-leaf {
  position: absolute;
  top: -10%;
  width: var(--size);
  height: var(--size);
  border-radius: 0 100% 0 100%;
  background: linear-gradient(135deg, var(--autumn), var(--gold));
  opacity: 0;
  animation: leaf-fall var(--dur) linear var(--delay) infinite;
}
.pull-ember {
  position: absolute;
  bottom: -4%;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--gold);
  box-shadow: 0 0 8px 1px rgba(215, 173, 88, .8);
  opacity: 0;
  animation: ember-rise var(--dur) ease-in var(--delay) infinite;
}

.pull-overlay-flash {
  position: fixed;
  inset: 0;
  z-index: 4;
  pointer-events: none;
  animation: rarity-flash .65s ease;
}
.pull-overlay-flash.flash-3 { background: radial-gradient(circle at 50% 45%, rgba(190, 214, 165, .3), transparent 60%); }
.pull-overlay-flash.flash-4 { background: radial-gradient(circle at 50% 45%, rgba(184, 152, 255, .45), transparent 62%); }
.pull-overlay-flash.flash-5 { background: radial-gradient(circle at 50% 42%, rgba(250, 224, 165, .68), rgba(226, 112, 63, .2) 38%, transparent 66%); }

/* ── 裂隙之门 ── */
.pull-gate {
  /* 开门前保持中性银白，不提前泄露星级 */
  --omen-a: #8d9a86;
  --omen-b: #cfd8ce;
  --omen-soft: rgba(200, 214, 196, .26);
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  width: min(340px, 78vw);
  aspect-ratio: 1;
  color: var(--gold);
}
.pull-gate.omen-3 { --omen-a: var(--rarity-3); --omen-b: var(--leaf-bright); --omen-soft: var(--rarity-3-soft); }
.pull-gate.omen-4 { --omen-a: var(--rarity-4); --omen-b: #e2d3ff; --omen-soft: var(--rarity-4-soft); }
.pull-gate.omen-5 { --omen-a: var(--rarity-5-a); --omen-b: var(--rarity-5-b); --omen-soft: var(--rarity-5-soft); }

.pull-gate-halo {
  position: absolute;
  inset: -18%;
  border-radius: 50%;
  background: radial-gradient(circle, var(--omen-soft), transparent 62%);
  opacity: .5;
  animation: rarity-pulse 2.6s ease-in-out infinite;
}
.pull-gate.omen .pull-gate-halo { animation: omen-swell .9s cubic-bezier(.15, .8, .3, 1) both, rarity-pulse 2.2s ease-in-out .9s infinite; }

.pull-gate-ring {
  position: absolute;
  inset: 14%;
  border: 1px solid var(--omen-a);
  border-radius: 50%;
  opacity: 0;
  animation: ring-out 2.4s cubic-bezier(.2, .6, .3, 1) infinite;
}
.pull-gate-ring.r2 { animation-delay: .8s; }
.pull-gate-ring.r3 { animation-delay: 1.6s; }

/* 门缝：先竖着裂开，再向两侧撑开 */
.pull-rift {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 52px;
  height: 82%;
  border-radius: 50%;
  background: linear-gradient(to bottom, transparent, var(--omen-b) 18%, #fff8e6 50%, var(--omen-b) 82%, transparent);
  box-shadow: 0 0 60px 16px var(--omen-soft);
  filter: blur(4px);
  transform-origin: center;
  animation: rift-open 1.35s cubic-bezier(.35, 0, .2, 1) both;
}
/* 门缝正中的一道锐利白芯，让裂隙不至于糊成一团光 */
.pull-rift::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 4%;
  width: 2px;
  height: 92%;
  border-radius: 50%;
  transform: translateX(-50%);
  background: linear-gradient(to bottom, transparent, #fff8e6 25%, #fff 50%, #fff8e6 75%, transparent);
}
.pull-gate.omen-5 .pull-rift { filter: blur(5px) saturate(1.35); }

.pull-gate-burst {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid var(--omen-a);
  background: radial-gradient(circle, var(--omen-b), transparent 58%);
  animation: gate-burst .7s cubic-bezier(.1, .75, .3, 1) both;
}

.pull-gate-icon { position: relative; z-index: 2; color: #fff6e2; filter: drop-shadow(0 0 12px var(--omen-a)); animation: rarity-pulse 1.6s ease-in-out infinite; }
.pull-gate-text {
  position: absolute;
  bottom: 4%;
  margin: 0;
  color: #e4ecdf;
  font: 600 13px Georgia, 'Noto Serif SC', serif;
  letter-spacing: .12em;
  white-space: nowrap;
  text-shadow: 0 0 18px var(--omen-soft);
}
.pull-omen-text-enter-active { transition: opacity .3s ease, transform .3s ease, letter-spacing .3s ease; }
.pull-omen-text-leave-active { transition: opacity .12s ease; }
.pull-omen-text-enter-from { opacity: 0; transform: translateY(6px); letter-spacing: .34em; }
.pull-omen-text-leave-to { opacity: 0; }

.pull-skip--gate { position: absolute; bottom: -12%; }

.pull-overlay-header {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 14px;
  color: #c6b488;
  font: 700 13px Georgia, 'Noto Serif SC', serif;
  letter-spacing: .08em;
}
.pull-progress { color: #7f8b7d; font-family: Georgia, serif; letter-spacing: .06em; }
.pull-skip {
  padding: 7px 13px;
  color: var(--cream);
  font-size: 12px;
  border: 1px solid var(--line);
  border-radius: 99px;
  background: rgba(255, 255, 255, .05);
  cursor: pointer;
  transition: background .18s ease, border-color .18s ease;
}
.pull-skip:hover { background: rgba(255, 255, 255, .1); border-color: rgba(215, 173, 88, .4); }

.pull-overlay-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(5, minmax(84px, 118px));
  gap: 12px;
  max-width: min(760px, 92vw);
}
.pull-overlay-grid.single { grid-template-columns: minmax(180px, 240px); }

.pull-tap-hint { position: relative; z-index: 1; margin: 0; color: #6f7a70; font-size: 11px; letter-spacing: .1em; animation: hint-breathe 2.4s ease-in-out infinite; }

.pull-overlay-footer { position: relative; z-index: 1; display: grid; justify-items: center; gap: 14px; }
.pull-summary { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
.pull-summary > span {
  padding: 6px 11px;
  font-size: 12px;
  font-weight: 700;
  border-radius: 99px;
  border: 1px solid var(--line);
  background: #ffffff06;
  color: #d5deca;
  animation: chip-in .4s cubic-bezier(.2, .9, .25, 1) calc(var(--i, 0) * 70ms) both;
}
.pull-summary .rarity-5 { color: #2a1608; border-color: transparent; background: linear-gradient(135deg, var(--rarity-5-a), var(--rarity-5-b)); box-shadow: 0 0 22px var(--rarity-5-soft); }
.pull-summary .rarity-4 { color: #f0e8ff; border-color: color-mix(in srgb, var(--rarity-4) 55%, transparent); background: color-mix(in srgb, var(--rarity-4) 26%, #1a1424); }
.pull-summary .rarity-3 { color: var(--rarity-3); border-color: color-mix(in srgb, var(--rarity-3) 55%, transparent); }
.pull-continue { min-height: 48px; padding: 0 26px; font-size: 14px; border-radius: 99px; }

.pull-overlay-enter-active, .pull-overlay-leave-active { transition: opacity .22s ease; }
.pull-overlay-enter-from, .pull-overlay-leave-to { opacity: 0; }
.pull-summary-enter-active { transition: opacity .3s ease .1s, transform .3s ease .1s; }
.pull-summary-enter-from { opacity: 0; transform: translateY(10px); }

@keyframes leaf-fall {
  0% { transform: translate3d(0, 0, 0) rotate(0deg); opacity: 0; }
  8% { opacity: var(--op); }
  88% { opacity: var(--op); }
  100% { transform: translate3d(var(--drift), 120vh, 0) rotate(var(--spin)); opacity: 0; }
}
@keyframes ember-rise {
  0% { transform: translateY(0) scale(.6); opacity: 0; }
  20% { opacity: .9; }
  100% { transform: translateY(-70vh) scale(1); opacity: 0; }
}
@keyframes rift-open {
  0% { transform: translate(-50%, -50%) scaleX(.05) scaleY(0); opacity: 0; }
  26% { transform: translate(-50%, -50%) scaleX(.05) scaleY(1); opacity: 1; }
  100% { transform: translate(-50%, -50%) scaleX(1) scaleY(1); opacity: .92; }
}
@keyframes ring-out {
  0% { opacity: 0; transform: scale(.25); }
  22% { opacity: .75; }
  100% { opacity: 0; transform: scale(1.9); }
}
@keyframes omen-swell {
  0% { opacity: .3; transform: scale(.6); }
  45% { opacity: 1; transform: scale(1.18); }
  100% { opacity: .55; transform: scale(1); }
}
@keyframes chip-in {
  from { opacity: 0; transform: translateY(8px) scale(.9); }
  to { opacity: 1; transform: none; }
}
@keyframes hint-breathe { 0%, 100% { opacity: .45; } 50% { opacity: .9; } }

@media (max-width: 680px) {
  .pull-overlay-grid { grid-template-columns: repeat(3, minmax(72px, 1fr)); gap: 9px; max-width: 96vw; }
  .pull-overlay-grid.single { grid-template-columns: minmax(160px, 210px); }
  .pull-gate { width: min(260px, 72vw); }
}

@media (prefers-reduced-motion: reduce) {
  .pull-ambient { display: none; }
  .pull-gate-halo, .pull-gate-ring, .pull-rift, .pull-gate-burst, .pull-gate-icon,
  .pull-overlay-flash, .pull-tap-hint, .pull-summary > span { animation: none !important; }
  .pull-rift { transform: translate(-50%, -50%); opacity: .9; }
  .pull-gate-halo, .pull-summary > span { opacity: 1; }
}
</style>
