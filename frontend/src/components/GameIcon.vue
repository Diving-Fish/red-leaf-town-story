<script setup lang="ts">
import { Bean, Beef, Bird, Carrot, Citrus, CookingPot, Droplet, Droplets, Egg, EggFried, Fish, FishSymbol, FlaskConical, Flower2, Gem, GlassWater, LampDesk, Leaf, Milk, Package, PackageCheck, PanelsTopLeft, Pickaxe, Repeat2, Shell, Sprout, Ticket, Trees, Vegan, Waves, Wheat, Wind } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{ name?: string; size?: number }>()
const icons = { bean: Bean, beef: Beef, bird: Bird, carrot: Carrot, citrus: Citrus, 'cooking-pot': CookingPot, droplet: Droplet, droplets: Droplets, fish: Fish, 'fish-symbol': FishSymbol, egg: Egg, 'egg-fried': EggFried, 'flask-conical': FlaskConical, 'flower-2': Flower2, gem: Gem, 'glass-water': GlassWater, 'lamp-desk': LampDesk, leaf: Leaf, milk: Milk, package: Package, 'package-check': PackageCheck, 'panels-top-left': PanelsTopLeft, pickaxe: Pickaxe, 'repeat-2': Repeat2, shell: Shell, sprout: Sprout, ticket: Ticket, trees: Trees, vegan: Vegan, waves: Waves, wheat: Wheat, wind: Wind }
const component = computed(() => icons[props.name as keyof typeof icons] || Package)
</script>

<template>
  <component :is="component" :size="size || 24" stroke-width="1.8" />
</template>
