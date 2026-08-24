<script setup lang="ts">
import { Coins, Flame, Leaf, Sparkles, Star, TrendingUp } from 'lucide-vue-next'

import GameIcon from '@/components/GameIcon.vue'
import QualityTag from '@/components/QualityTag.vue'
import type { Reward } from '@/types'

defineProps<{ reward: Reward }>()
</script>

<template>
  <div v-if="!reward.empty" class="reward-chips">
    <span v-if="reward.coins"><Coins :size="13" />{{ reward.coins }}</span>
    <span v-if="reward.experience"><TrendingUp :size="13" />{{ reward.experience }} XP</span>
    <span v-if="reward.talent_points" class="reward-chips--rare"><Star :size="13" />天赋点 ×{{ reward.talent_points }}</span>
    <span v-if="reward.maple_flame"><Flame :size="13" />{{ reward.maple_flame }}</span>
    <span v-if="reward.guide_leaves" class="reward-chips--rare"><Leaf :size="13" />{{ reward.guide_leaves }}</span>
    <span v-for="item in reward.items" :key="item.item_id">
      <GameIcon :name="item.icon" :size="13" />
      {{ item.name }} ×{{ item.quantity }}
      <QualityTag v-if="item.quality" :quality="item.quality" :name="item.quality_name" plain />
    </span>
    <span v-for="partner in reward.partners" :key="partner.partner_id" class="reward-chips--rare">
      <Sparkles :size="13" />{{ partner.name }} 加入
    </span>
  </div>
</template>

<style scoped>
.reward-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.reward-chips span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  color: #9fb08f;
  font-size: 12px;
  border-radius: 99px;
  background: #8fb26f12;
}
.reward-chips--rare { color: var(--gold); background: #d5ae6314; }
</style>
