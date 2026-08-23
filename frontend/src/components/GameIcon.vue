<script setup lang="ts">
import { Bean, Carrot, Citrus, CookingPot, FlaskConical, Gem, Leaf, Package, PanelsTopLeft, Pickaxe, Sprout, Trees, Vegan, Wheat } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{ name?: string; size?: number }>()
const icons = { bean: Bean, carrot: Carrot, citrus: Citrus, 'cooking-pot': CookingPot, 'flask-conical': FlaskConical, gem: Gem, leaf: Leaf, package: Package, 'panels-top-left': PanelsTopLeft, pickaxe: Pickaxe, sprout: Sprout, trees: Trees, vegan: Vegan, wheat: Wheat }
const component = computed(() => icons[props.name as keyof typeof icons] || Package)
</script>

<template>
  <component :is="component" :size="size || 24" stroke-width="1.8" />
</template>
