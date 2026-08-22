<script setup lang="ts">
import { computed } from 'vue'

import GameIcon from '@/components/GameIcon.vue'

const props = withDefaults(
  defineProps<{ icon?: string; size?: number; iconSize?: number; accent?: string; tone?: 'accent' | 'gold' | 'plain' }>(),
  { size: 44, tone: 'accent' },
)

const accentColor = computed(() => {
  if (props.tone === 'gold') return 'var(--gold)'
  if (props.tone === 'plain') return '#9eaf91'
  return props.accent || 'var(--industry-accent, #78906d)'
})
const tint = computed(() => (props.tone === 'plain' ? '#ffffff08' : `color-mix(in srgb, ${accentColor.value} 13%, transparent)`))
const radius = computed(() => `${Math.round(props.size * 0.28)}px ${Math.round(props.size * 0.09)}px`)
</script>

<template>
  <span
    class="item-tile"
    :style="{ width: `${size}px`, height: `${size}px`, color: accentColor, background: tint, borderRadius: radius }"
  >
    <slot><GameIcon :name="icon" :size="iconSize || Math.round(size * 0.55)" /></slot>
  </span>
</template>

<style scoped>
.item-tile { flex: 0 0 auto; overflow: hidden; display: grid; place-items: center; }
</style>
