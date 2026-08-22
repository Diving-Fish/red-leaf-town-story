<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Clock3, Hammer, Lock, PackageCheck, Sparkles, UserRound } from 'lucide-vue-next'

import CroppedImage from '@/components/CroppedImage.vue'
import GameIcon from '@/components/GameIcon.vue'
import { useGameStore } from '@/stores/game'
import type { CraftingStationState, OwnedPartner, RecipeState } from '@/types'

const game = useGameStore()
const tick = ref(Date.now())
const qualityNames = ['', '普通', '良品', '上品', '臻品', '奇迹']
let timer = 0

onMounted(() => {
  timer = window.setInterval(() => (tick.value = Date.now()), 1000)
})
onBeforeUnmount(() => window.clearInterval(timer))

const craftingPartners = computed(() => (game.state?.partners || []).filter(
  (partner) => !partner.missing && partner.tendencies?.some((entry) => entry.industry === 'crafting'),
))

function ability(partner: OwnedPartner) {
  const tendency = partner.tendencies?.find((entry) => entry.industry === 'crafting')
  return tendency?.effective_ability ?? tendency?.current_ability ?? 0
}

function remaining(station: CraftingStationState) {
  tick.value
  return station.task_snapshot ? Math.max(0, station.task_snapshot.ready_at - game.effectiveNow()) : 0
}

function progress(station: CraftingStationState) {
  if (!station.task_snapshot) return 0
  return Math.min(100, Math.max(3, 100 - remaining(station) / station.task_snapshot.final_duration * 100))
}

function timeLabel(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return minutes ? `${minutes}分${rest ? `${rest}秒` : ''}` : `${rest}秒`
}

function assign(stationId: string, event: Event) {
  const partnerId = (event.target as HTMLSelectElement).value
  game.assignCraftingPartner(stationId, partnerId || null)
}

function inputSummary(recipe: RecipeState) {
  return recipe.inputs.map((input) => `${input.item.name} ${input.owned_quantity}/${input.quantity}`).join(' · ')
}

function inputName(station: CraftingStationState, itemId: string) {
  return station.recipe?.inputs.find((input) => input.item_id === itemId)?.item.name || itemId
}
</script>

