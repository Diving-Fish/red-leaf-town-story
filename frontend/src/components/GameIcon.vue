<script setup lang="ts">
import { Carrot, CookingPot, FlaskConical, Leaf, Package, PanelsTopLeft, Sprout, Trees, Wheat } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{ name?: string; size?: number }>()
const icons = { carrot: Carrot, 'cooking-pot': CookingPot, 'flask-conical': FlaskConical, leaf: Leaf, package: Package, 'panels-top-left': PanelsTopLeft, sprout: Sprout, trees: Trees, wheat: Wheat }
const component = computed(() => icons[props.name as keyof typeof icons] || Package)
</script>

<template>
  <component :is="component" :size="size || 24" stroke-width="1.8" />
</template>
