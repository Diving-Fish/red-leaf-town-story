<script setup lang="ts">
import { computed, ref, watchEffect } from 'vue'
import { ArrowLeft, ArrowRight, Brain, CheckCircle2, Clover, Coins, Dices, Dumbbell, Footprints, PackageOpen, Sparkles, Trees, UsersRound, Wind, XCircle } from 'lucide-vue-next'

import PartnerAvatar from '@/components/PartnerAvatar.vue'
import PartnerPicker from '@/components/PartnerPicker.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { useGameStore } from '@/stores/game'
import type { ExplorationAttribute, ExplorationChoice, ExplorationResolutionResult } from '@/types'

const game = useGameStore()
const leaderId = ref('')
const memberTwo = ref('')
const memberThree = ref('')
const resolution = ref<ExplorationResolutionResult | null>(null)
const selectedActors = ref<Record<string, string>>({})

const CHECK_ATTRIBUTES: Record<ExplorationAttribute, { name: string; icon: typeof Dumbbell }> = {
  strength: { name: '力量', icon: Dumbbell },
  agility: { name: '敏捷', icon: Wind },
  intelligence: { name: '智力', icon: Brain },
  luck: { name: '幸运', icon: Clover },
}

const DEGREE_NAMES = {
  automatic_success: '行动完成',
  critical_failure: '大失败',
  failure: '检定失败',
  success: '检定成功',
  critical_success: '大成功',
} as const

const exploration = computed(() => game.state?.exploration || null)
const run = computed(() => exploration.value?.active_run || null)
const expedition = computed(() => exploration.value?.expeditions.find((entry) => entry.kind === 'transport') || null)
const allPartners = computed(() => (game.state?.partners || []).filter((partner) => !partner.missing))
const leaders = computed(() => allPartners.value.filter((partner) =>
  (partner.tendencies || []).some((tendency) => tendency.industry === 'exploration'),
))
const selectedIds = computed(() => [leaderId.value, memberTwo.value, memberThree.value].filter(Boolean))

watchEffect(() => {
  if (!leaderId.value && leaders.value.length) leaderId.value = leaders.value[0].partner_id
})

function availableFor(slot: number) {
  const selections = [leaderId.value, memberTwo.value, memberThree.value]
  return allPartners.value.filter((partner) => !selections.some((id, index) => index !== slot && id === partner.partner_id))
}

function partnerById(partnerId: string) {
  return allPartners.value.find((partner) => partner.partner_id === partnerId) || null
}

function excludedFor(slot: number) {
  return [leaderId.value, memberTwo.value, memberThree.value].filter((id, index) => index !== slot && Boolean(id))
}

function explorationAbility(partner: (typeof allPartners.value)[number]) {
  return (partner.tendencies || []).find((entry) => entry.industry === 'exploration')?.effective_ability || 0
}

async function start() {
  if (!expedition.value || !leaderId.value) return
  resolution.value = null
  await game.startExploration(expedition.value.id, selectedIds.value, leaderId.value)
}

async function resolveChoice(choiceId: string) {
  const result = await game.resolveExploration(choiceId, selectedActors.value[choiceId] || '')
  if (result) resolution.value = result
}

function actorFor(choice: ExplorationChoice) {
  return selectedActors.value[choice.id] || choice.actor_partner_id || choice.actor_options[0]?.partner_id || ''
}

function selectActor(choice: ExplorationChoice, partnerId: string) {
  selectedActors.value = { ...selectedActors.value, [choice.id]: partnerId }
}

function actorName(choice: ExplorationChoice) {
  const id = actorFor(choice)
  return choice.actor_options.find((actor) => actor.partner_id === id)?.name || id
}

function continueRoute() {
  resolution.value = null
}

async function withdraw() {
  const result = await game.withdrawExploration()
  if (result) resolution.value = null
}

function rewardText(rewards: NonNullable<typeof run.value>['pending_rewards']) {
  return rewards.map((reward) => `${reward.quality_name}${reward.item?.name || reward.item_id} ×${reward.quantity}`).join('、')
}

