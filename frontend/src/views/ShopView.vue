<script setup lang="ts">
import { LockKeyhole, ShoppingBasket } from 'lucide-vue-next'

import GameIcon from '@/components/GameIcon.vue'
import { useGameStore } from '@/stores/game'

const game = useGameStore()
</script>

<template>
  <section class="view-section" v-if="game.state">
    <header class="view-heading">
      <div>
        <p class="eyebrow">MAPLE SEED CO.</p>
        <h1>种子商店</h1>
        <p>精选当季种子，收获后可以在仓库出售农产品。</p>
      </div>
      <div class="season-chip"><ShoppingBasket :size="18" /> 今日营业中</div>
    </header>

    <div class="catalog-grid">
      <article v-for="entry in game.state.shop" :key="entry.id" class="catalog-card" :class="{ locked: entry.locked }">
        <div class="item-icon"><GameIcon :name="entry.item.icon" :size="34" /></div>
        <div class="catalog-copy">
          <small>种子</small>
          <h2>{{ entry.item.name }}</h2>
          <p v-if="entry.locked"><LockKeyhole :size="14" /> 等级 {{ entry.min_level }} 解锁</p>
          <p v-else>仓库中有 {{ game.inventoryMap.get(entry.item_id)?.quantity || 0 }} 包</p>
        </div>
        <div class="catalog-buy">
          <strong>{{ entry.price }} <small>金币</small></strong>
          <button class="primary-button" :disabled="entry.locked || game.busy" @click="game.buy(entry.id, 1)">购买</button>
          <button class="text-button" :disabled="entry.locked || game.busy" @click="game.buy(entry.id, 5)">买 5 包</button>
        </div>
      </article>
    </div>
  </section>
</template>
