<script setup lang="ts">
import { BatteryCharging, Coins } from 'lucide-vue-next'

withDefaults(defineProps<{ kind: 'coins' | 'stamina'; amount: number; affordable?: boolean; signed?: boolean }>(), {
  affordable: true,
  signed: false,
})
</script>

<template>
  <span class="cost-chip" :class="{ short: !affordable }">
    <component :is="kind === 'coins' ? Coins : BatteryCharging" :size="13" />
    {{ signed ? '-' : '' }}{{ amount }}
  </span>
</template>

<style scoped>
.cost-chip { display: inline-flex; align-items: center; gap: 3px; color: #8b9689; font-size: 12px; white-space: nowrap; }
.cost-chip.short { color: var(--danger); }
</style>
