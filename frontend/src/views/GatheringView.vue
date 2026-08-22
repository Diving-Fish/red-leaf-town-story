<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Clock3, Compass, Lock, Sparkles, Trees, UsersRound } from 'lucide-vue-next'

import CroppedImage from '@/components/CroppedImage.vue'
import GameIcon from '@/components/GameIcon.vue'
import { useGameStore } from '@/stores/game'
import type { GatheringSiteState, OwnedPartner } from '@/types'

const game = useGameStore()
const tick = ref(Date.now())
const qualityNames = ['', '普通', '良品', '上品', '臻品', '奇迹']
let timer = 0

onMounted(() => {
  timer = window.setInterval(() => (tick.value = Date.now()), 1000)
})
onBeforeUnmount(() => window.clearInterval(timer))

const gatheringPartners = computed(() => (game.state?.partners || []).filter(
  (partner) => !partner.missing && partner.tendencies?.some((entry) => entry.industry === 'gathering'),
))
const gatheringTalents = computed(() => (game.state?.talents.nodes || []).filter((node) => node.industry === 'gathering'))

function ability(partner: OwnedPartner) {
  const tendency = partner.tendencies?.find((entry) => entry.industry === 'gathering')
  return tendency?.effective_ability ?? tendency?.current_ability ?? 0
}

function remaining(site: GatheringSiteState) {
  tick.value
  return site.task_snapshot ? Math.max(0, site.task_snapshot.ready_at - game.effectiveNow()) : 0
}

function progress(site: GatheringSiteState) {
  if (!site.task_snapshot) return 0
  return Math.min(100, Math.max(3, 100 - remaining(site) / site.task_snapshot.final_duration * 100))
}

function timeLabel(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return minutes ? `${minutes}分${rest ? `${rest}秒` : ''}` : `${rest}秒`
}

function assign(siteId: string, event: Event) {
  const partnerId = (event.target as HTMLSelectElement).value
  game.assignGatheringPartner(siteId, partnerId || null)
}
</script>