<template>
  <section v-if="game.state" class="view-section crafting-view">
    <header class="view-heading">
      <div>
        <p class="eyebrow">TOWN WORKSHOP</p>
        <h1>加工工坊</h1>
        <p>把农作物和采集物制成更有价值的商品。每份配方都由服务器条件钩子独立解锁。</p>
      </div>
      <div class="season-chip"><Hammer :size="18" /> 加工编制 {{ game.state.industry_rules.crafting?.partner_capacity || 0 }}</div>
    </header>

    <div class="tip-card crafting-tip">
      <PackageCheck :size="20" />
      <span>加工允许玩家独自操作；派驻具有加工倾向的伙伴可以缩短时间并提高品质能力。开工默认优先消耗低品质原料。</span>
    </div>

    <div v-if="!game.state.crafting_stations.length" class="locked-panel">
      <Lock :size="34" />
      <h2>镇民工坊尚未开放</h2>
      <p>居民等级 {{ game.state.next_crafting_station_level || 3 }} 解锁加工产业。</p>
    </div>

    <div v-else class="station-list">
      <article
        v-for="station in game.state.crafting_stations"
        :key="station.station_id"
        class="surface-card industry-card crafting-station"
        :class="{ ready: station.ready }"
        :style="{ '--industry-accent': station.definition?.accent || '#ad8159' }"
      >
        <header class="industry-card-heading station-heading">
          <span class="industry-card-icon"><Hammer :size="25" /></span>
          <div><h2>{{ station.definition?.name || station.station_id }}</h2><p>{{ station.definition?.description }}</p></div>
          <label class="production-partner-field">
            <small>协助伙伴（可选）</small>
            <select :value="station.assigned_partner_ids[0] || ''" :disabled="game.busy || station.assignment_locked" @change="assign(station.station_id, $event)">
              <option value="">玩家独自加工</option>
              <option
                v-for="partner in craftingPartners"
                :key="partner.partner_id"
                :value="partner.partner_id"
                :disabled="partner.locked && partner.partner_id !== station.assigned_partner_ids[0]"
              >{{ partner.name }} · 能力 {{ ability(partner) }}</option>
            </select>
          </label>
        </header>

        <div v-if="station.assigned_partners[0]" class="production-partner-chip">
          <span class="production-avatar">
            <CroppedImage
              v-if="station.assigned_partners[0].artwork?.url && station.assigned_partners[0].avatar_crop"
              :image-url="station.assigned_partners[0].artwork!.url!"
              :image-width="station.assigned_partners[0].artwork!.width"
              :image-height="station.assigned_partners[0].artwork!.height"
              :crop="station.assigned_partners[0].avatar_crop!"
              :alt="`${station.assigned_partners[0].name}头像`"
            />
            <UserRound v-else :size="16" />
          </span>
          <div><strong>{{ station.assigned_partners[0].name }}</strong><small>{{ station.assignment_locked ? '加工任务中 · 已锁定' : `加工能力 ${ability(station.assigned_partners[0])}` }}</small></div>
        </div>

        <div v-if="station.empty" class="recipe-grid">
          <article v-for="recipe in station.recipes" :key="recipe.id" class="surface-card recipe-card" :class="{ locked: !recipe.unlocked }">
            <div class="recipe-output">
              <span><GameIcon :name="recipe.item.icon" :size="24" /></span>
              <div><h3>{{ recipe.name }}</h3><small>产出 {{ recipe.produce_quantity }} 个{{ recipe.item.name }}</small></div>
              <Lock v-if="!recipe.unlocked" :size="15" />
            </div>
            <div class="recipe-inputs">
              <span v-for="input in recipe.inputs" :key="input.item_id" :class="{ missing: input.owned_quantity < input.quantity }">
                <GameIcon :name="input.item.icon" :size="14" />{{ input.item.name }} {{ input.owned_quantity }}/{{ input.quantity }}
              </span>
            </div>
            <p v-if="!recipe.unlocked" class="unlock-copy">{{ recipe.unlock_description }}</p>
            <p v-else>{{ timeLabel(recipe.duration_seconds) }} · -{{ recipe.stamina_cost }} 体力 · 品质加工</p>
            <button
              class="secondary-button"
              :disabled="game.busy || !recipe.unlocked || !recipe.ingredients_available"
              :title="!recipe.unlocked ? recipe.unlock_description : inputSummary(recipe)"
              @click="game.startCrafting(station.station_id, recipe.id)"
            >{{ !recipe.unlocked ? '配方未解锁' : !recipe.ingredients_available ? '原料不足' : '开始加工' }}</button>
          </article>
        </div>

        <div v-else-if="station.ready" class="production-status crafting-result">
          <span class="production-task-icon"><GameIcon :name="station.recipe?.item.icon" :size="34" /></span>
          <div><strong>加工完成</strong><small v-if="station.task_result">{{ qualityNames[station.task_result.quality] }}品质 · {{ station.task_result.quantity }} 个{{ station.recipe?.item.name }}</small></div>
          <button class="primary-button" :disabled="game.busy" @click="game.collectCrafting(station.station_id)">领取成品</button>
        </div>

        <div v-else class="crafting-running">
          <div class="running-product"><span><GameIcon :name="station.recipe?.item.icon" :size="28" /></span><div><strong>{{ station.recipe?.name }}</strong><small>品质 Q{{ station.task_snapshot?.quality_parameters.ability }} · 剩余 {{ timeLabel(remaining(station)) }}</small></div><Clock3 :size="17" /></div>
          <div class="consumed-list"><small>已投入</small><span v-for="input in station.task_snapshot?.consumed_inputs" :key="`${input.item_id}:${input.quality}`">{{ qualityNames[input.quality] || '无品质' }}{{ inputName(station, input.item_id) }} ×{{ input.quantity }}</span></div>
          <div class="production-progress"><i :style="{ width: `${progress(station)}%` }" /></div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.crafting-tip { margin-bottom: 24px; }.station-list { display: grid; gap: 18px; }.station-heading { grid-template-columns: auto 1fr minmax(220px, 280px); padding-bottom: 15px; border-bottom: 1px solid #ffffff0d; }.station-heading .production-partner-field { display: block; margin: 0; }.recipe-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 15px; }.recipe-card { padding: 13px; border-radius: 13px; background: #0c130f99; }.recipe-card.locked { opacity: .58; }.recipe-output { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 9px; }.recipe-output > span { width: 40px; height: 40px; display: grid; place-items: center; color: var(--industry-accent); border-radius: 11px 4px; background: color-mix(in srgb, var(--industry-accent) 11%, transparent); }.recipe-output h3 { margin: 0; }.recipe-output small { color: #78827a; }.recipe-inputs { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 11px; }.recipe-inputs span { display: flex; align-items: center; gap: 4px; padding: 5px 7px; color: #9eaa9f; border-radius: 6px; background: #ffffff05; }.recipe-inputs span.missing { color: #c08073; }.recipe-card > p { min-height: 16px; margin: 9px 0; color: #7c877e; }.recipe-card .unlock-copy { color: #ae9163; }.recipe-card button { width: 100%; }.crafting-result { min-height: 130px; }.crafting-running { margin-top: 15px; padding: 15px; border-radius: 14px; background: #0c130f99; }.running-product { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 11px; }.running-product > span { width: 52px; height: 52px; display: grid; place-items: center; color: var(--industry-accent); border-radius: 15px 5px; background: color-mix(in srgb, var(--industry-accent) 13%, transparent); }.running-product strong,.running-product small { display: block; }.running-product small { margin-top: 4px; color: #7a867c; }.consumed-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }.consumed-list small { color: #7b867d; }.consumed-list span { padding: 4px 7px; color: #a3aca4; border-radius: 5px; background: #ffffff05; }
@media (max-width: 720px) { .station-heading { grid-template-columns: auto 1fr; }.station-heading label { grid-column: 1 / -1; }.recipe-grid { grid-template-columns: 1fr; }.crafting-result { grid-template-columns: auto 1fr; }.crafting-result button { grid-column: 1 / -1; width: 100%; } }
</style>
