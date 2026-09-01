<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

import GameIcon from '@/components/GameIcon.vue'
import PartnerAvatar from '@/components/PartnerAvatar.vue'
import type { CropRect, PartnerArtwork } from '@/types'

/** 战斗里的一个单位：伙伴用立绘头像，敌人用自己配置的图标；名字和状态放在 hover / 轻触弹出的气泡里。 */
const props = withDefaults(
  defineProps<{
    name: string
    kind: 'party' | 'enemy'
    hp?: number | null
    maxHp?: number | null
    armorClass?: number | null
    artwork?: PartnerArtwork | null
    crop?: CropRect | null
    icon?: string
    boss?: boolean
    active?: boolean
    note?: string
    size?: number
  }>(),
  { size: 38, boss: false, active: false },
)

const root = ref<HTMLElement>()
const tip = ref<HTMLElement>()
const tipOpen = ref(false)
const tipStyle = ref<Record<string, string>>({})

const down = computed(() => typeof props.hp === 'number' && props.hp <= 0)
const ratio = computed(() => {
  if (typeof props.hp !== 'number' || !props.maxHp) return 1
  return Math.max(0, Math.min(1, props.hp / props.maxHp))
})
const status = computed(() => {
  if (down.value) return props.kind === 'party' ? '已经失去战斗力' : '已经倒下'
  if (typeof props.hp === 'number' && props.maxHp) return `${props.hp} / ${props.maxHp} HP`
  return ''
})

function hoverCapable() {
  return typeof window !== 'undefined' && window.matchMedia('(hover: hover)').matches
}

async function openTip() {
  tipOpen.value = true
  await nextTick()
  const anchor = root.value?.getBoundingClientRect()
  const bubble = tip.value?.getBoundingClientRect()
  if (!anchor || !bubble) return
  const left = Math.min(Math.max(8, anchor.left + anchor.width / 2 - bubble.width / 2), window.innerWidth - bubble.width - 8)
  const above = anchor.top - bubble.height - 9
  tipStyle.value = { left: `${left}px`, top: `${above < 8 ? anchor.bottom + 9 : above}px` }
  if (!hoverCapable()) {
    document.addEventListener('click', closeSoon, { once: true, capture: true })
  }
}

function closeTip() {
  tipOpen.value = false
}

function closeSoon() {
  // 触屏上点别处就收起来，避免气泡一直挂在屏幕上。
  setTimeout(closeTip, 0)
}

function onEnter() {
  if (hoverCapable()) openTip()
}

function onLeave() {
  if (hoverCapable()) closeTip()
}

function onClick() {
  if (tipOpen.value) closeTip()
  else openTip()
}

onBeforeUnmount(closeTip)
</script>

<template>
  <button
    ref="root"
    type="button"
    class="unit-chip"
    :class="[kind, { active, down, boss }]"
    :style="{ '--unit-size': `${size}px` }"
    :aria-label="`${name}${status ? ` · ${status}` : ''}`"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
    @focus="onEnter"
    @blur="onLeave"
    @click.stop="onClick"
  >
    <PartnerAvatar
      v-if="kind === 'party'"
      :artwork="artwork"
      :crop="crop"
      :name="name"
      :size="size"
    />
    <span v-else class="unit-seal"><GameIcon :name="icon" :size="Math.round(size * 0.5)" /></span>
    <i class="unit-hp"><b :style="{ width: `${Math.round(ratio * 100)}%` }" /></i>

    <Teleport to="body">
      <div v-if="tipOpen" ref="tip" class="unit-tip" :class="kind" :style="tipStyle">
        <strong>{{ name }}</strong>
        <span v-if="status">{{ status }}</span>
        <span v-if="armorClass" class="tip-muted">AC {{ armorClass }}</span>
        <span v-if="note" class="tip-muted">{{ note }}</span>
      </div>
    </Teleport>
  </button>
</template>

<style scoped>
.unit-chip {
  position: relative;
  display: grid;
  gap: 3px;
  padding: 3px;
  border: 1px solid transparent;
  border-radius: 13px 5px 13px 5px;
  background: transparent;
  cursor: pointer;
  transition: border-color .16s ease, transform .16s ease;
}
.unit-chip.active { border-color: var(--gold); transform: translateY(-2px); }
.unit-chip.down { filter: saturate(.2); opacity: .45; }
.unit-seal {
  width: var(--unit-size);
  height: var(--unit-size);
  display: grid;
  place-items: center;
  color: var(--autumn);
  border-radius: calc(var(--unit-size) * .27) calc(var(--unit-size) * .09);
  background: #31201a;
}
.unit-chip.boss .unit-seal { color: var(--gold); background: #35291a; }
.unit-hp { display: block; overflow: hidden; height: 3px; border-radius: 99px; background: #ffffff14; }
.unit-hp b { display: block; height: 100%; background: var(--leaf-bright); transition: width .3s ease; }
.unit-chip.enemy .unit-hp b { background: var(--autumn); }
@media (prefers-reduced-motion: reduce) {
  .unit-chip.active { transform: none; }
}
</style>

<style>
.unit-tip {
  position: fixed;
  z-index: 70;
  display: grid;
  gap: 3px;
  min-width: 120px;
  max-width: 220px;
  padding: 9px 11px;
  color: var(--cream);
  border: 1px solid var(--line);
  border-left: 2px solid var(--leaf-bright);
  border-radius: 4px 12px 4px 12px;
  background: #16201a;
  box-shadow: 0 18px 44px #0009;
  font-size: 12px;
  line-height: 1.5;
  pointer-events: none;
}
.unit-tip.enemy { border-left-color: var(--autumn); }
.unit-tip strong { font-size: 13px; }
.unit-tip .tip-muted { color: #7f8a80; }
</style>
