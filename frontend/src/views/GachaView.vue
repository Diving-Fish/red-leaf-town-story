<script setup lang="ts">
import { computed, ref } from 'vue'
import { Flame, Leaf, Sparkles, Stamp, Star } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import PartnerAvatar from '@/components/PartnerAvatar.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { useGameStore } from '@/stores/game'
import type { GachaDrop } from '@/types'

const game = useGameStore()
const results = ref<GachaDrop[]>([])
const gacha = computed(() => game.state?.gacha)

function partner(drop: GachaDrop) {
  return gacha.value?.catalog.find((entry) => entry.partner_id === drop.content_id)
}

function taskItem(drop: GachaDrop) {
  return gacha.value?.task_items.find((entry) => entry.id === drop.content_id)
}

async function pull(count: 1 | 10) {
  const outcome = await game.recruit(count)
  if (outcome) results.value = outcome.results
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

      <article class="gacha-banner">
        <div>
          <p class="eyebrow">{{ gacha.pool_id }}</p>
          <h2>把点亮的红叶送进裂口</h2>
          <p>伙伴与只在招募中出现的特殊工作道具，都可能从另一边回应。</p>
          <div class="pity-row">
            <span>至多 {{ gacha.pulls_until_four_star }} 抽出现 4★+</span>
            <span>至多 {{ gacha.pulls_until_five_star }} 抽出现 5★</span>
          </div>
        </div>
        <div class="pull-actions">
          <ActionButton action-key="gacha:single" :disabled="(game.player?.guide_leaves || 0) < 1" reason="引路枫叶不足" @click="pull(1)">
            单次招募 · 1 片
          </ActionButton>
          <ActionButton action-key="gacha:ten" :disabled="(game.player?.guide_leaves || 0) < 10" reason="引路枫叶不足" @click="pull(10)">
            十次招募 · 10 片
          </ActionButton>
        </div>
      </article>

      <div v-if="results.length" class="pull-results">
        <article v-for="(drop, index) in results" :key="`${index}:${drop.content_id}`" :class="[`drop-${drop.rarity || 'item'}`]">
          <template v-if="drop.kind === 'partner'">
            <PartnerAvatar :artwork="partner(drop)?.artwork" :crop="partner(drop)?.avatar_crop" :name="partner(drop)?.name || drop.content_id" :size="64" />
            <strong>{{ partner(drop)?.name || drop.content_id }}</strong>
            <span><Star v-for="star in drop.rarity || 0" :key="star" :size="12" fill="currentColor" /></span>
            <small v-if="drop.duplicate">已同行 · 印记 +{{ drop.companion_marks }}</small>
            <small v-else>新伙伴</small>
          </template>
          <template v-else>
            <Sparkles :size="42" />
            <strong>{{ taskItem(drop)?.name || drop.content_id }}</strong>
            <small>特殊道具 ×{{ drop.quantity }}</small>
          </template>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.gacha-wallet { display: grid; grid-template-columns: repeat(3, minmax(130px, 1fr)) auto; gap: 9px; margin-bottom: 14px; }.gacha-wallet > span { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 8px; padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: var(--surface); }.gacha-wallet svg { color: var(--gold); }.gacha-wallet small { color: #849087; }.gacha-banner { min-height: 310px; display: grid; grid-template-columns: 1fr auto; align-items: end; gap: 30px; padding: clamp(24px, 5vw, 58px); border: 1px solid #d8b76b33; border-radius: 28px 8px; background: radial-gradient(circle at 75% 25%, #d3a64a2b, transparent 34%), linear-gradient(135deg, #1f2c23, #111914); }.gacha-banner h2 { max-width: 620px; margin: 8px 0; font: 700 clamp(2rem, 5vw, 4rem) Georgia, 'Noto Serif SC', serif; }.gacha-banner p { color: #9aa69c; }.pity-row { display: flex; flex-wrap: wrap; gap: 8px; }.pity-row span { padding: 5px 8px; color: #c6b488; font-size: 12px; border-radius: 99px; background: #d7b46b12; }.pull-actions { min-width: 190px; display: grid; gap: 9px; }.pull-results { display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 8px; margin-top: 14px; }.pull-results article { min-height: 160px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; padding: 12px; text-align: center; border: 1px solid var(--line); border-radius: 15px 5px; background: #141d18; }.pull-results article > span { display: flex; color: var(--gold); }.pull-results small { color: #849087; }.pull-results .drop-5 { border-color: #d9b65c88; background: linear-gradient(145deg, #3a2b19, #171d17); }.pull-results .drop-4 { border-color: #9b82d866; background: linear-gradient(145deg, #28223b, #171d17); }
@media (max-width: 800px) { .gacha-wallet { grid-template-columns: 1fr 1fr; }.gacha-banner { grid-template-columns: 1fr; }.pull-results { grid-template-columns: repeat(2, 1fr); } }
</style>
