<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Clock3, Gem, Lock, Pickaxe, UserRound } from 'lucide-vue-next'

import CroppedImage from '@/components/CroppedImage.vue'
import GameIcon from '@/components/GameIcon.vue'
import { useGameStore } from '@/stores/game'
import type { MiningSiteState, OwnedPartner } from '@/types'

const game = useGameStore()
const tick = ref(Date.now())
const qualityNames = ['', '普通', '良品', '上品', '臻品', '奇迹']
let timer = 0

onMounted(() => {
  timer = window.setInterval(() => (tick.value = Date.now()), 1000)
})
onBeforeUnmount(() => window.clearInterval(timer))

const miningPartners = computed(() => (game.state?.partners || []).filter(
  (partner) => !partner.missing && partner.tendencies?.some((entry) => entry.industry === 'mining'),
))

function ability(partner: OwnedPartner) {
  const tendency = partner.tendencies?.find((entry) => entry.industry === 'mining')
  return tendency?.effective_ability ?? tendency?.current_ability ?? 0
}

function remaining(site: MiningSiteState) {
  tick.value
  return site.task_snapshot ? Math.max(0, site.task_snapshot.ready_at - game.effectiveNow()) : 0
}

function progress(site: MiningSiteState) {
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
  game.assignMiningPartner(siteId, partnerId || null)
}
</script>

<template>
  <section v-if="game.state" class="view-section mining-view">
    <header class="view-heading">
      <div>
        <p class="eyebrow">MOUNTAIN MINING</p>
        <h1>山地矿产</h1>
        <p>前往矿脉开采带品质的矿石。玩家可以独自采矿，也可以邀请具有矿产倾向的伙伴协助。</p>
      </div>
      <div class="season-chip"><Pickaxe :size="18" /> 矿产编制 {{ game.state.industry_rules.mining?.partner_capacity || 0 }}</div>
    </header>

    <div class="tip-card mining-tip">
      <Gem :size="20" />
      <span>协助伙伴会缩短开采时间并提高品质能力；任务开始后，该伙伴会锁定到结算完成。</span>
    </div>

    <div v-if="!game.state.mining_sites.length" class="locked-panel">
      <Lock :size="34" />
      <h2>通往矿山的道路尚未开放</h2>
      <p>居民等级 {{ game.state.next_mining_site_level || 2 }} 解锁矿产产业。</p>
    </div>

    <div v-else class="industry-grid">
      <article
        v-for="site in game.state.mining_sites"
        :key="site.site_id"
        class="surface-card industry-card"
        :class="{ ready: site.ready }"
        :style="{ '--industry-accent': site.definition?.accent || '#a47955' }"
      >
        <header class="industry-card-heading">
          <span class="industry-card-icon"><Pickaxe :size="25" /></span>
          <div><h2>{{ site.definition?.name || site.site_id }}</h2><p>{{ site.definition?.description }}</p></div>
          <label class="production-partner-field">
            <small>协助伙伴（可选）</small>
            <select :value="site.assigned_partner_ids[0] || ''" :disabled="game.busy || site.assignment_locked" @change="assign(site.site_id, $event)">
              <option value="">玩家独自采矿</option>
              <option
                v-for="partner in miningPartners"
                :key="partner.partner_id"
                :value="partner.partner_id"
                :disabled="partner.locked && partner.partner_id !== site.assigned_partner_ids[0]"
              >{{ partner.name }} · 能力 {{ ability(partner) }}</option>
            </select>
          </label>
        </header>

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
            <UserRound v-else :size="16" />
          </span>
          <div><strong>{{ site.assigned_partners[0].name }}</strong><small>{{ site.assignment_locked ? '采矿任务中 · 已锁定' : `矿产能力 ${ability(site.assigned_partners[0])}` }}</small></div>
        </div>

        <div v-if="site.empty" class="production-task-list">
          <button
            v-for="task in site.available_tasks"
            :key="task.id"
            class="production-task-button"
            :disabled="game.busy"
            @click="game.startMining(site.site_id, task.id)"
          >
            <span class="production-task-icon"><GameIcon :name="task.item.icon" :size="25" /></span>
            <div><strong>{{ task.name }}</strong><small>{{ task.yield_min }}—{{ task.yield_max }} 个 · {{ timeLabel(task.duration_seconds) }} · -{{ task.stamina_cost }} 体力</small></div>
            <Pickaxe :size="16" />
          </button>
        </div>

        <div v-else-if="site.ready" class="production-status">
          <span class="production-task-icon"><GameIcon :name="site.task?.item.icon" :size="34" /></span>
          <div><strong>开采完成</strong><small v-if="site.task_result">{{ qualityNames[site.task_result.quality] }}品质 · {{ site.task_result.quantity }} 个{{ site.task?.item.name }}</small></div>
          <button class="primary-button" :disabled="game.busy" @click="game.collectMining(site.site_id)">收取矿石</button>
        </div>

        <div v-else>
          <div class="production-status"><span class="production-task-icon"><GameIcon :name="site.task?.item.icon" :size="30" /></span><div><strong>{{ site.task?.name }}</strong><small>品质 Q{{ site.task_snapshot?.quality_parameters.ability }} · 剩余 {{ timeLabel(remaining(site)) }}</small></div><Clock3 :size="17" /></div>
          <div class="production-progress"><i :style="{ width: `${progress(site)}%` }" /></div>
        </div>
      </article>

      <article v-if="game.state.next_mining_site_level" class="surface-card industry-card locked-industry-card">
        <Lock :size="28" /><strong>更深的矿脉</strong><span>等级 {{ game.state.next_mining_site_level }} 解锁</span>
      </article>
    </div>
  </section>
</template>

<style scoped>
.mining-tip { margin-bottom: 24px; }.industry-card-heading .production-partner-field { grid-column: 1 / -1; margin: 4px 0 0; }
</style>
