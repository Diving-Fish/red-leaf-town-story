<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Check, Clock3, Flame, HandHeart, Lock, Send, Sparkles, Undo2 } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import GameIcon from '@/components/GameIcon.vue'
import ItemTile from '@/components/ItemTile.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { useCountdown } from '@/composables/useCountdown'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { CommissionBoard, CommissionBoardEntry } from '@/types'

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

const game = useGameStore()
const ui = useUiStore()
const board = ref<CommissionBoard | null>(null)

const commissions = computed(() => game.state?.commissions || null)
const today = computed(() => commissions.value?.commission || null)
const { label: refreshLabel } = useCountdown(() => commissions.value?.refresh_at, null)

const luckyLabel = computed(() => {
  const state = commissions.value
  if (!state) return ''
  return state.lucky_today ? '今天就是你的幸运日' : `幸运日：每${WEEKDAYS[state.lucky_weekday]}`
})

const progress = computed(() => {
  const entry = today.value
  if (!entry) return 0
  return Math.min(100, (entry.owned / entry.quantity) * 100)
})

const statusLabel = computed(() => {
  const entry = today.value
  if (!entry) return ''
  if (entry.status === 'completed') return '已交付'
  if (entry.status === 'forward_completed') return `${entry.completed_by_name} 替你跑了这一趟`
  if (entry.status === 'forwarded') return '正在公共转发池里等人接手'
  return `还差 ${Math.max(0, entry.quantity - entry.owned)} 份`
})

async function reloadBoard() {
  if (!commissions.value?.board_available) return
  const next = await game.loadCommissionBoard()
  if (next) board.value = next
}

async function submit() {
  await game.submitCommission()
  await reloadBoard()
}

async function forward() {
  await game.forwardCommission()
  await reloadBoard()
}

async function withdraw() {
  const accepted = await ui.confirm({
    title: '收回这份委托？',
    description: '将从公共转发池收回尚未被接走的委托，之后仍可自行交付并获得全额奖励。',
    confirmLabel: '收回委托',
    cancelLabel: '保留委托',
  })
  if (!accepted) return
  await game.withdrawCommission()
  await reloadBoard()
}

async function take(entry: CommissionBoardEntry) {
  await game.takeCommission(entry.commission_id)
  await reloadBoard()
}

onMounted(reloadBoard)
watch(() => commissions.value?.day, reloadBoard)
</script>

