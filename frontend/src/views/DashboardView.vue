<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  CloudRain,
  CloudSun,
  HandHeart,
  Leaf,
  Lock,
  PackageCheck,
  Sparkles,
  Sprout,
  Store,
  Sun,
  Wind,
} from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import ItemTile from '@/components/ItemTile.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { INDUSTRIES } from '@/lib/industries'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { IndustryId, TalentNode } from '@/types'

const game = useGameStore()
const ui = useUiStore()
const selectedIndustry = ref<IndustryId | null>(null)
const selectedDirection = computed(() => INDUSTRIES.find((entry) => entry.id === selectedIndustry.value))
function talentSummary(industry: IndustryId) {
  const nodes = talentNodes(industry)
  if (!nodes.length) return '节点筹备中'
  const ready = nodes.filter((node) => node.can_unlock).length
  return `已点亮 ${nodes.filter((node) => node.unlocked).length} / ${nodes.length}${ready ? ` · ${ready} 项可点亮` : ''}`
}

const commissions = computed(() => game.state?.commissions || null)
const commissionHint = computed(() => {
  const state = commissions.value
  if (!state) return ''
  const today = state.commission
  if (!today) return '今天没人来找你'
  if (today.settled) return '今天的已经交了'
  if (today.status === 'forwarded') return '等人接手中'
  return `${today.npc_name}要 ${today.item?.name || today.item_id} ×${today.quantity}`
})

const weatherIcons = { sunny: Sun, cloudy: CloudSun, rain: CloudRain, windy: Wind }

const weather = computed(() => {
  const current = game.state?.world.weather
  return {
    name: current?.name || '天气未知',
    accent: current?.accent || '#a9b6a8',
    icon: weatherIcons[current?.id as keyof typeof weatherIcons] || CloudSun,
  }
})

const experienceProgress = computed(() => {
  const player = game.player
  if (!player || player.next_level_xp === null) return 100
  const span = player.next_level_xp - player.current_level_xp
  return span > 0 ? Math.max(0, Math.min(100, ((player.experience - player.current_level_xp) / span) * 100)) : 100
})

function talentNodes(industry: IndustryId): TalentNode[] {
  return game.state?.talents.nodes.filter((node) => node.industry === industry) || []
}

async function unlock(node: TalentNode) {
  const available = game.state?.talents.available_points || 0
  const accepted = await ui.confirm({
    title: `点亮「${node.name}」？`,
    description: `将消耗 ${node.cost} 点天赋点，点亮后剩余 ${available - node.cost} 点。天赋点目前无法重置。`,
    confirmLabel: '点亮天赋',
  })
  if (accepted) game.unlockTalent(node.id)
}
</script>

<template>
  <section v-if="game.state && game.player" class="view-section dashboard-view">
    <ViewHeader
      eyebrow="TOWN DASHBOARD"
      :title="`早上好，${game.player.display_name}`"
    >
      <template #chip><Leaf :size="18" /> 红叶镇日常</template>
    </ViewHeader>

    <div class="dashboard-summary">
      <article class="surface-card resident-card">
        <ItemTile :size="62" tone="gold"><Sparkles :size="26" /></ItemTile>
        <div class="resident-level"><small>居民等级</small><strong>Lv.{{ game.player.level }}</strong></div>
        <div class="xp-copy">
          <span>
            <b>经验</b>
            <b>{{ game.player.next_level_xp === null ? '当前等级已满' : `${game.player.experience} / ${game.player.next_level_xp}` }}</b>
          </span>
          <ProgressBar class="xp-progress" :value="experienceProgress" :height="8" track="#28332b" color="linear-gradient(90deg, var(--leaf), var(--gold))" />
        </div>
      </article>

      <article class="surface-card weather-card" :style="{ '--weather-accent': weather.accent }">
        <component :is="weather.icon" :size="36" />
        <div><small>今日天气</small><strong>{{ weather.name }}</strong></div>
      </article>
    </div>

    <section class="dashboard-section">
      <header>
        <div><p class="eyebrow">QUICK ACTIONS</p><h2>快捷入口</h2></div>
        <span>{{ game.readyCounts.total }} 项产出可领取</span>
      </header>
      <div class="quick-grid">
        <RouterLink class="surface-card quick-card" to="/farm">
          <Sprout :size="24" /><span><strong>管理农场</strong></span>
        </RouterLink>
        <RouterLink class="surface-card quick-card" to="/market">
          <Store :size="24" /><span><strong>去商店</strong></span>
        </RouterLink>
        <button class="surface-card quick-card reserved" disabled>
          <PackageCheck :size="24" /><span><strong>一键收取</strong></span><Lock :size="16" />
        </button>
        <RouterLink v-if="commissions?.unlocked" class="surface-card quick-card" to="/commissions">
          <HandHeart :size="24" /><span><strong>今日委托</strong><small>{{ commissionHint }}</small></span>
        </RouterLink>
        <button v-else class="surface-card quick-card reserved" disabled>
          <HandHeart :size="24" /><span><strong>今日委托</strong></span><Lock :size="16" />
        </button>
      </div>
    </section>

    <section class="dashboard-section talent-tree-section">
      <header>
        <div>
          <p class="eyebrow">SEVEN PATHS</p>
          <h2>产业天赋树</h2>
        </div>
        <span class="talent-points"><Sparkles :size="18" /><strong>{{ game.state.talents.available_points }}</strong> 点可用</span>
      </header>

      <div class="talent-directions">
        <button v-for="direction in INDUSTRIES" :key="direction.id" type="button"
          class="surface-card talent-direction" aria-haspopup="dialog" @click="selectedIndustry = direction.id">
          <ItemTile :size="34" :accent="direction.accent"><component :is="direction.icon" :size="19" /></ItemTile>
          <span><strong>{{ direction.name }}</strong><small>{{ talentSummary(direction.id) }}</small></span>
          <span class="direction-arrow" aria-hidden="true">›</span>
        </button>
      </div>
    </section>
    <ModalSheet :open="Boolean(selectedDirection)" :title="`${selectedDirection?.name || ''}天赋`"
      :subtitle="`${game.state.talents.available_points} 点可用 · 点亮后无法重置`" @close="selectedIndustry = null">
      <template v-if="selectedDirection">
          <div v-if="talentNodes(selectedDirection.id).length" class="talent-node-list">
            <ActionButton
              v-for="node in talentNodes(selectedDirection.id)"
              :key="node.id"
              variant="bare"
              class="talent-node"
              :class="{ unlocked: node.unlocked }"
              :action-key="`talent:${node.id}`"
              :disabled="!node.can_unlock"
              :reason="node.locked_reason || undefined"
              @click="unlock(node)"
            >
              <span class="node-mark"><Sparkles v-if="node.unlocked" :size="15" /><Lock v-else :size="15" /></span>
              <span>
                <strong>{{ node.name }}</strong>
                <small>{{ node.description }}</small>
                <em>{{ node.unlocked ? '已点亮' : node.locked_reason || `消耗 ${node.cost} 点` }}</em>
              </span>
            </ActionButton>
          </div>
          <StateBlock v-else variant="inline" title="该方向节点正在筹备" />
      </template>
    </ModalSheet>
  </section>
