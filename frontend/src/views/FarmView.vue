<script setup lang="ts">
import { computed } from 'vue'
import { CircleHelp, Tractor } from 'lucide-vue-next'

import FarmPlot from '@/components/FarmPlot.vue'
import { useGameStore } from '@/stores/game'

const game = useGameStore()
const availableCrops = computed(() => {
  if (!game.state) return []
  return game.state.shop
    .filter((entry) => !entry.locked && entry.crop && (game.inventoryMap.get(entry.item_id)?.quantity || 0) > 0)
    .map((entry) => entry.crop!)
})
</script>

<template>
  <section class="view-section" v-if="game.state">
    <header class="view-heading">
      <div>
        <p class="eyebrow">AUTUMN FARM</p>
        <h1>我的农场</h1>
        <p>安排具有农作倾向的伙伴驻场，可以缩短下一次种植时间。</p>
      </div>
      <div class="season-chip"><Tractor :size="18" /> 农作编制 {{ game.state.industry_rules.farming?.partner_capacity || 0 }}</div>
    </header>

    <div class="tip-card" v-if="!availableCrops.length">
      <CircleHelp :size="20" />
      <span>先去种子商店购买种子，就可以开始第一轮种植。</span>
      <RouterLink to="/shop">前往商店</RouterLink>
    </div>

    <div class="plot-grid">
      <FarmPlot
        v-for="plot in game.state.plots"
        :key="plot.slot"
        :plot="plot"
        :crops="availableCrops"
        :partners="game.state.partners"
      />
      <FarmPlot v-if="game.state.next_plot_level" :locked-level="game.state.next_plot_level" />
    </div>
  </section>
</template>
