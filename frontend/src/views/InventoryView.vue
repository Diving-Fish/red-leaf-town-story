<script setup lang="ts">
import { Archive, PackageOpen } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import ItemTile from '@/components/ItemTile.vue'
import QualityTag from '@/components/QualityTag.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { qualityClass } from '@/lib/quality'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { InventoryItem } from '@/types'

const game = useGameStore()
const ui = useUiStore()

async function sellAll(item: InventoryItem) {
  const accepted = await ui.confirm({
    title: `出售全部${item.name}？`,
    description: `${item.quality_name || ''}${item.name} ×${item.quantity} 会一次性卖出，共 ${item.sell_price * item.quantity} 金币。出售之后无法撤销。`,
    confirmLabel: '全部出售',
    tone: 'danger',
  })
  if (accepted) game.sell(item.item_id, item.quantity, item.quality)
}
</script>

<template>
  <section v-if="game.state" class="view-section">
    <ViewHeader
      eyebrow="TOWN BARN"
      title="仓库"
      description="种子和收获物都保存在这里。出售农产品，为下一轮生产积累资金。"
    >
      <template #chip><Archive :size="18" /> {{ game.state.inventory.length }} 类物品</template>
    </ViewHeader>

    <StateBlock
      v-if="!game.state.inventory.length"
      :icon="PackageOpen"
      title="仓库还是空的"
      description="购买种子、完成种植后，收获物会出现在这里。"
    >
      <RouterLink class="primary-button" to="/shop">去买种子</RouterLink>
    </StateBlock>

    <div v-else class="inventory-list">
      <article
        v-for="item in game.state.inventory"
        :key="item.inventory_key"
        class="inventory-row"
        :class="qualityClass(item.quality)"
      >
        <ItemTile :icon="item.icon" :size="48" tone="gold" />
        <div class="inventory-copy">
          <h2>{{ item.name }} <QualityTag :quality="item.quality" :name="item.quality_name" /></h2>
          <span>
            {{ item.kind === 'seed'
              ? '种植用种子'
              : `收购价 ${item.sell_price} 金币${item.quality_sale_multiplier > 1 ? ` · ${item.quality_sale_multiplier}×` : ''}` }}
          </span>
        </div>
        <strong class="quantity">× {{ item.quantity }}</strong>
        <div v-if="item.sell_price" class="row-actions">
          <ActionButton
            variant="text"
            :action-key="`inventory:${item.item_id}:${item.quality || 0}:1`"
            :group="`inventory:${item.item_id}:${item.quality || 0}`"
            @click="game.sell(item.item_id, 1, item.quality)"
          >出售 1 个</ActionButton>
          <ActionButton
            :action-key="`inventory:${item.item_id}:${item.quality || 0}:${item.quantity}`"
            :group="`inventory:${item.item_id}:${item.quality || 0}`"
            @click="sellAll(item)"
          >全部出售</ActionButton>
        </div>
      </article>
    </div>
  </section>
</template>
