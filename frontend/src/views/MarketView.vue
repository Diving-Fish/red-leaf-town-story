<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { PackageOpen, Search, Store } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'

import BuyItemDialog from '@/components/BuyItemDialog.vue'
import ItemGridTile from '@/components/ItemGridTile.vue'
import SellItemDialog from '@/components/SellItemDialog.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { groupInventory, itemKindName } from '@/lib/items'
import { qualityName } from '@/lib/quality'
import { useGameStore } from '@/stores/game'
import type { InventoryItem, ShopEntry } from '@/types'

type MarketTab = 'buy' | 'sell'

const TOOLBAR_THRESHOLD = 6

const game = useGameStore()
const route = useRoute()
const router = useRouter()

const tab = ref<MarketTab>(route.query.tab === 'sell' ? 'sell' : 'buy')
const buyKeyword = ref('')
const buyKind = ref('all')
const sellKeyword = ref('')
const sellKind = ref('all')
const buyTargetId = ref('')
const sellTargetId = ref('')

const coins = computed(() => game.player?.coins || 0)
const shopEntries = computed(() => game.state?.shop || [])
const sellGroups = computed(() => groupInventory(game.state?.inventory || []))

const buyKinds = computed(() => [...new Set(shopEntries.value.map((entry) => entry.item.kind))])
const sellKinds = computed(() => [...new Set(sellGroups.value.map((group) => group.kind))])

const showBuyToolbar = computed(() => shopEntries.value.length > TOOLBAR_THRESHOLD || buyKinds.value.length > 1)
const showSellToolbar = computed(() => sellGroups.value.length > TOOLBAR_THRESHOLD || sellKinds.value.length > 1)

function matches(name: string, keyword: string) {
  const text = keyword.trim().toLowerCase()
  return !text || name.toLowerCase().includes(text)
}

const visibleShop = computed(() =>
  shopEntries.value.filter(
    (entry) => (buyKind.value === 'all' || entry.item.kind === buyKind.value) && matches(entry.item.name, buyKeyword.value),
  ),
)

const visibleSell = computed(() =>
  sellGroups.value.filter(
    (group) => (sellKind.value === 'all' || group.kind === sellKind.value) && matches(group.name, sellKeyword.value),
  ),
)

const buyTarget = computed(() => shopEntries.value.find((entry) => entry.id === buyTargetId.value) || null)
const sellTarget = computed(() => sellGroups.value.find((group) => group.itemId === sellTargetId.value) || null)

watch(
  () => route.query.tab,
  (value) => (tab.value = value === 'sell' ? 'sell' : 'buy'),
)

watch(buyKinds, (kinds) => {
  if (buyKind.value !== 'all' && !kinds.includes(buyKind.value)) buyKind.value = 'all'
})
watch(sellKinds, (kinds) => {
  if (sellKind.value !== 'all' && !kinds.includes(sellKind.value)) sellKind.value = 'all'
})
// 卖光最后一件时分组会消失，顺手把详情弹窗收起来。
watch(sellTarget, (group) => {
  if (!group) sellTargetId.value = ''
})

function selectTab(value: MarketTab) {
  tab.value = value
  router.replace({ query: value === 'sell' ? { tab: 'sell' } : {} })
}

function affordable(entry: ShopEntry) {
  return coins.value >= entry.price
}

function ownedCount(entry: ShopEntry) {
  return game.inventoryMap.get(entry.item_id)?.quantity || 0
}

function bucketLabel(bucket: InventoryItem) {
  return bucket.quality_name || qualityName(bucket.quality, '无品质')
}
</script>

