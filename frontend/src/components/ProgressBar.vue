<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ value: number; color?: string; track?: string; height?: number; smooth?: boolean }>(), {
  height: 6,
  smooth: false,
})

const width = computed(() => `${Math.min(100, Math.max(0, props.value))}%`)
</script>

<template>
  <div class="progress-bar" :style="{ height: `${height}px`, background: track }">
    <i :class="{ smooth }" :style="{ width, background: color || 'var(--leaf-bright)' }" />
  </div>
</template>

<style scoped>
.progress-bar { overflow: hidden; border-radius: 99px; background: #ffffff0c; }
.progress-bar i { display: block; height: 100%; border-radius: inherit; transition: width .4s ease; }
.progress-bar i.smooth { transition: width 1s linear; }
</style>