<template>
  <section v-if="game.state" class="view-section gathering-view">
    <header class="view-heading">
      <div>
        <p class="eyebrow">WOODLAND FORAGING</p>
        <h1>林野采集</h1>
        <p>玩家无法亲自完成采集。派遣具有采集倾向的伙伴，让他们从镇外带回带品质的素材。</p>
      </div>
      <div class="season-chip"><UsersRound :size="18" /> 采集编制 {{ game.state.industry_rules.gathering?.partner_capacity || 0 }}</div>
    </header>

    <div v-if="!gatheringPartners.length" class="tip-card">
      <Compass :size="20" />
      <span>伙伴仓库中还没有具有采集倾向的伙伴，因此暂时无法开始采集。</span>
      <RouterLink to="/partners">查看伙伴</RouterLink>
    </div>

    <section class="talent-panel">
      <div class="talent-heading">
        <div><Sparkles :size="19" /><span><strong>采集天赋树</strong><small>编制节点决定可以同时派出的采集伙伴数量</small></span></div>
        <b>{{ game.state.talents.available_points }} 点可用</b>
      </div>
      <div class="talent-nodes">
        <button
          v-for="node in gatheringTalents"
          :key="node.id"
          :class="{ unlocked: node.unlocked }"
          :disabled="game.busy || !node.can_unlock"
          @click="game.unlockTalent(node.id)"
        >
          <span class="talent-mark"><Sparkles v-if="node.unlocked" :size="15" /><Lock v-else :size="14" /></span>
          <span><strong>{{ node.name }}</strong><small>{{ node.description }}</small><em v-if="!node.unlocked">{{ node.locked_reason || `消耗 ${node.cost} 点` }}</em><em v-else>已点亮</em></span>
        </button>
      </div>
    </section>

    <div class="gathering-grid">
      <article
        v-for="site in game.state.gathering_sites"
        :key="site.site_id"
        class="gathering-site"
        :class="{ ready: site.ready }"
        :style="{ '--site-accent': site.definition?.accent || '#78906d' }"
      >
        <div class="site-heading">
          <span class="site-icon"><Trees :size="25" /></span>
          <div><h2>{{ site.definition?.name || site.site_id }}</h2><p>{{ site.definition?.description }}</p></div>
        </div>

        <label class="partner-select">
          <span>派驻伙伴</span>
          <select :value="site.assigned_partner_ids[0] || ''" :disabled="game.busy || site.assignment_locked" @change="assign(site.site_id, $event)">
            <option value="">未派驻</option>
            <option
              v-for="partner in gatheringPartners"
              :key="partner.partner_id"
              :value="partner.partner_id"
              :disabled="partner.locked && partner.partner_id !== site.assigned_partner_ids[0]"
            >{{ partner.name }} · 能力 {{ ability(partner) }}</option>
          </select>
        </label>

        <div v-if="site.assigned_partners[0]" class="assigned-partner">
          <span class="assigned-avatar">
            <CroppedImage
              v-if="site.assigned_partners[0].artwork?.url && site.assigned_partners[0].avatar_crop"
              :image-url="site.assigned_partners[0].artwork!.url!"
              :image-width="site.assigned_partners[0].artwork!.width"
              :image-height="site.assigned_partners[0].artwork!.height"
              :crop="site.assigned_partners[0].avatar_crop!"
              :alt="`${site.assigned_partners[0].name}头像`"
            />
            <UsersRound v-else :size="17" />
          </span>
          <span><strong>{{ site.assigned_partners[0].name }}</strong><small>{{ site.assignment_locked ? '采集任务中 · 已锁定' : `采集能力 ${ability(site.assigned_partners[0])}` }}</small></span>
        </div>

        <template v-if="site.empty">
          <div class="gather-actions">
            <button
              v-for="task in site.available_tasks"
              :key="task.id"
              class="gather-task"
              :disabled="game.busy || !site.assigned_partner_ids.length"
              @click="game.startGathering(site.site_id, task.id)"
            >
              <GameIcon :name="task.item.icon" :size="21" />
              <span><strong>{{ task.name }}</strong><small>{{ task.yield_min }}—{{ task.yield_max }} 个 · {{ timeLabel(task.duration_seconds) }} · -{{ task.stamina_cost }} 体力</small></span>
            </button>
          </div>
          <p v-if="!site.assigned_partner_ids.length" class="site-hint">必须先派一名采集伙伴前往</p>
        </template>

        <template v-else-if="site.ready">
          <div class="gather-result">
            <GameIcon :name="site.task?.item.icon" :size="30" />
            <span><strong>采集完成</strong><small v-if="site.task_result">{{ qualityNames[site.task_result.quality] }}品质 · {{ site.task_result.quantity }} 个{{ site.task?.item.name }}</small></span>
          </div>
          <button class="primary-button collect-button" :disabled="game.busy" @click="game.collectGathering(site.site_id)">领取采集物</button>
        </template>

        <template v-else>
          <div class="running-copy"><Clock3 :size="15" /><span><strong>{{ site.task?.name }}</strong><small>品质 Q{{ site.task_snapshot?.quality_parameters.ability }} · 剩余 {{ timeLabel(remaining(site)) }}</small></span></div>
          <div class="gather-progress"><i :style="{ width: `${progress(site)}%` }" /></div>
        </template>
      </article>

      <article v-if="game.state.next_gathering_site_level" class="gathering-site locked-site">
        <Lock :size="27" /><strong>新的采集区域</strong><span>等级 {{ game.state.next_gathering_site_level }} 解锁</span>
      </article>
    </div>
  </section>
</template>

