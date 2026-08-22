<script setup lang="ts">
import { Archive, PackageOpen } from 'lucide-vue-next'

import GameIcon from '@/components/GameIcon.vue'
import { useGameStore } from '@/stores/game'

const game = useGameStore()
</script>

<template>
  <section class="view-section" v-if="game.state">
    <header class="view-heading">
      <div>
        <p class="eyebrow">TOWN BARN</p>
        <h1>仓库</h1>
        <p>种子和收获物都保存在这里。出售农产品，为下一轮生产积累资金。</p>
      </div>
      <div class="season-chip"><Archive :size="18" /> {{ game.state.inventory.length }} 类物品</div>
    </header>

    <div v-if="!game.state.inventory.length" class="empty-state">
      <PackageOpen :size="42" />
      <h2>仓库还是空的</h2>
      <p>购买种子、完成种植后，收获物会出现在这里。</p>
      <RouterLink class="primary-button" to="/shop">去买种子</RouterLink>
    </div>

    <div v-else class="inventory-list">
      <article v-for="item in game.state.inventory" :key="item.inventory_key" class="inventory-row" :class="item.quality ? `quality-${item.quality}` : ''">
        <div class="item-icon item-icon--small"><GameIcon :name="item.icon" :size="26" /></div>
        <div class="inventory-copy">
          <h2>{{ item.name }} <em v-if="item.quality" class="quality-label">{{ item.quality_name }}</em></h2>
          <span>{{ item.kind === 'seed' ? '种植用种子' : `收购价 ${item.sell_price} 金币${item.quality_sale_multiplier > 1 ? ` · ${item.quality_sale_multiplier}×` : ''}` }}</span>
        </div>
        <strong class="quantity">× {{ item.quantity }}</strong>
        <div v-if="item.sell_price" class="row-actions">
          <button class="text-button" :disabled="game.busy" @click="game.sell(item.item_id, 1, item.quality)">出售 1 个</button>
          <button class="primary-button" :disabled="game.busy" @click="game.sell(item.item_id, item.quantity, item.quality)">全部出售</button>
        </div>
      </article>
    </div>
  </section>
</template>
