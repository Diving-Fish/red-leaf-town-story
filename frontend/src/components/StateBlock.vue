<script setup lang="ts">
import type { Component } from 'vue'
import { Lock } from 'lucide-vue-next'

withDefaults(defineProps<{ icon?: Component; title: string; description?: string; variant?: 'panel' | 'card' | 'tile' | 'inline' }>(), {
  variant: 'panel',
})
</script>

<template>
  <div class="state-block" :class="`state-block--${variant}`">
    <component :is="icon || Lock" :size="variant === 'tile' ? 26 : 36" />
    <strong>{{ title }}</strong>
    <span v-if="description">{{ description }}</span>
    <div v-if="$slots.default" class="state-actions"><slot /></div>
  </div>
</template>

<style scoped>
.state-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 24px;
  text-align: center;
  color: #778178;
  border: 1px dashed var(--line);
  background: #12191588;
}
.state-block strong { color: #b6bfb5; font-family: Georgia, 'Noto Serif SC', serif; font-size: 17px; }
.state-block span { color: #7c8880; font-size: 13px; line-height: 1.6; max-width: 40ch; }
.state-block--panel { min-height: 330px; border-radius: 22px 7px; }
.state-block--card { min-height: 250px; border-radius: 20px 7px; }
.state-block--tile { min-height: 215px; border-radius: 22px 7px 22px 7px; background: #ffffff04; }
.state-block--tile strong { font-size: 14px; }
.state-block--inline { min-height: 66px; flex-direction: row; gap: 8px; margin-top: 12px; padding: 12px; border-radius: 10px; background: none; }
.state-block--inline strong { color: #7c8880; font-family: inherit; font-size: 12px; font-weight: 500; }
.state-actions { margin-top: 12px; }
</style>
