<script setup lang="ts">
import { Bean, Carrot, Citrus, CookingPot, Droplets, FlaskConical, Flower2, Gem, Leaf, Package, PanelsTopLeft, Pickaxe, Shell, Sprout, Trees, Vegan, Wheat } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{ name?: string; size?: number }>()
const icons = { bean: Bean, carrot: Carrot, citrus: Citrus, 'cooking-pot': CookingPot, droplets: Droplets, 'flask-conical': FlaskConical, 'flower-2': Flower2, gem: Gem, leaf: Leaf, package: Package, 'panels-top-left': PanelsTopLeft, pickaxe: Pickaxe, shell: Shell, sprout: Sprout, trees: Trees, vegan: Vegan, wheat: Wheat }
const component = computed(() => icons[props.name as keyof typeof icons] || Package)
</script>

<template>
  <component :is="component" :size="size || 24" stroke-width="1.8" />
</template>