</template>

<style scoped>
.dashboard-summary { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(280px, .8fr); gap: 16px; }
.resident-card,.weather-card { min-height: 174px; padding: 22px; }
.resident-card { display: grid; grid-template-columns: auto auto 1fr; align-items: center; gap: 20px; }
.resident-level small,.resident-level strong,.weather-card small,.weather-card strong { display: block; }
.resident-level strong { margin-top: 4px; color: var(--leaf-bright); font: 700 30px Georgia, serif; }
.xp-copy { min-width: 0; }
.xp-copy > span { display: flex; justify-content: space-between; gap: 12px; color: #abb5ac; }
.xp-progress { margin: 11px 0 8px; }
.weather-card { --weather-accent: #e0b45d; display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 18px; }
.weather-card > svg { color: var(--weather-accent); }
.weather-card strong { margin-top: 4px; color: var(--weather-accent); font: 700 25px Georgia, 'Noto Serif SC', serif; }
.dashboard-section { margin-top: 34px; }
.dashboard-section > header { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin-bottom: 14px; }
.dashboard-section h2 { margin: 4px 0 0; font: 700 23px Georgia, 'Noto Serif SC', serif; }
.dashboard-section > header > span { color: #929d94; }
.quick-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.quick-card { min-height: 94px; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 11px; padding: 15px; text-align: left; color: #d6ddd3; }
.quick-card > svg:first-child { color: var(--leaf-bright); }
.quick-card strong,.quick-card small { display: block; }
.quick-card small { margin-top: 3px; overflow: hidden; color: #8b968c; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.quick-card.reserved { opacity: .55; }
.talent-tree-section > header { align-items: center; }
.talent-points { display: flex; align-items: center; gap: 7px; padding: 10px 14px; color: #d8c17e !important; border: 1px solid #d7ad5833; border-radius: 99px; background: #d7ad580b; white-space: nowrap; }
.talent-points strong { font-size: 20px; }
.talent-directions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; }
.talent-direction { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; padding: 12px; text-align: left; color: inherit; cursor: pointer; }
.talent-direction:hover, .talent-direction:focus-visible { border-color: var(--gold); }
.talent-direction strong, .talent-direction small { display: block; }
.talent-direction small { margin-top: 4px; color: #929d94; font-size: 12px; }
.direction-arrow { color: var(--gold); font-size: 22px; }
.talent-direction > header { display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 10px; padding-bottom: 12px; border-bottom: 1px solid #ffffff0d; }
.talent-direction h3 { margin: 0; }
.talent-node-list { display: grid; gap: 8px; margin-top: 12px; }
.talent-node { display: grid; grid-template-columns: auto 1fr; gap: 10px; padding: 11px; text-align: left; color: #a1aba3; border: 1px solid #ffffff0e; border-radius: 10px; background: #0e1511aa; }
.talent-node:not(:disabled) { cursor: pointer; }
.talent-node.unlocked { color: #dce3d9; border-color: #d7ad5840; background: #d7ad5809; }
.node-mark { width: 31px; height: 31px; display: grid; place-items: center; color: var(--gold); border-radius: 50%; background: #d7ad5812; }
.talent-node strong,.talent-node small,.talent-node em { display: block; }
.talent-node small { margin: 4px 0; color: #828d84; font-size: 12px; line-height: 1.5; }
.talent-node em { color: #b9a465; font-size: 12px; font-style: normal; }
@media (max-width: 900px) { .dashboard-summary { grid-template-columns: 1fr; }.quick-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .resident-card { grid-template-columns: auto 1fr; }.xp-copy { grid-column: 1 / -1; }.quick-grid,.talent-directions { grid-template-columns: 1fr; }.dashboard-section > header { align-items: flex-start; }.talent-tree-section > header { flex-direction: column; }.talent-points { align-self: flex-start; } }
</style>
