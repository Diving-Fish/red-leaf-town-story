<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Sparkles } from 'lucide-vue-next'

import GachaResultCard, { type GachaResultMeta } from '@/components/gacha/GachaResultCard.vue'
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
const instantFrom = ref(Infinity)
const flashKey = ref(0)
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

const summaryTiers = computed(() => {
  const counts = new Map<number, number>()
  for (const drop of props.results) {
    if (drop.kind !== 'partner' || !drop.rarity) continue
    counts.set(drop.rarity, (counts.get(drop.rarity) || 0) + 1)
  }
  return [...counts.entries()].sort((a, b) => b[0] - a[0]).map(([rarity, count]) => ({ rarity, count }))
})
const itemCount = computed(() => props.results.filter((drop) => drop.kind === 'task_item').reduce((total, drop) => total + drop.quantity, 0))

function clearTimers() {
  timers.forEach((id) => window.clearTimeout(id))
  timers = []
}

function scheduleNext(index: number) {
  if (index >= props.results.length) {
    phase.value = 'done'
    return
  }
  const rarity = metas.value[index]?.rarity
  const wait = rarity && rarity >= 5 ? 950 : rarity === 4 ? 620 : 360
  timers.push(
    window.setTimeout(() => {
      revealCount.value = index + 1
      if (rarity && rarity >= 5) flashKey.value += 1
      scheduleNext(index + 1)
    }, wait),
  )
}

function startSequence() {
  clearTimers()
  phase.value = 'gate'
  revealCount.value = 0
  instantFrom.value = Infinity
  flashKey.value = 0
  timers.push(
    window.setTimeout(() => {
      phase.value = 'revealing'
      scheduleNext(0)
    }, 650),
  )
}

function skip() {
  clearTimers()
  instantFrom.value = revealCount.value
  revealCount.value = props.results.length
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
        <div v-if="flashKey > 0" :key="flashKey" class="pull-overlay-flash" />

        <div v-if="phase === 'gate'" class="pull-gate">
          <span class="pull-gate-ring pull-gate-ring--outer" />
          <span class="pull-gate-ring pull-gate-ring--inner" />
          <Sparkles class="pull-gate-icon" :size="38" />
          <p class="pull-gate-text">裂隙正在回应……</p>
        </div>

        <template v-else>
          <header class="pull-overlay-header">
            <span>{{ phase === 'done' ? '招募结果' : '正在揭示……' }}</span>
            <button v-if="phase !== 'done'" type="button" class="pull-skip" @click="skip">跳过动画</button>
          </header>

          <div class="pull-overlay-grid" :class="{ single: results.length === 1 }">
            <GachaResultCard
              v-for="(drop, index) in results"
              :key="`${index}:${drop.content_id}`"
              :drop="drop"
              :meta="metas[index]"
              :revealed="index < revealCount"
              :instant="index < instantFrom"
              :big="results.length === 1"
            />
          </div>

          <Transition name="pull-summary">
            <footer v-if="phase === 'done'" class="pull-overlay-footer">
              <div class="pull-summary">
                <span v-for="tier in summaryTiers" :key="tier.rarity" :class="`rarity-${tier.rarity}`">{{ tier.rarity }}★ ×{{ tier.count }}</span>
                <span v-if="itemCount" class="pull-summary-item">特殊道具 ×{{ itemCount }}</span>
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
  gap: 22px;
  padding: clamp(16px, 4vw, 40px);
  background:
    radial-gradient(circle at 50% 30%, rgba(215, 173, 88, .1), transparent 55%),
    rgba(6, 9, 7, .88);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
.pull-overlay-flash {
  position: fixed;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background: radial-gradient(circle at 50% 42%, rgba(244, 200, 115, .55), transparent 62%);
  animation: rarity-flash .65s ease;
}

.pull-gate { position: relative; display: grid; place-items: center; width: 220px; height: 220px; color: var(--gold); }
.pull-gate-ring { position: absolute; border: 1px solid rgba(215, 173, 88, .4); border-radius: 50%; }
.pull-gate-ring--outer { inset: 0; border-style: dashed; animation: gate-ring 10s linear infinite; }
.pull-gate-ring--inner { inset: 28px; animation: gate-ring 6s linear infinite reverse; }
.pull-gate-icon { position: relative; z-index: 1; animation: rarity-pulse 1.6s ease-in-out infinite; }
.pull-gate-text { position: absolute; bottom: -8px; color: #cfd8ce; font-size: 12px; letter-spacing: .1em; white-space: nowrap; }

.pull-overlay-header {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  color: #c6b488;
  font: 700 13px Georgia, 'Noto Serif SC', serif;
  letter-spacing: .08em;
}
.pull-skip {
  padding: 7px 13px;
  color: var(--cream);
  font-size: 12px;
  border: 1px solid var(--line);
  border-radius: 99px;
  background: rgba(255, 255, 255, .05);
  cursor: pointer;
}

.pull-overlay-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(5, minmax(84px, 118px));
  gap: 12px;
  max-width: min(760px, 92vw);
}
.pull-overlay-grid.single { grid-template-columns: minmax(180px, 240px); }

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
}
.pull-summary .rarity-5 { color: #2a1608; border-color: transparent; background: linear-gradient(135deg, var(--rarity-5-a), var(--rarity-5-b)); }
.pull-summary .rarity-4 { color: #f0e8ff; border-color: color-mix(in srgb, var(--rarity-4) 55%, transparent); background: color-mix(in srgb, var(--rarity-4) 26%, #1a1424); }
.pull-summary .rarity-3 { color: var(--rarity-3); border-color: color-mix(in srgb, var(--rarity-3) 55%, transparent); }
.pull-continue { min-height: 48px; padding: 0 26px; font-size: 14px; border-radius: 99px; }

.pull-overlay-enter-active, .pull-overlay-leave-active { transition: opacity .22s ease; }
.pull-overlay-enter-from, .pull-overlay-leave-to { opacity: 0; }
.pull-summary-enter-active { transition: opacity .3s ease .1s, transform .3s ease .1s; }
.pull-summary-enter-from { opacity: 0; transform: translateY(10px); }

@media (max-width: 680px) {
  .pull-overlay-grid { grid-template-columns: repeat(3, minmax(72px, 1fr)); gap: 9px; max-width: 96vw; }
  .pull-overlay-grid.single { grid-template-columns: minmax(160px, 210px); }
}
</style>
