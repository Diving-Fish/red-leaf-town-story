<script setup lang="ts">
import { Bean, Carrot, Citrus, CookingPot, Droplets, FlaskConical, Flower2, Gem, LampDesk, Leaf, Package, PanelsTopLeft, Pickaxe, Repeat2, Shell, Sprout, Trees, Vegan, Wheat, Wind } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{ name?: string; size?: number }>()
const icons = { bean: Bean, carrot: Carrot, citrus: Citrus, 'cooking-pot': CookingPot, droplets: Droplets, 'flask-conical': FlaskConical, 'flower-2': Flower2, gem: Gem, 'lamp-desk': LampDesk, leaf: Leaf, package: Package, 'panels-top-left': PanelsTopLeft, pickaxe: Pickaxe, 'repeat-2': Repeat2, shell: Shell, sprout: Sprout, trees: Trees, vegan: Vegan, wheat: Wheat, wind: Wind }
const component = computed(() => icons[props.name as keyof typeof icons] || Package)
</script>

<template>
  <component :is="component" :size="size || 24" stroke-width="1.8" />
</template>
