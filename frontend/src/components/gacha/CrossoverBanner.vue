<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRight, Check, Gift, Lock } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import RewardChips from '@/components/RewardChips.vue'
import type { CrossoverCampaign } from '@/types'

const props = defineProps<{ campaign: CrossoverCampaign }>()
const emit = defineEmits<{ (event: 'claim', campaignId: string): void }>()

const claimedDate = computed(() => {
  if (!props.campaign.claimed_at) return ''
  return new Date(props.campaign.claimed_at * 1000).toLocaleDateString('zh-CN')
})
</script>

<template>
  <article class="crossover-banner" :class="{ 'is-locked': !campaign.eligible }">
    <header>
      <span class="crossover-source">{{ campaign.source }}联动</span>
      <h3>{{ campaign.title }}</h3>
    </header>

    <p class="crossover-copy">{{ campaign.description }}</p>

    <div class="crossover-meta">
      <p class="crossover-requirement">
        <component :is="campaign.eligible ? Check : Lock" :size="13" />
        {{ campaign.requirement }}
      </p>
      <RewardChips :reward="campaign.reward" />
    </div>

    <footer>
      <p v-if="campaign.claimed" class="crossover-note">
        <Check :size="13" />已于 {{ claimedDate }} 领取，每个账号仅限一次
      </p>
      <p v-else-if="!campaign.eligible" class="crossover-note">{{ campaign.locked_hint }}</p>
      <p v-else class="crossover-note crossover-note--ready"><Gift :size="13" />礼物正等着你</p>

      <a
        v-if="campaign.home_url"
        class="crossover-link"
        :class="{ 'crossover-link--primary': !campaign.eligible }"
        :href="campaign.home_url"
        target="_blank"
        rel="noopener"
      >
        前往{{ campaign.source }}<ArrowUpRight :size="13" />
      </a>
      <ActionButton
        :action-key="`crossover:claim:${campaign.campaign_id}`"
        :disabled="!campaign.claimable"
        :reason="campaign.claimed ? '这份联动奖励已经领过了' : campaign.locked_hint"
        @click="emit('claim', campaign.campaign_id)"
      >{{ campaign.claimed ? '已领取' : '领取礼物' }}</ActionButton>
    </footer>
  </article>
</template>

<style scoped>
.crossover-banner {
  display: grid;
  gap: 10px;
  padding: 14px 16px;
  margin-bottom: 14px;
  border: 1px solid #d5ae6340;
  border-radius: 14px;
  background: linear-gradient(105deg, #d5ae630f, var(--surface) 55%);
}
.crossover-banner.is-locked { border-color: var(--line); background: var(--surface); }

.crossover-source {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 99px;
  background: #d5ae6318;
  color: var(--gold);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .08em;
}
.crossover-banner h3 { margin: 6px 0 0; font-size: 16px; }

.crossover-copy { margin: 0; color: #97a293; font-size: 12px; line-height: 1.7; }

.crossover-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
.crossover-requirement { display: inline-flex; align-items: center; gap: 5px; margin: 0; color: #849087; font-size: 12px; }
.is-locked .crossover-requirement svg { color: #849087; }
.crossover-requirement svg { color: var(--leaf-bright); }

footer { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.crossover-note { display: inline-flex; align-items: center; gap: 5px; margin: 0 auto 0 0; color: #7c877e; font-size: 12px; }
.crossover-note--ready { color: var(--gold); }
.crossover-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 7px 13px;
  border: 1px solid var(--line);
  border-radius: 9px;
  color: #b9c4b4;
  font-size: 13px;
  text-decoration: none;
}
.crossover-link:hover { border-color: #d5ae6355; color: var(--gold); }
.crossover-link--primary { border-color: #d5ae6355; color: var(--gold); background: #d5ae630f; }

@media (max-width: 620px) {
  footer { align-items: stretch; }
  .crossover-note { margin: 0; flex-basis: 100%; }
}
</style>
