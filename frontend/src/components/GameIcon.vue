<script setup lang="ts">
import { Carrot, Package, Sprout, Wheat } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{ name?: string; size?: number }>()
const icons = { carrot: Carrot, package: Package, sprout: Sprout, wheat: Wheat }
const component = computed(() => icons[props.name as keyof typeof icons] || Package)
</script>

<template>
  <component :is="component" :size="size || 24" stroke-width="1.8" />
</template>
