<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { LockKeyhole } from 'lucide-vue-next'

import GameIcon from '@/components/GameIcon.vue'
import { qualityClass } from '@/lib/quality'

const props = withDefaults(
  defineProps<{
    icon?: string
    name: string
    quality?: number | null
    badge?: string | number
    locked?: boolean
    dimmed?: boolean
  }>(),
  { locked: false, dimmed: false },
)

const emit = defineEmits<{ (event: 'click'): void }>()

const NAME_LIMIT = 4

const shortName = computed(() =>
  [...props.name].length > NAME_LIMIT ? `${[...props.name].slice(0, NAME_LIMIT).join('')}…` : props.name,
)

const root = ref<HTMLElement>()
const tip = ref<HTMLElement>()
const tipOpen = ref(false)
const tipStyle = ref<Record<string, string>>({})

function hoverCapable() {
  return typeof window !== 'undefined' && window.matchMedia('(hover: hover)').matches
}

async function onFocus(event: FocusEvent) {
  // Pointer clicks also focus the tile, and the dialog they open would sit under a lingering tooltip.
  if ((event.target as HTMLElement).matches(':focus-visible')) openTip()
}

function onClick() {
  closeTip()
  emit('click')
}

async function openTip() {
  if (!hoverCapable()) return
  tipOpen.value = true
  await nextTick()
  const anchor = root.value?.getBoundingClientRect()
  const bubble = tip.value?.getBoundingClientRect()
  if (!anchor || !bubble) return
  const left = Math.min(Math.max(8, anchor.left + anchor.width / 2 - bubble.width / 2), window.innerWidth - bubble.width - 8)
  const above = anchor.top - bubble.height - 10
  tipStyle.value = { left: `${left}px`, top: `${above < 8 ? anchor.bottom + 10 : above}px` }
}

function closeTip() {
  tipOpen.value = false
}

onBeforeUnmount(closeTip)
</script>

<template>
  <button
    ref="root"
    class="grid-tile"
    :class="[qualityClass(quality), { locked, dimmed }]"
    :title="name"
    @click="onClick"
    @mouseenter="openTip"
    @mouseleave="closeTip"
    @focus="onFocus"
    @blur="closeTip"
  >
    <span class="grid-tile-icon">
      <GameIcon :name="icon" :size="26" />
      <LockKeyhole v-if="locked" class="grid-tile-lock" :size="12" />
    </span>
    <span v-if="badge !== undefined && badge !== ''" class="grid-tile-badge">{{ badge }}</span>
    <span class="grid-tile-name">{{ shortName }}</span>

    <Teleport to="body">
      <div v-if="tipOpen && $slots.tooltip" ref="tip" class="grid-tile-tip" :style="tipStyle">
        <slot name="tooltip" />
      </div>
    </Teleport>
  </button>
</template>

<style scoped>
.grid-tile {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 7px;
  padding: 10px 5px 9px;
  color: inherit;
  border: 1px solid var(--line);
  border-radius: 15px 5px 15px 5px;
  background: var(--surface);
  cursor: pointer;
  transition: border-color .18s ease, transform .18s ease, box-shadow .18s ease;
}
.grid-tile:hover,
.grid-tile:focus-visible {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--tile-accent, var(--gold)) 45%, transparent);
  box-shadow: 0 10px 24px color-mix(in srgb, var(--tile-accent, var(--gold)) 12%, transparent);
  outline: none;
}
.grid-tile.locked { filter: saturate(.35); opacity: .62; }
.grid-tile.dimmed { opacity: .78; }

.grid-tile-icon {
  position: relative;
  width: 46px;
  height: 46px;
  display: grid;
  place-items: center;
  color: var(--tile-accent, var(--gold));
  border-radius: 13px 4px 13px 4px;
  background: color-mix(in srgb, var(--tile-accent, var(--gold)) 13%, transparent);
}
.grid-tile-lock { position: absolute; right: -3px; top: -3px; padding: 2px; color: #d8cdb4; border-radius: 50%; background: #101713; }
.grid-tile-badge {
  position: absolute;
  right: 5px;
  top: 32px;
  padding: 1px 6px;
  color: var(--tile-accent, var(--gold));
  border-radius: 999px;
  background: #0d1410;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.5;
}
.grid-tile-name {
  max-width: 100%;
  overflow: hidden;
  color: #c3ccc1;
  font-size: 12px;
  line-height: 1.3;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.grid-tile.quality-1 { --tile-accent: var(--quality-1); }
.grid-tile.quality-2 { --tile-accent: var(--quality-2); }
.grid-tile.quality-3 { --tile-accent: var(--quality-3); }
.grid-tile.quality-4 { --tile-accent: var(--quality-4); }
.grid-tile.quality-5 { --tile-accent: var(--quality-5); }
</style>

<style>
.grid-tile-tip {
  position: fixed;
  z-index: 55;
  display: grid;
  gap: 5px;
  min-width: 148px;
  max-width: 240px;
  padding: 10px 12px;
  color: var(--cream);
  border: 1px solid var(--line);
  border-radius: 13px 4px 13px 4px;
  background: #16201a;
  box-shadow: 0 18px 44px #0009;
  font-size: 12px;
  line-height: 1.5;
  pointer-events: none;
}
.grid-tile-tip strong { font-size: 13px; }
.grid-tile-tip .tip-muted { color: #7f8a80; }
.grid-tile-tip .tip-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.grid-tile-tip .tip-total { color: var(--gold); font-weight: 700; }
.grid-tile-tip .tip-divider { height: 1px; margin: 2px 0; background: var(--line); }
</style>