function signed(value: number | null) {
  if (value === null) return ''
  return value >= 0 ? `+${value}` : String(value)
}

function diceTitle(result: ExplorationResolutionResult) {
  if (result.dice_mode === 'advantage') return '优势骰'
  if (result.dice_mode === 'disadvantage') return '劣势骰'
  if (result.rolls.length > 1) return '自动重投'
  return '检定骰'
}

function diceCaption(result: ExplorationResolutionResult) {
  if (result.dice_mode === 'advantage') return '两次掷骰，取较高结果'
  if (result.dice_mode === 'disadvantage') return '两次掷骰，取较低结果'
  if (result.rolls.length > 1) return '第一次普通失败，特性自动使用重投'
  return '本次检定使用的 d20 结果'
}

function keptDieIndex(result: ExplorationResolutionResult) {
  if (result.rolls.length < 2) return 0
  if (result.dice_mode === 'advantage') return result.rolls.indexOf(Math.max(...result.rolls))
  if (result.dice_mode === 'disadvantage') return result.rolls.indexOf(Math.min(...result.rolls))
  return 1
}

function dieLabel(result: ExplorationResolutionResult, index: number) {
  if (result.rolls.length < 2) return '结果'
  if (result.dice_mode === 'advantage') return index === keptDieIndex(result) ? '取高' : '舍弃'
  if (result.dice_mode === 'disadvantage') return index === keptDieIndex(result) ? '取低' : '舍弃'
  return index === 0 ? '首次失败' : '自动重投'
}
</script>

