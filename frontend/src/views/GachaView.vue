<script setup lang="ts">
import { computed, ref } from 'vue'
import { Flame, Leaf, Sparkles, Stamp } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import GachaConvertDialog from '@/components/gacha/GachaConvertDialog.vue'
import GachaPoolSidebar from '@/components/gacha/GachaPoolSidebar.vue'
import type { GachaPoolSummary } from '@/components/gacha/GachaPoolCard.vue'
import GachaPoster from '@/components/gacha/GachaPoster.vue'
import GachaPullOverlay from '@/components/gacha/GachaPullOverlay.vue'
import GachaResultCard from '@/components/gacha/GachaResultCard.vue'
import type { GachaResultMeta } from '@/components/gacha/GachaResultCard.vue'
import { poolDisplayName } from '@/lib/gacha'
import { useGameStore } from '@/stores/game'
import type { GachaDrop } from '@/types'

const game = useGameStore()
const gacha = computed(() => game.state?.gacha)

const results = ref<GachaDrop[]>([])
const overlayOpen = ref(false)
const convertDialogOpen = ref(false)
const pendingPullCount = ref<1 | 10>(1)
const selectedPoolId = ref<string | null>(null)
const activePoolId = computed(() => selectedPoolId.value || gacha.value?.pool_id || '')

const pools = computed<GachaPoolSummary[]>(() => {
  if (!gacha.value) return []
  return [
    {
      id: gacha.value.pool_id,
      title: poolDisplayName(gacha.value.pool_id),
      subtitle: `${gacha.value.catalog.length} 位常驻伙伴`,
      unlocked: gacha.value.unlocked,
      fiveStarRate: `5★ ${((gacha.value.rarity_probabilities[5] || 0) * 100).toFixed(1)}%`,
    },
  ]
})

function selectPool(id: string) {
  selectedPoolId.value = id
}

const posterBackground = computed(() => {
  const catalog = gacha.value?.catalog || []
  const featured = [...catalog].sort((a, b) => b.rarity - a.rarity).find((entry) => entry.artwork?.url)
  return featured?.artwork?.url || null
})

const pityTags = computed(() => {
  if (!gacha.value) return []
  return [`至多 ${gacha.value.pulls_until_four_star} 抽出现 4★+`, `至多 ${gacha.value.pulls_until_five_star} 抽出现 5★`]
})

function recapMeta(drop: GachaDrop): GachaResultMeta {
  if (drop.kind === 'partner') {
    const entry = gacha.value?.catalog.find((item) => item.partner_id === drop.content_id)
    return { name: entry?.name || drop.content_id, rarity: drop.rarity ?? entry?.rarity ?? null, artwork: entry?.artwork, crop: entry?.avatar_crop }
  }
  const entry = gacha.value?.task_items.find((item) => item.id === drop.content_id)
  return { name: entry?.name || drop.content_id, rarity: null }
}

async function pull(count: 1 | 10) {
  if ((game.player?.guide_leaves || 0) < count) {
    pendingPullCount.value = count
    convertDialogOpen.value = true
    return
  }
  const outcome = await game.recruit(count)
  if (outcome) {
    results.value = outcome.results
    overlayOpen.value = true
  }
}

function onDialogPulled(pulled: GachaDrop[]) {
  results.value = pulled
  convertDialogOpen.value = false
  overlayOpen.value = true
}

</script>

<template>
  <section v-if="game.state && gacha" class="view-section gacha-view">
    <ViewHeader eyebrow="GUIDING LEAVES" title="异界招募">
      <template #chip><Sparkles :size="18" /> 常驻同行 {{ gacha.catalog.length }} 位</template>
    </ViewHeader>

    <StateBlock
      v-if="!gacha.unlocked"
      title="传送门还听不见你的呼唤"
      :description="`居民等级 ${gacha.min_level} 开放异界招募。`"
    />

    <template v-else>
      <div class="gacha-wallet">
        <span><Flame :size="18" /><small>枫火</small><strong>{{ game.player?.maple_flame }}</strong></span>
        <span><Leaf :size="18" /><small>引路枫叶</small><strong>{{ game.player?.guide_leaves }}</strong></span>
        <span><Stamp :size="18" /><small>同行印记</small><strong>{{ game.player?.companion_marks }}</strong></span>
        <ActionButton
          variant="secondary"
          action-key="gacha:convert:1"
          :disabled="(game.player?.maple_flame || 0) < gacha.maple_flame_per_leaf"
          reason="枫火不足"
          @click="game.convertMapleFlame(1)"
        >{{ gacha.maple_flame_per_leaf }} 枫火兑换 1 片</ActionButton>
      </div>

      <div class="gacha-layout">
        <GachaPoolSidebar :pools="pools" :active-id="activePoolId" @select="selectPool">
          <template #footer>
            <p class="pool-sidebar-note">常驻招募池不会下架，可放心攒引路枫叶。</p>
          </template>
        </GachaPoolSidebar>

        <GachaPoster
          :eyebrow="gacha.pool_id"
          title="把点亮的红叶送进裂口"
          description="伙伴与只在招募中出现的特殊工作道具，都可能从另一边回应。"
          :background-url="posterBackground"
          :pity-tags="pityTags"
        >
          <template #actions>
            <span class="poster-balance"><Leaf :size="14" />引路枫叶 ×{{ game.player?.guide_leaves || 0 }}</span>
            <ActionButton action-key="gacha:single" @click="pull(1)">单次招募 · 1 片</ActionButton>
            <ActionButton action-key="gacha:ten" @click="pull(10)">十次招募 · 10 片</ActionButton>
          </template>
        </GachaPoster>
      </div>

      <div v-if="results.length" class="gacha-recap">
        <p class="gacha-recap-heading">最近获得</p>
        <div class="gacha-recap-grid">
          <GachaResultCard
            v-for="(drop, index) in results"
            :key="`recap:${index}:${drop.content_id}`"
            :drop="drop"
            :meta="recapMeta(drop)"
            revealed
            instant
          />
        </div>
      </div>
    </template>

    <GachaPullOverlay
      :open="overlayOpen"
      :results="results"
      :catalog="gacha.catalog"
      :task-items="gacha.task_items"
      @close="overlayOpen = false"
    />
    <GachaConvertDialog
      :open="convertDialogOpen"
      :count="pendingPullCount"
      @close="convertDialogOpen = false"
      @pulled="onDialogPulled"
    />
  </section>
</template>

<style scoped>
.gacha-wallet { display: grid; grid-template-columns: repeat(3, minmax(130px, 1fr)) auto; gap: 9px; margin-bottom: 14px; }
.gacha-wallet > span { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 8px; padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }
.gacha-wallet svg { color: var(--gold); }
.gacha-wallet small { color: #849087; }

.gacha-layout { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 16px; align-items: start; }
.pool-sidebar-note { color: #7c877e; font-size: 11px; line-height: 1.6; }

.poster-balance { display: flex; align-items: center; gap: 6px; color: #c9d3c6; font-size: 12px; }
.poster-balance svg { color: var(--leaf-bright); }

.gacha-recap { margin-top: 20px; }
.gacha-recap-heading { margin: 0 0 10px; color: #77837a; font-size: 12px; font-weight: 800; letter-spacing: .12em; }
.gacha-recap-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 10px; }

@media (max-width: 900px) {
  .gacha-layout { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .gacha-wallet { grid-template-columns: 1fr 1fr; }
}
</style>
