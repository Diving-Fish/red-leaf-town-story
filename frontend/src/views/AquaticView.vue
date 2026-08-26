<script setup lang="ts">
import { computed } from 'vue'
import { Coins, Lock, Shovel, UsersRound } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import FeedSlotPanel from '@/components/aquatic/FeedSlotPanel.vue'
import FishingPanel from '@/components/aquatic/FishingPanel.vue'
import PondCard from '@/components/aquatic/PondCard.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { useGameStore } from '@/stores/game'

const game = useGameStore()

const aquatic = computed(() => game.state?.aquatic || null)
</script>

<template>
  <section v-if="game.state && aquatic" class="view-section aquatic-view">
    <ViewHeader eyebrow="WATERS AND PONDS" title="水产">
      <template #chip>
        <UsersRound :size="18" /> 水产编制 {{ game.state.industry_rules.aquatic?.partner_capacity || 0 }}
      </template>
    </ViewHeader>

    <StateBlock
      v-if="!aquatic.unlocked"
      :icon="Lock"
      title="水边还没有你的位置"
      :description="`居民等级 ${aquatic.next_spot_level || 2} 开放镇口小溪。`"
    />

    <template v-else>
      <FishingPanel :aquatic="aquatic" />

      <section class="ponds">
        <header class="ponds-heading">
          <h2>鱼塘</h2>
          <p>鱼塘持续运转，不需要守候，离线期间同样计算，捞鱼也不消耗体力。投下的鱼苗要养满三个繁殖周期才长成可捞的成鱼，此后每个周期按成鱼数繁殖，新出生的鱼同样从鱼苗养起。成鱼数保持在稳态线以上时，世代加值持续累积，捞起的鱼品质更好；跌破稳态线则逐周期回落。饲料槽见底时全塘停摆，鱼苗也停止生长。</p>
        </header>

        <div class="pond-grid">
          <PondCard
            v-for="pond in aquatic.ponds"
            :key="pond.pond_id"
            :pond="pond"
            :aquatic="aquatic"
          />

          <article
            v-for="site in aquatic.buildable_ponds"
            :key="site.id"
            class="pond-site surface-card"
            :style="{ '--pond-accent': site.accent }"
          >
            <header>
              <h3>{{ site.name }}</h3>
              <small>{{ site.description }}</small>
            </header>
            <p class="pond-site-note">
              可容纳 {{ site.capacity }} 尾。挖塘是一次性投入，此后只需负担饲料。
            </p>
            <div class="pond-site-cost">
              <Coins :size="16" />
              <strong :class="{ 'is-short': site.unlocked && !site.affordable }">{{ site.build_cost }}</strong>
              <span>红叶币</span>
            </div>
            <p v-if="!site.unlocked" class="pond-site-locked">
              <Lock :size="13" />居民等级 {{ site.min_level }} 才能挖这口塘（当前 Lv.{{ game.state.player.level }}）
            </p>
            <p v-else-if="!site.affordable" class="pond-site-locked">
              <Coins :size="13" />红叶币不足，还差 {{ site.build_cost - game.state.player.coins }} 枚
            </p>
            <ActionButton
              :action-key="`aquatic:pond:${site.id}:build`"
              :disabled="!site.unlocked || !site.affordable"
              :reason="!site.unlocked ? `居民等级 ${site.min_level} 解锁` : (!site.affordable ? '红叶币不足' : undefined)"
              @click="game.buildPond(site.id)"
            >
              <Shovel :size="15" /> 挖塘
            </ActionButton>
          </article>
        </div>
      </section>

      <FeedSlotPanel :feed-slot="aquatic.feed_slot" />
    </template>
  </section>
</template>

<style scoped>
.aquatic-view { display: flex; flex-direction: column; gap: 30px; }
.ponds-heading h2 { margin: 0; font: 600 18px Georgia, 'Noto Serif SC', serif; }
.ponds-heading p { margin: 6px 0 16px; color: #849087; font-size: 13px; line-height: 1.6; }
.pond-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.pond-site { --pond-accent: #4f8f9c; display: flex; flex-direction: column; gap: 12px; padding: 18px; border-style: dashed; border-color: color-mix(in srgb, var(--pond-accent) 26%, transparent); }
.pond-site h3 { margin: 0; font: 600 17px Georgia, 'Noto Serif SC', serif; }
.pond-site header small { display: block; margin-top: 5px; color: #849087; line-height: 1.55; }
.pond-site-note { margin: 0; color: #7d887f; font-size: 12px; line-height: 1.6; }
.pond-site-cost { display: flex; align-items: center; gap: 7px; margin-top: auto; color: var(--gold); }
.pond-site-cost strong { font-size: 19px; }
.pond-site-cost strong.is-short { color: #b4635a; }
.pond-site-locked { display: flex; align-items: center; gap: 6px; margin: -4px 0 0; color: #a4736a; font-size: 12px; line-height: 1.5; }
.pond-site-cost span { color: #7d887f; font-size: 12px; }
</style>
