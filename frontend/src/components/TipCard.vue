<script setup lang="ts">
import type { Component } from 'vue'
import { CircleHelp } from 'lucide-vue-next'

defineProps<{ icon?: Component; text?: string; to?: string; actionLabel?: string }>()
</script>

<template>
  <div class="tip-card">
    <component :is="icon || CircleHelp" :size="20" />
    <span><slot>{{ text }}</slot></span>
    <RouterLink v-if="to" :to="to">{{ actionLabel || '前往' }}</RouterLink>
  </div>
</template>
