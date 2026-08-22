<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Clock3, Compass, Lock, Trees, UsersRound } from 'lucide-vue-next'

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

    <div class="industry-grid">
      <article
        v-for="site in game.state.gathering_sites"
        :key="site.site_id"
        class="surface-card industry-card"
        :class="{ ready: site.ready }"
        :style="{ '--industry-accent': site.definition?.accent || '#78906d' }"
      >
        <div class="industry-card-heading">
          <span class="industry-card-icon"><Trees :size="25" /></span>
          <div><h2>{{ site.definition?.name || site.site_id }}</h2><p>{{ site.definition?.description }}</p></div>
        </div>

        <label class="production-partner-field">
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

        <div v-if="site.assigned_partners[0]" class="production-partner-chip">
          <span class="production-avatar">
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
          <div class="production-task-list">
            <button
              v-for="task in site.available_tasks"
              :key="task.id"
              class="production-task-button"
              :disabled="game.busy || !site.assigned_partner_ids.length"
              @click="game.startGathering(site.site_id, task.id)"
            >
              <span class="production-task-icon"><GameIcon :name="task.item.icon" :size="21" /></span>
              <span><strong>{{ task.name }}</strong><small>{{ task.yield_min }}—{{ task.yield_max }} 个 · {{ timeLabel(task.duration_seconds) }} · -{{ task.stamina_cost }} 体力</small></span>
            </button>
          </div>
          <p v-if="!site.assigned_partner_ids.length" class="site-hint">必须先派一名采集伙伴前往</p>
        </template>

        <template v-else-if="site.ready">
          <div class="production-status">
            <span class="production-task-icon"><GameIcon :name="site.task?.item.icon" :size="30" /></span>
            <span><strong>采集完成</strong><small v-if="site.task_result">{{ qualityNames[site.task_result.quality] }}品质 · {{ site.task_result.quantity }} 个{{ site.task?.item.name }}</small></span>
            <button class="primary-button" :disabled="game.busy" @click="game.collectGathering(site.site_id)">领取采集物</button>
          </div>
        </template>

        <template v-else>
          <div class="production-status"><Clock3 :size="17" /><span><strong>{{ site.task?.name }}</strong><small>品质 Q{{ site.task_snapshot?.quality_parameters.ability }} · 剩余 {{ timeLabel(remaining(site)) }}</small></span></div>
          <div class="production-progress"><i :style="{ width: `${progress(site)}%` }" /></div>
        </template>
      </article>

      <article v-if="game.state.next_gathering_site_level" class="surface-card industry-card locked-industry-card">
        <Lock :size="27" /><strong>新的采集区域</strong><span>等级 {{ game.state.next_gathering_site_level }} 解锁</span>
      </article>
    </div>
  </section>
</template>

<style scoped>
.site-hint { margin: 9px 0 0; text-align: center; color: #778178; }
</style>
