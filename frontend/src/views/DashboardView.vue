<script setup lang="ts">
import { computed } from 'vue'
import {
  Archive,
  CloudRain,
  CloudSun,
  Compass,
  Gem,
  Hammer,
  Leaf,
  Lock,
  PackageCheck,
  PawPrint,
  Pickaxe,
  Sparkles,
  Sprout,
  Sun,
  Trees,
  Waves,
  Wind,
} from 'lucide-vue-next'

import { useGameStore } from '@/stores/game'
import type { IndustryId, TalentNode } from '@/types'

const game = useGameStore()

const weatherOptions = [
  { name: '晴朗', description: '阳光穿过红叶，适合处理镇上的日常事务。', icon: Sun, accent: '#e0b45d' },
  { name: '多云', description: '云层缓慢经过山谷，空气十分舒适。', icon: CloudSun, accent: '#a9b6a8' },
  { name: '小雨', description: '细雨落在屋檐与田埂上，山路略显湿润。', icon: CloudRain, accent: '#7fa4b7' },
  { name: '山风', description: '来自北面山谷的风吹过整座小镇。', icon: Wind, accent: '#91ad9b' },
]

const weather = computed(() => {
  const chinaDay = Math.floor(((game.state?.server_time || 0) + 8 * 3600) / 86400)
  return weatherOptions[chinaDay % weatherOptions.length]
})

const experienceProgress = computed(() => {
  const player = game.player
  if (!player || player.next_level_xp === null) return 100
  const span = player.next_level_xp - player.current_level_xp
  return span > 0 ? Math.max(0, Math.min(100, (player.experience - player.current_level_xp) / span * 100)) : 100
})

const readyCount = computed(() => {
  if (!game.state) return 0
  return game.state.plots.filter((entry) => entry.ready).length
    + game.state.gathering_sites.filter((entry) => entry.ready).length
    + game.state.crafting_stations.filter((entry) => entry.ready).length
    + game.state.mining_sites.filter((entry) => entry.ready).length
})

const industryDirections: Array<{
  id: IndustryId
  name: string
  description: string
  icon: typeof Sprout
}> = [
  { id: 'farming', name: '农作', description: '作物、土地与收获', icon: Sprout },
  { id: 'gathering', name: '采集', description: '林野派遣与采集编制', icon: Trees },
  { id: 'mining', name: '矿产', description: '矿脉、开采与矿石品质', icon: Pickaxe },
  { id: 'aquatic', name: '水产', description: '垂钓、养殖与捕捞', icon: Waves },
  { id: 'livestock', name: '畜牧', description: '动物、饲料与畜产品', icon: PawPrint },
  { id: 'crafting', name: '加工', description: '配方、工位与成品', icon: Hammer },
  { id: 'exploration', name: '探索', description: '派遣、地点与特殊事件', icon: Compass },
]

function talentNodes(industry: IndustryId): TalentNode[] {
  return game.state?.talents.nodes.filter((node) => node.industry === industry) || []
}
</script>

<template>
  <section v-if="game.state && game.player" class="view-section dashboard-view">
    <header class="view-heading dashboard-heading">
      <div>
        <p class="eyebrow">TOWN DASHBOARD</p>
        <h1>早上好，{{ game.player.display_name }}</h1>
        <p>查看今天的状态，安排产业任务与成长方向。</p>
      </div>
      <div class="season-chip"><Leaf :size="18" /> 红叶镇日常</div>
    </header>

    <div class="dashboard-summary">
      <article class="surface-card resident-card">
        <div class="summary-icon"><Sparkles :size="26" /></div>
        <div class="resident-level"><small>居民等级</small><strong>Lv.{{ game.player.level }}</strong></div>
        <div class="xp-copy">
          <span><b>经验</b><b>{{ game.player.next_level_xp === null ? '当前等级已满' : `${game.player.experience} / ${game.player.next_level_xp}` }}</b></span>
          <div class="summary-progress"><i :style="{ width: `${experienceProgress}%` }" /></div>
          <small>每次升级获得 1 个公共天赋点</small>
        </div>
      </article>

      <article class="surface-card weather-card" :style="{ '--weather-accent': weather.accent }">
        <component :is="weather.icon" :size="36" />
        <div><small>今日天气</small><strong>{{ weather.name }}</strong><p>{{ weather.description }}</p></div>
      </article>
    </div>

    <section class="dashboard-section">
      <header><div><p class="eyebrow">QUICK ACTIONS</p><h2>快捷入口</h2></div><span>{{ readyCount }} 项产出可领取</span></header>
      <div class="quick-grid">
        <RouterLink class="surface-card quick-card" to="/farm"><Sprout :size="24" /><span><strong>管理农场</strong><small>种植与收获作物</small></span></RouterLink>
        <RouterLink class="surface-card quick-card" to="/inventory"><Archive :size="24" /><span><strong>打开仓库</strong><small>查看品质与出售物品</small></span></RouterLink>
        <button class="surface-card quick-card reserved" disabled><PackageCheck :size="24" /><span><strong>一键收取</strong><small>功能位置已预留</small></span><Lock :size="16" /></button>
        <button class="surface-card quick-card reserved" disabled><Gem :size="24" /><span><strong>今日委托</strong><small>功能位置已预留</small></span><Lock :size="16" /></button>
      </div>
    </section>

    <section class="dashboard-section talent-tree-section">
      <header>
        <div><p class="eyebrow">SEVEN PATHS</p><h2>产业天赋树</h2><p>七个方向共享升级获得的天赋点，请根据自己的生产路线进行分配。</p></div>
        <span class="talent-points"><Sparkles :size="18" /><strong>{{ game.state.talents.available_points }}</strong> 点可用</span>
      </header>

      <div class="talent-directions">
        <article v-for="direction in industryDirections" :key="direction.id" class="surface-card talent-direction">
          <header><span><component :is="direction.icon" :size="21" /></span><div><h3>{{ direction.name }}</h3><p>{{ direction.description }}</p></div></header>
          <div v-if="talentNodes(direction.id).length" class="talent-node-list">
            <button
              v-for="node in talentNodes(direction.id)"
              :key="node.id"
              :class="{ unlocked: node.unlocked }"
              :disabled="game.busy || !node.can_unlock"
              @click="game.unlockTalent(node.id)"
            >
              <span class="node-mark"><Sparkles v-if="node.unlocked" :size="15" /><Lock v-else :size="15" /></span>
              <span><strong>{{ node.name }}</strong><small>{{ node.description }}</small><em>{{ node.unlocked ? '已点亮' : node.locked_reason || `消耗 ${node.cost} 点` }}</em></span>
            </button>
          </div>
          <div v-else class="talent-empty"><Lock :size="17" /><span>该方向节点正在筹备</span></div>
        </article>
      </div>
    </section>
  </section>