<style scoped>
.talent-panel { padding: 17px 19px; margin-bottom: 24px; border: 1px solid #d6b36a24; border-radius: 17px 6px; background: linear-gradient(120deg, #b98d3710, #172019); }.talent-heading,.talent-heading > div { display: flex; align-items: center; justify-content: space-between; gap: 10px; }.talent-heading > div { justify-content: flex-start; }.talent-heading strong,.talent-heading small { display: block; }.talent-heading small { margin-top: 2px; color: #7f8a81; font-size: 10px; }.talent-heading b { color: #dbbd76; font-size: 11px; }.talent-nodes { display: flex; gap: 10px; margin-top: 13px; }.talent-nodes button { flex: 1; display: grid; grid-template-columns: auto 1fr; gap: 9px; padding: 11px; text-align: left; color: #9ca69e; border: 1px solid #ffffff0d; border-radius: 11px; background: #0f1712a6; }.talent-nodes button.unlocked { color: #d8dfd5; border-color: #bfa25e44; }.talent-nodes button:not(:disabled) { cursor: pointer; }.talent-mark { width: 28px; height: 28px; display: grid; place-items: center; color: #bda35f; border-radius: 50%; background: #bda35f14; }.talent-nodes strong,.talent-nodes small,.talent-nodes em { display: block; }.talent-nodes strong { font-size: 11px; }.talent-nodes small { margin: 3px 0; color: #748078; font-size: 9px; }.talent-nodes em { color: #a58d56; font-size: 8px; font-style: normal; }
.gathering-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 17px; }.gathering-site { --site-accent: #78906d; min-height: 320px; padding: 19px; border: 1px solid color-mix(in srgb, var(--site-accent) 32%, transparent); border-radius: 20px 6px; background: linear-gradient(145deg, color-mix(in srgb, var(--site-accent) 8%, #111813), #101713); box-shadow: 0 13px 35px #0002; }.gathering-site.ready { box-shadow: inset 0 0 35px color-mix(in srgb, var(--site-accent) 8%, transparent); }.site-heading { display: grid; grid-template-columns: auto 1fr; gap: 12px; }.site-icon { width: 45px; height: 45px; display: grid; place-items: center; color: var(--site-accent); border-radius: 14px 5px; background: color-mix(in srgb, var(--site-accent) 13%, transparent); }.site-heading h2 { margin: 0 0 4px; font: 600 17px Georgia, 'Noto Serif SC', serif; }.site-heading p { min-height: 32px; margin: 0; color: #78837b; font-size: 10px; line-height: 1.55; }.partner-select { display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 10px; margin: 16px 0 9px; color: #849087; font-size: 9px; }.partner-select select { width: 100%; min-width: 0; height: 34px; padding: 0 9px; color: #cbd3c8; border: 1px solid #ffffff14; border-radius: 8px; outline: none; background: #0c120e; }.assigned-partner { display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 8px; padding: 8px; margin-bottom: 10px; border-radius: 10px; background: #ffffff05; }.assigned-avatar { width: 33px; height: 33px; overflow: hidden; display: grid; place-items: center; color: #95a88a; border-radius: 9px 3px; background: #263027; }.assigned-partner strong,.assigned-partner small { display: block; }.assigned-partner strong { font-size: 10px; }.assigned-partner small { margin-top: 2px; color: #748078; font-size: 8px; }.gather-actions { display: grid; gap: 7px; }.gather-task { display: grid; grid-template-columns: auto 1fr; align-items: center; gap: 10px; padding: 11px; text-align: left; color: #ccd5c9; border: 1px solid #ffffff10; border-radius: 10px; background: #0c130f; cursor: pointer; }.gather-task:disabled { opacity: .42; cursor: default; }.gather-task strong,.gather-task small { display: block; }.gather-task strong { font-size: 11px; }.gather-task small { margin-top: 3px; color: #768078; font-size: 8px; }.site-hint { margin: 8px 0 0; text-align: center; color: #6f7971; font-size: 9px; }.running-copy,.gather-result { display: flex; align-items: center; gap: 9px; min-height: 52px; padding: 10px; color: var(--site-accent); border-radius: 11px; background: #0b110d99; }.running-copy strong,.running-copy small,.gather-result strong,.gather-result small { display: block; }.running-copy strong,.gather-result strong { color: #cbd5c8; font-size: 11px; }.running-copy small,.gather-result small { margin-top: 3px; color: #7b897e; font-size: 9px; }.gather-progress { height: 5px; overflow: hidden; margin-top: 10px; border-radius: 99px; background: #ffffff0c; }.gather-progress i { display: block; height: 100%; border-radius: inherit; background: var(--site-accent); transition: width .4s ease; }.collect-button { width: 100%; margin-top: 9px; }.locked-site { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 250px; color: #667169; border-style: dashed; background: #11171388; }.locked-site strong { margin-top: 10px; color: #8d978e; }.locked-site span { margin-top: 3px; font-size: 10px; }
@media (max-width: 720px) { .talent-heading { align-items: flex-start; }.talent-nodes { flex-direction: column; }.gathering-grid { grid-template-columns: 1fr; }.gathering-site { min-height: 0; }.site-heading p { min-height: 0; } }
</style>
