<script setup lang="ts">
import { computed } from 'vue'
import { LockKeyhole, ShoppingBasket } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import ItemTile from '@/components/ItemTile.vue'
import TipCard from '@/components/TipCard.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { useGameStore } from '@/stores/game'
import type { ShopEntry } from '@/types'

const game = useGameStore()

const coins = computed(() => game.player?.coins || 0)

function affordable(entry: ShopEntry, quantity: number) {
  return coins.value >= entry.price * quantity
}

function reason(entry: ShopEntry, quantity: number) {
  if (entry.locked) return `等级 ${entry.min_level} 解锁`
  if (!affordable(entry, quantity)) return '金币不足'
  return undefined
}
</script>

<template>
  <section v-if="game.state" class="view-section">
    <ViewHeader eyebrow="MAPLE SEED CO." title="种子商店" description="精选当季种子，收获后可以在仓库出售农产品。">
      <template #chip><ShoppingBasket :size="18" /> 今日营业中</template>
    </ViewHeader>

    <TipCard text="买好种子就可以回农场开工了。" to="/farm" action-label="回农场种植" />

    <div class="catalog-grid">
      <article v-for="entry in game.state.shop" :key="entry.id" class="catalog-card" :class="{ locked: entry.locked }">
        <ItemTile :icon="entry.item.icon" :size="66" tone="gold" />
        <div class="catalog-copy">
          <small>种子</small>
          <h2>{{ entry.item.name }}</h2>
          <p v-if="entry.locked"><LockKeyhole :size="14" /> 等级 {{ entry.min_level }} 解锁</p>
          <p v-else>仓库中有 {{ game.inventoryMap.get(entry.item_id)?.quantity || 0 }} 包</p>
        </div>
        <div class="catalog-buy">
          <strong>{{ entry.price }} <small>金币</small></strong>
          <ActionButton
            :action-key="`shop:${entry.id}:1`"
            :group="`shop:${entry.id}`"
            :disabled="entry.locked || !affordable(entry, 1)"
            :reason="reason(entry, 1)"
            @click="game.buy(entry.id, 1)"
          >购买</ActionButton>
          <ActionButton
            variant="text"
            :action-key="`shop:${entry.id}:5`"
            :group="`shop:${entry.id}`"
            :disabled="entry.locked || !affordable(entry, 5)"
            :reason="reason(entry, 5)"
            @click="game.buy(entry.id, 5)"
          >买 5 包</ActionButton>
        </div>
      </article>
    </div>
  </section>
</template>