</template>

<style scoped>
.dashboard-heading { align-items: center; }.dashboard-summary { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(280px, .8fr); gap: 16px; }.resident-card,.weather-card { min-height: 174px; padding: 22px; }.resident-card { display: grid; grid-template-columns: auto auto 1fr; align-items: center; gap: 20px; }.summary-icon { width: 62px; height: 62px; display: grid; place-items: center; color: var(--gold); border-radius: 20px 7px; background: #d7ad5812; }.resident-level small,.resident-level strong,.weather-card small,.weather-card strong { display: block; }.resident-level strong { margin-top: 4px; color: var(--leaf-bright); font: 700 30px Georgia, serif; }.xp-copy { min-width: 0; }.xp-copy > span { display: flex; justify-content: space-between; gap: 12px; color: #abb5ac; }.summary-progress { height: 8px; overflow: hidden; margin: 11px 0 8px; border-radius: 99px; background: #28332b; }.summary-progress i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--leaf), var(--gold)); }.xp-copy small { color: #849087; }.weather-card { --weather-accent: #e0b45d; display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 18px; }.weather-card > svg { color: var(--weather-accent); }.weather-card strong { margin-top: 4px; color: var(--weather-accent); font: 700 25px Georgia, 'Noto Serif SC', serif; }.weather-card p { margin: 8px 0 0; color: #919c93; line-height: 1.65; }.dashboard-section { margin-top: 34px; }.dashboard-section > header { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin-bottom: 14px; }.dashboard-section h2 { margin: 4px 0 0; font: 700 23px Georgia, 'Noto Serif SC', serif; }.dashboard-section > header > span { color: #929d94; }.quick-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }.quick-card { min-height: 94px; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 11px; padding: 15px; text-align: left; color: #d6ddd3; }.quick-card > svg:first-child { color: var(--leaf-bright); }.quick-card strong,.quick-card small { display: block; }.quick-card small { margin-top: 4px; color: #849087; }.quick-card.reserved { opacity: .55; }.talent-tree-section > header { align-items: center; }.talent-tree-section > header p:last-child { max-width: 670px; margin: 7px 0 0; color: #8e9990; line-height: 1.6; }.talent-points { display: flex; align-items: center; gap: 7px; padding: 10px 14px; color: #d8c17e !important; border: 1px solid #d7ad5833; border-radius: 99px; background: #d7ad580b; white-space: nowrap; }.talent-points strong { font-size: 20px; }.talent-directions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; }.talent-direction { padding: 16px; }.talent-direction > header { display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 10px; padding-bottom: 12px; border-bottom: 1px solid #ffffff0d; }.talent-direction > header > span { width: 39px; height: 39px; display: grid; place-items: center; color: var(--leaf-bright); border-radius: 12px 4px; background: #87a96b12; }.talent-direction h3 { margin: 0; }.talent-direction header p { margin: 3px 0 0; color: #7e8981; }.talent-node-list { display: grid; gap: 8px; margin-top: 12px; }.talent-node-list button { display: grid; grid-template-columns: auto 1fr; gap: 10px; padding: 11px; text-align: left; color: #a1aba3; border: 1px solid #ffffff0e; border-radius: 10px; background: #0e1511aa; }.talent-node-list button:not(:disabled) { cursor: pointer; }.talent-node-list button.unlocked { color: #dce3d9; border-color: #d7ad5840; background: #d7ad5809; }.node-mark { width: 31px; height: 31px; display: grid; place-items: center; color: var(--gold); border-radius: 50%; background: #d7ad5812; }.talent-node-list strong,.talent-node-list small,.talent-node-list em { display: block; }.talent-node-list small { margin: 4px 0; color: #828d84; line-height: 1.5; }.talent-node-list em { color: #b9a465; font-style: normal; }.talent-empty { min-height: 66px; display: flex; align-items: center; justify-content: center; gap: 8px; margin-top: 12px; color: #737e76; border: 1px dashed #ffffff0d; border-radius: 10px; }
@media (max-width: 900px) { .dashboard-summary { grid-template-columns: 1fr; }.quick-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .dashboard-heading { align-items: flex-start; }.resident-card { grid-template-columns: auto 1fr; }.xp-copy { grid-column: 1 / -1; }.quick-grid,.talent-directions { grid-template-columns: 1fr; }.dashboard-section > header { align-items: flex-start; }.talent-tree-section > header { flex-direction: column; }.talent-points { align-self: flex-start; } }
</style>
