<script setup lang="ts">
import { computed } from 'vue'

import { rarityClass, rarityMeta } from '@/lib/rarity'

const props = withDefaults(
  defineProps<{ rarity?: number | null; size?: 'xs' | 'sm' | 'md'; epithet?: boolean }>(),
  { size: 'sm', epithet: false },
)

const meta = computed(() => rarityMeta(props.rarity))
const cls = computed(() => rarityClass(props.rarity))
</script>

<template>
  <span class="rarity-badge-group" :class="`size-${size}`">
    <i class="rarity-badge" :class="cls">{{ meta.short }}</i>
    <span v-if="epithet" class="rarity-badge-copy">
      <strong>{{ meta.label }}</strong>
      <small>{{ meta.epithet }}</small>
    </span>
  </span>
</template>

<style scoped>
.rarity-badge-group { display: inline-flex; align-items: center; gap: 8px; }
.rarity-badge {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  font-style: normal;
  font-weight: 800;
  line-height: 1;
}
.rarity-badge-copy { display: grid; }
.rarity-badge-copy strong { font-size: 12px; }
.rarity-badge-copy small { margin-top: 2px; color: #8a9589; }

/* size: xs — dense list rows, simplified swatch */
.size-xs .rarity-badge { width: 16px; height: 16px; font-size: 9px; border-radius: 4px; }

/* size: sm — default, small ornamented medallion */
.size-sm .rarity-badge { width: 22px; height: 22px; font-size: 11px; }

/* size: md — hero contexts (poster corner, partner detail ribbon) */
.size-md .rarity-badge { width: 30px; height: 30px; font-size: 14px; }

/* tier 3 — quiet pill */
.rarity-badge.rarity-3 {
  border-radius: 999px;
  color: var(--rarity-3);
  border: 1px solid color-mix(in srgb, var(--rarity-3) 60%, transparent);
  background: color-mix(in srgb, var(--rarity-3) 16%, #10160f);
}

/* tier 4 — hexagon, soft arcane glow */
.rarity-badge.rarity-4 {
  clip-path: polygon(15% 0, 85% 0, 100% 50%, 85% 100%, 15% 100%, 0 50%);
  color: #f0e8ff;
  background: linear-gradient(140deg, color-mix(in srgb, var(--rarity-4) 55%, #1a1424), color-mix(in srgb, var(--rarity-4) 20%, transparent));
  box-shadow: 0 0 12px var(--rarity-4-soft);
}

/* tier 5 — eight-point starburst medallion, shimmering */
.rarity-badge.rarity-5 {
  clip-path: polygon(
    50% 0%, 63% 21%, 87% 13%, 81% 38%, 100% 50%, 81% 62%, 87% 87%, 63% 79%,
    50% 100%, 37% 79%, 13% 87%, 19% 62%, 0% 50%, 19% 38%, 13% 13%, 37% 21%
  );
  color: #2a1608;
  background: linear-gradient(135deg, var(--rarity-5-a), var(--rarity-5-b));
  box-shadow: 0 0 18px var(--rarity-5-soft);
  animation: rarity-pulse 2.4s ease-in-out infinite;
}

.size-xs .rarity-badge.rarity-4,
.size-xs .rarity-badge.rarity-5 {
  clip-path: none;
  border-radius: 5px;
}
</style>