<template>
  <section v-if="game.state" class="view-section">
    <ViewHeader eyebrow="TOWN MARKET" title="商店">
      <template #chip><Store :size="18" /> 今日营业中</template>
    </ViewHeader>

    <div class="market-tabs">
      <button :class="{ active: tab === 'buy' }" @click="selectTab('buy')">购买</button>
      <button :class="{ active: tab === 'sell' }" @click="selectTab('sell')">出售</button>
    </div>

    <div class="market-columns" :data-tab="tab">
      <section class="market-column market-column--buy">
        <div class="market-toolbar" :class="{ 'toolbar-quiet': !showBuyToolbar }">
          <h2>购买</h2>
          <template v-if="showBuyToolbar">
            <label class="search-field">
              <Search :size="15" />
              <input v-model="buyKeyword" type="search" placeholder="搜索商品" />
            </label>
            <div v-if="buyKinds.length > 1" class="filter-row">
              <button class="filter-chip" :class="{ active: buyKind === 'all' }" @click="buyKind = 'all'">全部</button>
              <button
                v-for="kind in buyKinds"
                :key="kind"
                class="filter-chip"
                :class="{ active: buyKind === kind }"
                @click="buyKind = kind"
              >{{ itemKindName(kind) }}</button>
            </div>
          </template>
        </div>

        <div v-if="visibleShop.length" class="item-grid">
          <ItemGridTile
            v-for="entry in visibleShop"
            :key="entry.id"
            :icon="entry.item.icon"
            :name="entry.item.name"
            :badge="entry.price"
            :locked="entry.locked"
            :dimmed="!entry.locked && !affordable(entry)"
            @click="buyTargetId = entry.id"
          >
            <template #tooltip>
              <strong>{{ entry.item.name }}</strong>
              <span class="tip-muted">{{ itemKindName(entry.item.kind) }}</span>
              <div class="tip-divider" />
              <div class="tip-row"><span class="tip-muted">单价</span><span class="tip-total">{{ entry.price }} 金币</span></div>
              <div class="tip-row"><span class="tip-muted">仓库中有</span><span>{{ ownedCount(entry) }} 个</span></div>
              <span v-if="entry.locked" class="tip-muted">等级 {{ entry.min_level }} 解锁</span>
              <span v-else-if="!affordable(entry)" class="tip-muted">金币不足</span>
            </template>
          </ItemGridTile>
        </div>

        <StateBlock
          v-else
          variant="inline"
          :icon="Store"
          :title="shopEntries.length ? '没有符合条件的商品' : '今天没有可以买的东西'"
        />
      </section>

      <section class="market-column market-column--sell">
        <div class="market-toolbar" :class="{ 'toolbar-quiet': !showSellToolbar }">
          <h2>出售</h2>
          <template v-if="showSellToolbar">
            <label class="search-field">
              <Search :size="15" />
              <input v-model="sellKeyword" type="search" placeholder="搜索物品" />
            </label>
            <div v-if="sellKinds.length > 1" class="filter-row">
              <button class="filter-chip" :class="{ active: sellKind === 'all' }" @click="sellKind = 'all'">全部</button>
              <button
                v-for="kind in sellKinds"
                :key="kind"
                class="filter-chip"
                :class="{ active: sellKind === kind }"
                @click="sellKind = kind"
              >{{ itemKindName(kind) }}</button>
            </div>
          </template>
        </div>

        <div v-if="visibleSell.length" class="item-grid">
          <ItemGridTile
            v-for="group in visibleSell"
            :key="group.itemId"
            :icon="group.icon"
            :name="group.name"
            :quality="group.topQuality"
            :badge="`×${group.quantity}`"
            @click="sellTargetId = group.itemId"
          >
            <template #tooltip>
              <strong>{{ group.name }}</strong>
              <span class="tip-muted">{{ itemKindName(group.kind) }} · {{ group.buckets.length }} 种品质</span>
              <div class="tip-divider" />
              <div v-for="bucket in group.buckets" :key="bucket.inventory_key" class="tip-row">
                <span :class="`quality-tone-${bucket.quality || 1}`">{{ bucketLabel(bucket) }}</span>
                <span>×{{ bucket.quantity }}</span>
              </div>
              <div class="tip-divider" />
              <div class="tip-row">
                <span class="tip-muted">总收购价</span>
                <span v-if="group.sellable" class="tip-total">{{ group.value }} 金币</span>
                <span v-else class="tip-muted">不可出售</span>
              </div>
            </template>
          </ItemGridTile>
        </div>

        <StateBlock
          v-else
          variant="inline"
          :icon="PackageOpen"
          :title="sellGroups.length ? '没有符合条件的物品' : '仓库还是空的'"
        />
      </section>
    </div>

    <BuyItemDialog :open="Boolean(buyTarget)" :entry="buyTarget" @close="buyTargetId = ''" />
    <SellItemDialog :open="Boolean(sellTarget)" :group="sellTarget" @close="sellTargetId = ''" />
  </section>
</template>

<style scoped>
.market-tabs { display: none; }
.market-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; align-items: start; }
.market-column { display: grid; gap: 12px; }
.market-toolbar {
  position: sticky;
  top: 0;
  z-index: 5;
  display: grid;
  gap: 9px;
  padding: 4px 0 10px;
  background: rgba(16, 23, 19, .88);
  backdrop-filter: blur(10px);
}
.market-toolbar h2 { margin: 0; font: 600 18px Georgia, 'Noto Serif SC', serif; }
.search-field { display: flex; align-items: center; gap: 8px; padding: 0 11px; color: #7f8a80; border: 1px solid var(--line); border-radius: 10px; background: #0f1712; }
.search-field input { flex: 1; min-width: 0; height: 36px; color: var(--cream); border: 0; background: transparent; outline: none; }
.filter-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.filter-chip { min-height: 28px; padding: 0 11px; color: #93a094; border: 1px solid var(--line); border-radius: 99px; background: #ffffff05; cursor: pointer; }
.filter-chip.active { color: #16210f; font-weight: 700; border-color: transparent; background: var(--leaf-bright); }
.item-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(76px, 1fr)); gap: 10px; align-content: start; }
.quality-tone-1 { color: var(--quality-1); }
.quality-tone-2 { color: var(--quality-2); }
.quality-tone-3 { color: var(--quality-3); }
.quality-tone-4 { color: var(--quality-4); }
.quality-tone-5 { color: var(--quality-5); }
@media (max-width: 900px) {
  .market-tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 16px; padding: 5px; border: 1px solid var(--line); border-radius: 12px; background: #ffffff05; }
  .market-tabs button { min-height: 38px; color: #93a094; border: 0; border-radius: 9px; background: transparent; cursor: pointer; }
  .market-tabs button.active { color: #16210f; font-weight: 700; background: var(--leaf-bright); }
  .market-columns { grid-template-columns: 1fr; }
  .market-toolbar h2 { display: none; }
  .market-toolbar.toolbar-quiet { display: none; }
  .market-columns[data-tab='buy'] .market-column--sell { display: none; }
  .market-columns[data-tab='sell'] .market-column--buy { display: none; }
}
</style>