<template>
  <section v-if="commissions" class="view-section">
    <ViewHeader eyebrow="DAILY COMMISSIONS" title="今日委托">
      <template #chip><Clock3 :size="18" /> {{ refreshLabel }}后刷新</template>
    </ViewHeader>

    <StateBlock
      v-if="!commissions.unlocked"
      :title="`居民等级达到 ${commissions.min_level} 级后开放`"
      description="镇上的人还不认识你，没人会把活儿托付过来。"
    />

    <template v-else>
      <article
        class="surface-card commission-card"
        :class="{ 'commission-card--lucky': today?.lucky, 'commission-card--done': today?.settled }"
      >
        <StateBlock v-if="!today" variant="inline" title="今天没有人来找你" description="等你能产出更多东西之后再来看看。" />
        <template v-else>
          <header class="commission-head">
            <ItemTile :size="52" :tone="today.lucky ? 'gold' : 'accent'">
              <HandHeart :size="24" />
            </ItemTile>
            <div class="commission-who">
              <strong>{{ today.npc_name }}</strong>
              <small>{{ today.npc_title }}</small>
            </div>
            <span v-if="today.lucky" class="commission-chip commission-chip--lucky"><Sparkles :size="13" />幸运日</span>
            <span v-else class="commission-chip">{{ today.tier_name }}</span>
          </header>

          <p class="commission-line">{{ today.line }}</p>

          <div class="commission-goods">
            <ItemTile :size="46" tone="plain"><GameIcon :name="today.item?.icon" :size="22" /></ItemTile>
            <div class="commission-count">
              <span>
                <b>{{ today.item?.name || today.item_id }}</b>
                <b :class="{ enough: today.owned >= today.quantity }">{{ today.owned }} / {{ today.quantity }}</b>
              </span>
              <ProgressBar :value="progress" :height="8" track="#28332b" color="linear-gradient(90deg, var(--leaf), var(--gold))" />
              <em>{{ statusLabel }}</em>
            </div>
            <div class="commission-pay">
              <Flame :size="17" />
              <strong>{{ today.reward_maple_flame }}</strong>
              <small>枫火</small>
            </div>
          </div>

          <footer v-if="!today.settled" class="commission-actions">
            <ActionButton
              action-key="commissions:submit"
              group="commissions:"
              :disabled="!today.can_submit"
              :reason="today.can_forward ? '仓库里的数量还不够' : '这份委托已经转发出去了'"
              @click="submit"
            >
              <Check :size="16" /> 交付委托
            </ActionButton>
            <ActionButton
              v-if="today.can_forward"
              variant="secondary"
              action-key="commissions:forward"
              group="commissions:"
              :disabled="!commissions.board_available"
              reason="转发池暂时不可用"
              @click="forward"
            >
              <Send :size="16" /> 转发出去（自己留 {{ today.owner_reward }} 枫火）
            </ActionButton>
            <ActionButton
              v-if="today.can_withdraw"
              variant="secondary"
              action-key="commissions:withdraw"
              group="commissions:"
              @click="withdraw"
            >
              <Undo2 :size="16" /> 收回委托
            </ActionButton>
          </footer>
          <footer v-else class="commission-settled"><Check :size="16" /> {{ statusLabel }}</footer>
        </template>
      </article>

      <p class="commission-hint">
        <Sparkles :size="14" />
        {{ luckyLabel }}——幸运日的委托更难交，但给 {{ commissions.lucky_reward_maple_flame }} 枫火。
      </p>

      <section class="commission-section">
        <header>
          <div><p class="eyebrow">PUBLIC BOARD</p><h2>公共转发池</h2></div>
          <span>今天还能接 {{ commissions.remaining_takes }} / {{ commissions.daily_take_limit }} 单</span>
        </header>

        <StateBlock
          v-if="!board || !board.entries.length"
          variant="panel"
          title="池子里还没有委托"
          description="别人交不掉的委托会挂到这里，替他们跑一趟能分到一份枫火。"
        />
        <div v-else class="board-grid">
          <article
            v-for="entry in board.entries"
            :key="entry.commission_id"
            class="surface-card board-card"
            :class="{ 'board-card--lucky': entry.lucky }"
          >
            <header>
              <div>
                <strong>{{ entry.npc_name }}</strong>
                <small>{{ entry.owner_name }} 转发</small>
              </div>
              <span v-if="entry.lucky" class="commission-chip commission-chip--lucky"><Sparkles :size="13" />幸运日</span>
            </header>
            <div class="board-goods">
              <ItemTile :size="40" tone="plain"><GameIcon :name="entry.item?.icon" :size="20" /></ItemTile>
              <div>
                <b>{{ entry.item?.name || entry.item_id }} ×{{ entry.quantity }}</b>
                <small>你有 {{ entry.owned }} 份</small>
              </div>
              <div class="commission-pay">
                <Flame :size="15" />
                <strong>{{ entry.taker_reward }}</strong>
              </div>
            </div>
            <ActionButton
              :action-key="`commissions:take:${entry.commission_id}`"
              group="commissions:"
              :disabled="!entry.can_take"
              :reason="commissions.remaining_takes ? '仓库里的数量还不够' : '今天已经替别人跑过一趟了'"
              @click="take(entry)"
            >
              <HandHeart :size="16" /> 接下这单
            </ActionButton>
          </article>
        </div>
      </section>

      <section v-if="commissions.takes.length" class="commission-section">
        <header><div><p class="eyebrow">TODAY'S HELP</p><h2>今天替别人跑的</h2></div></header>
        <ul class="take-list">
          <li v-for="record in commissions.takes" :key="record.commission_id" class="surface-card">
            <Check :size="15" />
            <span>替 <b>{{ record.owner_name }}</b> 交了 {{ record.quantity }} 份</span>
            <em><Flame :size="13" /> {{ record.reward_maple_flame }}</em>
          </li>
        </ul>
      </section>
    </template>
  </section>
  <StateBlock v-else :icon="Lock" title="正在读取委托" />
