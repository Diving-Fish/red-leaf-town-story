<script setup lang="ts">
import { computed } from 'vue'

import RarityBadge from '@/components/RarityBadge.vue'
import { normalizeRarity, rarityClass } from '@/lib/rarity'

const props = withDefaults(
  defineProps<{
    rarity?: number | null
    aspect?: string
    badge?: boolean
    badgeSize?: 'xs' | 'sm' | 'md'
  }>(),
  { aspect: '3 / 4', badge: true, badgeSize: 'sm' },
)

const cls = computed(() => rarityClass(props.rarity))
const isFive = computed(() => normalizeRarity(props.rarity) === 5)
</script>

<template>
  <div class="rarity-frame" :class="cls" :style="{ aspectRatio: aspect }">
    <div class="rarity-frame-glow" />
    <div class="rarity-frame-content"><slot /></div>
    <div class="rarity-frame-sheen" />
    <template v-if="isFive">
      <span class="rarity-frame-spark s1" />
      <span class="rarity-frame-spark s2" />
      <span class="rarity-frame-spark s3" />
    </template>
    <RarityBadge v-if="badge" class="rarity-frame-badge" :rarity="rarity" :size="badgeSize" />
  </div>
</template>

<style scoped>
.rarity-frame {
  position: relative;
  overflow: hidden;
  width: 100%;
  border: 3px solid var(--line);
  border-radius: 22px 6px 22px 6px;
  background: #0d1410;
}
.rarity-frame-content { position: relative; z-index: 1; width: 100%; height: 100%; }
.rarity-frame-content :deep(img) { display: block; width: 100%; height: 100%; object-fit: cover; }
.rarity-frame-glow {
  position: absolute;
  inset: -45%;
  z-index: 0;
  opacity: .3;
  pointer-events: none;
  background: radial-gradient(circle at 50% 28%, var(--tier-glow, transparent), transparent 62%);
}
.rarity-frame-sheen { position: absolute; inset: 0; z-index: 2; pointer-events: none; mix-blend-mode: overlay; background-size: 240% 240%; }
.rarity-frame-badge { position: absolute; left: 9px; top: 9px; z-index: 3; }
.rarity-frame-spark {
  position: absolute;
  z-index: 3;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--rarity-5-a);
  box-shadow: 0 0 9px 2px var(--rarity-5-a);
  animation: twinkle 1.7s ease-in-out infinite;
}
.rarity-frame-spark.s1 { left: 16%; top: 22%; }
.rarity-frame-spark.s2 { right: 16%; top: 42%; animation-delay: .5s; }
.rarity-frame-spark.s3 { left: 34%; bottom: 18%; animation-delay: 1s; }

.rarity-frame.rarity-3 { border-color: color-mix(in srgb, var(--rarity-3) 50%, var(--line)); }
.rarity-frame.rarity-3 .rarity-frame-glow { --tier-glow: var(--rarity-3-soft); }

.rarity-frame.rarity-4 {
  border-width: 4px;
  border-color: color-mix(in srgb, var(--rarity-4) 58%, var(--line));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--rarity-4) 22%, transparent) inset, 0 14px 38px color-mix(in srgb, var(--rarity-4) 15%, transparent);
}
.rarity-frame.rarity-4 .rarity-frame-glow { --tier-glow: var(--rarity-4-soft); opacity: .4; }
.rarity-frame.rarity-4 .rarity-frame-sheen {
  background-image: linear-gradient(115deg, transparent 42%, rgba(202, 182, 255, .22) 50%, transparent 58%);
  animation: rarity-sheen 5s ease-in-out infinite;
}

.rarity-frame.rarity-5 {
  border-color: transparent;
  border-width: 5px;
  border-radius: 30px 8px 30px 8px;
  background-image: linear-gradient(#0d1410, #0d1410), linear-gradient(135deg, var(--rarity-5-a), var(--rarity-5-b));
  background-origin: border-box;
  background-clip: padding-box, border-box;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--rarity-5-a) 30%, transparent) inset, 0 20px 55px color-mix(in srgb, var(--rarity-5-b) 22%, transparent);
}
.rarity-frame.rarity-5 .rarity-frame-glow { --tier-glow: var(--rarity-5-soft); opacity: .55; animation: rarity-pulse 2.6s ease-in-out infinite; }
.rarity-frame.rarity-5 .rarity-frame-sheen {
  background-image: linear-gradient(115deg, transparent 38%, rgba(255, 235, 190, .38) 50%, transparent 62%);
  animation: rarity-sheen 3.4s ease-in-out infinite;
}
</style>
