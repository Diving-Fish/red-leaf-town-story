<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { PackageOpen, Search, Store } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'

import ActionButton from '@/components/ActionButton.vue'
import MarketItem from '@/components/MarketItem.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { itemKindName } from '@/lib/items'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { InventoryItem, ShopEntry } from '@/types'

interface SellGroup {
  itemId: string
  name: string
  icon: string
  kind: string
  quantity: number
  value: number
  buckets: InventoryItem[]
}

type MarketTab = 'buy' | 'sell'

const TOOLBAR_THRESHOLD = 6

const game = useGameStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()

const tab = ref<MarketTab>(route.query.tab === 'sell' ? 'sell' : 'buy')
const buyKeyword = ref('')
const buyKind = ref('all')
const sellKeyword = ref('')
const sellKind = ref('all')
const expandedItems = ref<string[]>([])

const coins = computed(() => game.player?.coins || 0)
const shopEntries = computed(() => game.state?.shop || [])

const sellGroups = computed<SellGroup[]>(() => {
  const groups = new Map<string, SellGroup>()
  for (const item of game.state?.inventory || []) {
    let group = groups.get(item.item_id)
    if (!group) {
      group = { itemId: item.item_id, name: item.name, icon: item.icon, kind: item.kind, quantity: 0, value: 0, buckets: [] }
      groups.set(item.item_id, group)
    }
    group.quantity += item.quantity
    group.value += item.sell_price * item.quantity
    group.buckets.push(item)
  }
  for (const group of groups.values()) group.buckets.sort((left, right) => (right.quality || 0) - (left.quality || 0))
  return [...groups.values()]
})

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

function selectTab(value: MarketTab) {
  tab.value = value
  router.replace({ query: value === 'sell' ? { tab: 'sell' } : {} })
}

function expanded(itemId: string) {
  return expandedItems.value.includes(itemId)
}

function toggleGroup(itemId: string) {
  const index = expandedItems.value.indexOf(itemId)
  if (index >= 0) expandedItems.value.splice(index, 1)
  else expandedItems.value.push(itemId)
}

function affordable(entry: ShopEntry, quantity: number) {
  return coins.value >= entry.price * quantity
}

function buyReason(entry: ShopEntry, quantity: number) {
  if (entry.locked) return `等级 ${entry.min_level} 解锁`
  if (!affordable(entry, quantity)) return '金币不足'
  return undefined
}

function buyMeta(entry: ShopEntry) {
  if (entry.locked) return `等级 ${entry.min_level} 解锁`
  return `仓库中有 ${game.inventoryMap.get(entry.item_id)?.quantity || 0} 包`
}

function bucketMeta(item: InventoryItem) {
  if (!item.sell_price) return '种植用种子'
  const bonus = item.quality_sale_multiplier > 1 ? ` · ${item.quality_sale_multiplier}×` : ''
  return `收购价 ${item.sell_price} 金币${bonus}`
}

function groupMeta(group: SellGroup) {
  return `${group.buckets.length} 种品质 · 合计 ${group.value} 金币`
}

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

        <div class="market-list">
          <MarketItem
            v-for="entry in visibleShop"
            :key="entry.id"
            :icon="entry.item.icon"
            :name="entry.item.name"
            :meta="buyMeta(entry)"
            :amount="entry.price"
            amount-unit="金币"
            :locked="entry.locked"
          >
            <template #actions>
              <ActionButton
                variant="text"
                :action-key="`shop:${entry.id}:5`"
                :group="`shop:${entry.id}`"
                :disabled="entry.locked || !affordable(entry, 5)"
                :reason="buyReason(entry, 5)"
                @click="game.buy(entry.id, 5)"
              >买 5 包</ActionButton>
              <ActionButton
                :action-key="`shop:${entry.id}:1`"
                :group="`shop:${entry.id}`"
                :disabled="entry.locked || !affordable(entry, 1)"
                :reason="buyReason(entry, 1)"
                @click="game.buy(entry.id, 1)"
              >购买</ActionButton>
            </template>
          </MarketItem>

          <StateBlock
            v-if="!visibleShop.length"
            variant="inline"
            :icon="Store"
            :title="shopEntries.length ? '没有符合条件的商品' : '今天没有可以买的东西'"
          />
        </div>
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

        <div class="market-list">
          <template v-for="group in visibleSell" :key="group.itemId">
            <MarketItem
              v-if="group.buckets.length === 1"
              :icon="group.icon"
              :name="group.name"
              :quality="group.buckets[0].quality"
              :quality-name="group.buckets[0].quality_name"
              :meta="bucketMeta(group.buckets[0])"
              :amount="`×${group.quantity}`"
            >
              <template v-if="group.buckets[0].sell_price" #actions>
                <ActionButton
                  variant="text"
                  :action-key="`inventory:${group.itemId}:${group.buckets[0].quality || 0}:1`"
                  :group="`inventory:${group.itemId}:${group.buckets[0].quality || 0}`"
                  @click="game.sell(group.itemId, 1, group.buckets[0].quality)"
                >出售 1 个</ActionButton>
                <ActionButton
                  :action-key="`inventory:${group.itemId}:${group.buckets[0].quality || 0}:${group.quantity}`"
                  :group="`inventory:${group.itemId}:${group.buckets[0].quality || 0}`"
                  @click="sellAll(group.buckets[0])"
                >全部出售</ActionButton>
              </template>
            </MarketItem>

            <template v-else>
              <MarketItem
                expandable
                :expanded="expanded(group.itemId)"
                :icon="group.icon"
                :name="group.name"
                :meta="groupMeta(group)"
                :amount="`×${group.quantity}`"
                @toggle="toggleGroup(group.itemId)"
              />
              <div v-if="expanded(group.itemId)" class="market-buckets">
                <MarketItem
                  v-for="bucket in group.buckets"
                  :key="bucket.inventory_key"
                  nested
                  :icon="bucket.icon"
                  :name="bucket.name"
                  :quality="bucket.quality"
                  :quality-name="bucket.quality_name"
                  :meta="bucketMeta(bucket)"
                  :amount="`×${bucket.quantity}`"
                >
                  <template v-if="bucket.sell_price" #actions>
                    <ActionButton
                      variant="text"
                      :action-key="`inventory:${bucket.item_id}:${bucket.quality || 0}:1`"
                      :group="`inventory:${bucket.item_id}:${bucket.quality || 0}`"
                      @click="game.sell(bucket.item_id, 1, bucket.quality)"
                    >出售 1 个</ActionButton>
                    <ActionButton
                      :action-key="`inventory:${bucket.item_id}:${bucket.quality || 0}:${bucket.quantity}`"
                      :group="`inventory:${bucket.item_id}:${bucket.quality || 0}`"
                      @click="sellAll(bucket)"
                    >全部出售</ActionButton>
                  </template>
                </MarketItem>
              </div>
            </template>
          </template>

          <StateBlock
            v-if="!visibleSell.length"
            variant="inline"
            :icon="PackageOpen"
            :title="sellGroups.length ? '没有符合条件的物品' : '仓库还是空的'"
          />
        </div>
      </section>
    </div>
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
.market-list { display: grid; gap: 10px; align-content: start; }
.market-buckets { display: grid; gap: 6px; margin: -4px 0 4px; padding: 8px 10px 10px; border: 1px solid var(--line); border-top: 0; border-radius: 0 0 13px 13px; background: #0d1310a8; }
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