<template>
  <section v-if="game.state" class="view-section exploration-view">
    <ViewHeader eyebrow="TRANSPORT EXPEDITION" title="探索" />

    <StateBlock
      v-if="!exploration?.unlocked && !run"
      variant="card"
      :icon="Trees"
      title="红枫林腹地尚未开放"
      description="居民等级 6 解锁采运。"
    />

    <template v-else-if="!run && expedition">
      <article class="expedition-card surface-card" :style="{ '--expedition-accent': expedition.accent }">
        <div class="expedition-heading">
          <span class="expedition-icon"><Trees :size="28" /></span>
          <div>
            <small class="ui-kicker">采运</small>
            <h2 class="ui-section-title">{{ expedition.name }}</h2>
            <p class="ui-description">{{ expedition.description }}</p>
          </div>
        </div>

        <div class="route-facts">
          <span><Coins :size="16" /> 林场采运许可 <strong>{{ expedition.entry_fee }}</strong></span>
          <span><Footprints :size="16" /> 最深 {{ expedition.max_depth }} 个节点</span>
          <span><Trees :size="16" /> 主要产出 枫木</span>
        </div>

        <div class="party-panel">
          <h3 class="ui-section-title"><UsersRound :size="18" /> 组织采运队</h3>
          <p class="ui-description">领队必须具有探索倾向；其他位置可以安排任意伙伴。探索伙伴作为队员时提供 25% 探索能力。</p>
          <div class="party-selects">
            <section class="party-slot">
              <span class="ui-label">领队 · 必须具备探索倾向</span>
              <PartnerPicker
                industry="exploration"
                action-key="exploration:party:leader"
                :assigned="partnerById(leaderId)"
                :candidates="leaders"
                :excluded-partner-ids="excludedFor(0)"
                placeholder="选择领队"
                solo-label="取消领队"
                dialog-title="选择采运领队"
                :clearable="false"
                elevated
                @select="(partnerId) => leaderId = partnerId || ''"
              />
            </section>
            <section class="party-slot">
              <span class="ui-label">队员 1 · 可选</span>
              <PartnerPicker
                industry="exploration"
                action-key="exploration:party:member-1"
                :assigned="partnerById(memberTwo)"
                :candidates="availableFor(1)"
                :excluded-partner-ids="excludedFor(1)"
                placeholder="暂不安排"
                solo-label="暂不安排"
                dialog-title="选择采运队员"
                elevated
                @select="(partnerId) => memberTwo = partnerId || ''"
              />
            </section>
            <section class="party-slot">
              <span class="ui-label">队员 2 · 可选</span>
              <PartnerPicker
                industry="exploration"
                action-key="exploration:party:member-2"
                :assigned="partnerById(memberThree)"
                :candidates="availableFor(2)"
                :excluded-partner-ids="excludedFor(2)"
                placeholder="暂不安排"
                solo-label="暂不安排"
                dialog-title="选择采运队员"
                elevated
                @select="(partnerId) => memberThree = partnerId || ''"
              />
            </section>
          </div>
        </div>

        <button
          class="primary-button start-button"
          :disabled="!leaderId || !expedition.affordable || game.isPendingPrefix('exploration:')"
          @click="start"
        >
          支付 {{ expedition.entry_fee }} 红叶币并出发
        </button>
        <p v-if="!leaders.length" class="warning">你还没有具有探索倾向的伙伴。</p>
        <p v-else-if="!expedition.affordable" class="warning">红叶币不足。</p>
      </article>
    </template>

    <template v-else-if="run">
      <div class="run-status">
        <div><small>当前路线</small><strong>{{ run.expedition.name }}</strong></div>
        <div><small>探索能力</small><strong>{{ run.exploration_ability }}</strong></div>
        <div><small>体力减免</small><strong>{{ Math.round(run.stamina_discount_rate * 100) }}%</strong></div>
        <div><small>探索进度</small><strong>{{ run.depth }} / {{ run.expedition.max_depth }}</strong></div>
        <div><small>已耗体力</small><strong>{{ run.stamina_spent }}</strong></div>
      </div>

      <div class="party-row">
        <div v-for="partner in run.party" :key="partner.partner_id" class="party-member">
          <PartnerAvatar :artwork="partner.artwork" :crop="partner.avatar_crop" :name="partner.name" :size="38" />
          <span><strong>{{ partner.name }}</strong><small>{{ partner.partner_id === run.leader_partner_id ? '领队' : '队员' }}</small></span>
        </div>
      </div>

      <article v-if="resolution" class="event-card result-card surface-card" :class="{ failed: !resolution.success }">
        <div class="result-header">
          <component :is="resolution.success ? CheckCircle2 : XCircle" :size="30" class="result-icon" />
          <div class="result-copy">
            <small class="ui-kicker">节点 {{ run.depth }} · 事件结算</small>
            <h2 class="ui-section-title">{{ DEGREE_NAMES[resolution.degree] }}</h2>
            <p class="ui-description">{{ resolution.text }}</p>
          </div>
        </div>
        <div v-if="resolution.kept_roll !== null" class="dice-panel">
          <div class="dice-heading">
            <span class="dice-heading-icon"><Dices :size="17" /></span>
            <span><strong>{{ diceTitle(resolution) }}</strong><small>{{ diceCaption(resolution) }}</small></span>
            <b>{{ signed(resolution.modifier) }} = {{ resolution.total }}</b>
          </div>
          <div class="dice-track">
            <div
              v-for="(roll, index) in resolution.rolls"
              :key="`${index}:${roll}`"
              class="die-card"
              :class="{ kept: index === keptDieIndex(resolution), discarded: index !== keptDieIndex(resolution) && resolution.rolls.length > 1 }"
            >
              <small>{{ dieLabel(resolution, index) }}</small>
              <strong>{{ roll }}</strong>
            </div>
          </div>
        </div>
        <div class="result-summary">
          <span><Footprints :size="15" /> 体力 -{{ resolution.stamina_cost }}</span>
          <span v-for="drop in resolution.drops" :key="`${drop.item_id}:${drop.quality}`">
            <PackageOpen :size="15" /> {{ drop.quality_name }}{{ drop.item?.name || drop.item_id }} ×{{ drop.quantity }}
          </span>
          <span v-if="!resolution.drops.length"><PackageOpen :size="15" /> 本节点没有取得物资</span>
        </div>
        <button class="primary-button next-button" @click="continueRoute">
          {{ resolution.completed ? '查看路线终点' : '前往下一节点' }} <ArrowRight :size="17" />
        </button>
      </article>

      <article v-else-if="run.current_event" class="event-card surface-card">
        <small class="ui-kicker">第 {{ run.depth + 1 }} 段路线</small>
        <h2 class="ui-section-title">{{ run.current_event.name }}</h2>
        <p class="ui-description">{{ run.current_event.description }}</p>
        <div class="choice-list">
          <div
            v-for="choice in run.current_event.choices"
            :key="choice.id"
            class="choice-entry"
          >
            <div class="choice-button">
              <span><strong>{{ choice.label }}</strong><small>{{ choice.description }}</small></span>
              <span class="choice-meta">
                <b v-if="choice.check && choice.check_attribute">
                  <component :is="CHECK_ATTRIBUTES[choice.check_attribute].icon" :size="13" />
                  {{ choice.check_mode === 'sum' ? '全队' : '' }}{{ CHECK_ATTRIBUTES[choice.check_attribute].name }} · DC {{ choice.check.dc }}
                </b>
                <b v-if="choice.check && choice.actor_options.length">负责：{{ actorName(choice) }}</b>
                <b v-if="choice.check && !choice.actor_options.length">{{ choice.check_actor_names.join('、') }}负责</b>
                <b v-else-if="!choice.check">无需检定</b>
                <b>体力 {{ choice.stamina_cost_min }}<template v-if="choice.stamina_cost_max !== choice.stamina_cost_min">～{{ choice.stamina_cost_max }}</template></b>
              </span>
            </div>
            <div v-if="choice.actor_options.length" class="actor-options">
              <button
                v-for="actor in choice.actor_options"
                :key="actor.partner_id"
                type="button"
                class="actor-option"
                :class="{ selected: actorFor(choice) === actor.partner_id }"
                :disabled="game.isPendingPrefix('exploration:')"
                @click="selectActor(choice, actor.partner_id)"
              >
                {{ actor.name }} · {{ actor.success_chance >= 1 ? '必定' : `成功 ${Math.round(actor.success_chance * 100)}%` }}
                <span v-if="actor.applied_effects.length" class="actor-bonus">✦ 特性</span>
              </button>
            </div>
            <button
              type="button"
              class="primary-button resolve-button"
              :disabled="game.liveStamina < choice.stamina_cost_max || game.isPendingPrefix('exploration:')"
              @click="resolveChoice(choice.id)"
            >执行行动</button>
          </div>
        </div>
      </article>

      <article v-else class="event-card completed surface-card">
        <Sparkles :size="30" />
        <h2 class="ui-section-title">路线已经走完</h2>
        <p class="ui-description">队伍抵达空心古枫，可以带着全部采运所得返程。</p>
      </article>

      <article class="haul-card surface-card">
        <h3 class="ui-section-title">拖架上的战利品</h3>
        <p v-if="run.pending_rewards.length">{{ rewardText(run.pending_rewards) }}</p>
        <p v-else class="muted">目前还没有收获。</p>
        <button class="secondary-button withdraw-button" :disabled="game.isPendingPrefix('exploration:')" @click="withdraw">
          <ArrowLeft :size="17" /> {{ run.status === 'completed' ? '完成采运并返程' : '现在撤离并结算' }}
        </button>
      </article>

      <div v-if="run.logs.length" class="event-log surface-card">
        <h3 class="ui-section-title">行程记录</h3>
        <article v-for="entry in [...run.logs].reverse()" :key="`${entry.depth}:${entry.event_id}`">
          <span>节点 {{ entry.depth }}</span>
          <div><strong>{{ entry.event_name }}</strong><p>{{ entry.text }}</p><small>体力 -{{ entry.stamina_cost }}<template v-if="entry.rewards.length"> · {{ rewardText(entry.rewards) }}</template></small></div>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.exploration-view { --expedition-accent: #b85f3f; }
.expedition-card, .event-card, .haul-card, .event-log { padding: 20px; }
.expedition-card { border-top: 3px solid var(--expedition-accent); }
.expedition-heading { display: flex; gap: 15px; align-items: flex-start; }
.expedition-heading .ui-section-title, .event-card .ui-section-title { margin: 3px 0 6px; }
.expedition-icon { width: 52px; height: 52px; display: grid; flex: 0 0 auto; place-items: center; color: #efd1b7; border-radius: 15px 5px; background: color-mix(in srgb, var(--expedition-accent) 34%, transparent); }
.route-facts { display: flex; flex-wrap: wrap; gap: 9px; margin: 18px 0; }
.route-facts span { display: inline-flex; align-items: center; gap: 6px; padding: 8px 11px; color: #aeb9b0; font-size: var(--font-copy); border-radius: 99px; background: #ffffff08; }
.party-panel { padding-top: 17px; border-top: 1px solid var(--line); }
.party-panel h3, .haul-card h3, .event-log h3 { display: flex; align-items: center; gap: 7px; margin-bottom: 7px; }
.party-selects { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 15px; }
.party-slot { min-width: 0; }
.party-slot :deep(.partner-picker) { margin: 6px 0 0; }
.start-button, .withdraw-button { min-height: 42px; margin-top: 18px; }
.start-button { background: var(--leaf-bright); }
.withdraw-button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; }
.warning { color: var(--danger); font-size: var(--font-copy); }
.run-status { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin-bottom: 12px; }
.run-status div { display: grid; gap: 3px; padding: 11px; border: 1px solid var(--line); border-radius: 11px; background: #121914; }
.run-status small, .party-member small { color: #7f8c81; font-size: var(--font-caption); }
.run-status strong { color: #ead9c2; }
.party-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.party-member { display: flex; align-items: center; gap: 8px; padding: 7px 11px; border: 1px solid var(--line); border-radius: 12px; background: #121914; }
.party-member span { display: grid; }
.party-member strong { color: #dbe3da; font-size: var(--font-copy); }
.choice-list { display: grid; gap: 9px; margin-top: 17px; }
.choice-entry { display: grid; gap: 8px; padding: 11px 14px; border: 1px solid #ffffff12; border-radius: 13px; background: #ffffff06; }
.choice-button { min-height: 67px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 11px 14px; text-align: left; color: #dce5da; border: 1px solid #ffffff12; border-radius: 13px; background: #ffffff06; cursor: pointer; }
.choice-entry:has(.resolve-button:not(:disabled)):hover { border-color: #b85f3f80; background: #b85f3f12; }
.choice-button > span:first-child { display: grid; gap: 4px; }
.choice-button strong { font-size: var(--font-body); }
.choice-button small { color: #8f9b91; font-size: var(--font-copy); line-height: 1.55; }
.choice-meta { display: grid; flex: 0 0 auto; gap: 3px; text-align: right; color: #b9c5ba; font-size: var(--font-caption); }
.choice-meta b { display: inline-flex; align-items: center; justify-content: flex-end; gap: 4px; }
.actor-options { display: flex; flex-wrap: wrap; gap: 6px; }
.actor-option { min-height: 32px; padding: 5px 9px; color: #b8c7b7; border: 1px solid #ffffff18; border-radius: 8px; background: #ffffff08; cursor: pointer; }
.actor-option.selected { color: #f0d6a8; border-color: #d79a68; background: #d79a6818; }
.actor-option:disabled { opacity: .5; cursor: default; }
.actor-bonus { margin-left: 3px; color: #d8bb7c; font-size: var(--font-caption); }
.resolve-button { justify-self: end; min-height: 34px; padding: 0 12px; }
.result-card { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 440px); align-items: start; gap: 14px 20px; border-color: color-mix(in srgb, var(--leaf-bright) 32%, var(--line)); background: linear-gradient(145deg, color-mix(in srgb, var(--leaf) 10%, var(--surface)), var(--surface)); }
.result-card.failed { border-color: color-mix(in srgb, var(--autumn) 34%, var(--line)); }
.result-header { display: flex; align-items: flex-start; gap: 14px; min-width: 0; }
.result-icon { margin-top: 2px; color: var(--leaf-bright); }
.result-card.failed .result-icon { color: var(--autumn); }
.result-copy { min-width: 0; }
.result-summary { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 7px; padding-top: 13px; border-top: 1px solid var(--line); }
.result-summary > span { display: inline-flex; align-items: center; gap: 6px; padding: 7px 10px; color: #b9c5ba; font-size: var(--font-copy); border-radius: 99px; background: #ffffff07; }
.dice-panel { width: 100%; min-width: 0; padding: 12px; border: 1px solid #d79a6840; border-radius: 12px; background: linear-gradient(135deg, #d79a6814, #ffffff05); }
.dice-heading { display: flex; align-items: center; gap: 9px; }
.dice-heading-icon { display: grid; width: 31px; height: 31px; place-items: center; color: #f0c48e; border: 1px solid #d79a6860; border-radius: 8px; background: #d79a6820; }
.dice-heading > span:nth-child(2) { display: grid; flex: 1; gap: 2px; min-width: 0; }
.dice-heading strong { color: #f0d6a8; font-size: var(--font-copy); }
.dice-heading small { color: #a9b4a9; font-size: var(--font-caption); }
.dice-heading > b { color: #e9d8bd; font-size: var(--font-body); white-space: nowrap; }
.dice-track { display: flex; gap: 8px; margin-top: 11px; }
.die-card { display: grid; flex: 1; min-width: 72px; gap: 3px; padding: 8px 10px; text-align: center; border: 1px solid #ffffff18; border-radius: 9px; background: #0e1510; }
.die-card small { color: #89978c; font-size: var(--font-caption); }
.die-card strong { color: #e2eadf; font-size: 25px; line-height: 1; }
.die-card.kept { border-color: #d79a68; box-shadow: inset 0 0 0 1px #d79a6830, 0 0 14px #d79a6818; background: #d79a6812; }
.die-card.kept small { color: #e8bb87; }
.die-card.discarded { opacity: .55; }
.dice-panel + .result-summary { align-self: stretch; }
.next-button { grid-column: 1 / -1; justify-self: end; gap: 7px; min-height: 40px; }
.event-card.completed { text-align: center; color: #d8ae79; }
.event-card.completed .ui-section-title { margin-top: 8px; }
.haul-card { margin-top: 12px; }
.haul-card p { color: #b9c3b9; font-size: var(--font-copy); }
.muted { color: #78857b !important; }
.event-log { display: grid; gap: 8px; margin-top: 12px; }
.event-log article { display: grid; grid-template-columns: 70px 1fr; gap: 10px; padding-top: 10px; border-top: 1px solid var(--line); }
.event-log article > span { color: #9f765d; font-size: var(--font-caption); }
.event-log strong { color: #dce4da; font-size: var(--font-copy); }
.event-log p { margin: 3px 0; color: #929f95; font-size: var(--font-copy); line-height: 1.6; }
.event-log small { color: #78857b; font-size: var(--font-caption); }
@media (max-width: 720px) {
  .result-card { grid-template-columns: 1fr; gap: 14px; }
  .result-header, .dice-panel, .result-summary { grid-column: 1; }
  .party-selects { grid-template-columns: 1fr; }
  .run-status { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .choice-button { align-items: flex-start; flex-direction: column; }
  .choice-meta { display: flex; gap: 12px; text-align: left; }
  .choice-meta b { justify-content: flex-start; }
  .dice-heading { align-items: flex-start; flex-wrap: wrap; }
  .dice-heading > b { width: 100%; padding-left: 40px; }
  .dice-track { width: 100%; }
}
</style>