</template>

<style scoped>
.commission-card { padding: 22px; }
.commission-card--lucky { border-color: rgba(215, 173, 88, .34); }
.commission-card--done { opacity: .78; }
.commission-head { display: flex; align-items: center; gap: 14px; }
.commission-who { min-width: 0; }
.commission-who strong { display: block; font: 700 19px Georgia, 'Noto Serif SC', serif; }
.commission-who small { color: #8b968c; }
.commission-chip { margin-left: auto; display: flex; align-items: center; gap: 5px; padding: 6px 11px; color: #bdc9bc; font-size: 12px; border: 1px solid var(--line); border-radius: 99px; white-space: nowrap; }
.commission-chip--lucky { color: var(--gold); border-color: rgba(215, 173, 88, .32); background: rgba(215, 173, 88, .08); }
.commission-line { margin: 16px 0 18px; color: #cbd4c8; font-size: 14px; line-height: 1.9; }
.commission-goods { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 16px; padding: 14px; border: 1px solid var(--line); border-radius: 14px; background: #ffffff05; }
.commission-count { min-width: 0; }
.commission-count > span { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 9px; color: #abb5ac; font-size: 13px; }
.commission-count b.enough { color: var(--leaf-bright); }
.commission-count em { display: block; margin-top: 8px; color: #86917f; font-size: 12px; font-style: normal; }
.commission-pay { display: flex; align-items: center; gap: 6px; color: var(--gold); }
.commission-pay strong { font: 700 19px Georgia, serif; }
.commission-pay small { color: #8b968c; font-size: 12px; }
.commission-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
.commission-actions button { display: inline-flex; align-items: center; gap: 7px; }
.commission-settled { display: flex; align-items: center; gap: 8px; margin-top: 18px; color: var(--leaf-bright); font-size: 13px; }
.commission-hint { display: flex; align-items: center; gap: 8px; margin: 14px 2px 0; color: #86917f; font-size: 12px; }
.commission-hint svg { color: var(--gold); flex-shrink: 0; }
.commission-section { margin-top: 34px; }
.commission-section > header { display: flex; align-items: end; justify-content: space-between; gap: 18px; margin-bottom: 14px; }
.commission-section h2 { margin: 4px 0 0; font: 700 23px Georgia, 'Noto Serif SC', serif; }
.commission-section > header > span { color: #929d94; font-size: 13px; }
.board-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(288px, 1fr)); gap: 14px; }
.board-card { padding: 17px; display: flex; flex-direction: column; gap: 13px; }
.board-card--lucky { border-color: rgba(215, 173, 88, .3); }
.board-card > header { display: flex; align-items: center; gap: 10px; }
.board-card > header strong { display: block; font: 700 16px Georgia, 'Noto Serif SC', serif; }
.board-card > header small { color: #86917f; font-size: 12px; }
.board-goods { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 12px; }
.board-goods b { display: block; font-size: 14px; }
.board-goods small { color: #86917f; font-size: 12px; }
.board-card button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; }
.take-list { display: grid; gap: 10px; padding: 0; margin: 0; list-style: none; }
.take-list li { display: flex; align-items: center; gap: 10px; padding: 13px 16px; color: #bdc9bc; font-size: 13px; }
.take-list li > svg { color: var(--leaf-bright); }
.take-list em { margin-left: auto; display: flex; align-items: center; gap: 5px; color: var(--gold); font-style: normal; }
@media (max-width: 560px) {
  .commission-goods { grid-template-columns: auto minmax(0, 1fr); }
  .commission-pay { grid-column: 1 / -1; }
  .commission-actions button { flex: 1 1 100%; }
}
</style>
