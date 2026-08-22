<script setup lang="ts">
import { computed } from 'vue'

import { qualityName } from '@/lib/quality'

const props = defineProps<{ quality?: number | null; name?: string | null; plain?: boolean }>()

const label = computed(() => props.name || qualityName(props.quality))
</script>

<template>
  <em v-if="label" class="quality-tag" :class="[`quality-tone-${quality || 1}`, { plain }]">{{ label }}</em>
</template>

<style scoped>
.quality-tag {
  display: inline-block;
  padding: 2px 7px;
  color: var(--quality-color, #9baa9d);
  border: 1px solid currentColor;
  border-radius: 999px;
  font-size: 12px;
  font-style: normal;
  font-weight: 600;
}
.quality-tag.plain { padding: 0; border: 0; }
.quality-tone-1 { --quality-color: var(--quality-1); }
.quality-tone-2 { --quality-color: var(--quality-2); }
.quality-tone-3 { --quality-color: var(--quality-3); }
.quality-tone-4 { --quality-color: var(--quality-4); }
.quality-tone-5 { --quality-color: var(--quality-5); }
</style>
