<script setup lang="ts">
import { Carrot, Leaf, Package, Sprout, Trees, Wheat } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{ name?: string; size?: number }>()
const icons = { carrot: Carrot, leaf: Leaf, package: Package, sprout: Sprout, trees: Trees, wheat: Wheat }
const component = computed(() => icons[props.name as keyof typeof icons] || Package)
</script>

<template>
  <component :is="component" :size="size || 24" stroke-width="1.8" />
</template>
