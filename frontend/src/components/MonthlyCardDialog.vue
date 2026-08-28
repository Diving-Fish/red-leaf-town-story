<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, FlaskConical, Sparkles } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import { formatDuration } from '@/lib/format'
import { useGameStore } from '@/stores/game'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (event: 'close'): void }>()

const game = useGameStore()
const code = ref('')

watch(() => props.open, (value) => { if (!value) code.value = '' })

const card = computed(() => game.state?.monthly_card || null)
const subtitle = computed(() => {
  const entry = card.value
  if (!entry) return ''
  return entry.active ? `剩余 ${entry.days_left} 天 · 到 ${entry.expires_on}` : '尚未激活'
})

const refreshIn = computed(() => {
  const entry = card.value
  if (!entry) return ''
  return formatDuration(Math.max(0, entry.next_refresh_at - game.serverNow))
})

const capReached = computed(() => (card.value ? card.value.days_left >= card.value.max_days : false))
const canRedeem = computed(() => code.value.replace(/[^0-9a-zA-Z]/g, '').length >= 4)

async function redeem() {
  if (!canRedeem.value) return
  const result = await game.redeemCode(code.value)
  if (result) code.value = ''
}
</script>

<template>
  <ModalSheet :open="open" title="月卡" :subtitle="subtitle" @close="emit('close')">
    <div v-if="card" class="card-body">
      <section class="card-status" :class="{ active: card.active }">
        <div class="card-days">
          <strong>{{ card.days_left }}</strong>
          <small>剩余天数</small>
        </div>
        <div class="card-meta">
          <p v-if="card.active">有效期至 <b>{{ card.expires_on }}</b></p>
          <p v-else>用激活码激活月卡时，立即获得 {{ card.activation_maple_flame }} 枫火。</p>
          <p class="muted">最多可累积 {{ card.max_days }} 天，每次续期 {{ card.duration_days }} 天。</p>
        </div>
      </section>

      <section class="card-daily">
        <header>
          <h3>今日奖励</h3>
          <small v-if="card.active">{{ refreshIn }}后刷新</small>
        </header>
        <div class="card-rewards">
          <span class="reward"><Sparkles :size="16" />{{ card.daily_maple_flame }} 枫火</span>
          <span class="reward"><FlaskConical :size="16" />{{ card.daily_item?.name || '绯恩特调' }} ×{{ card.daily_item_amount }}</span>
        </div>
        <ActionButton
          v-if="card.claimable"
          action-key="monthly-card:claim"
          @click="game.claimMonthlyCard()"
        >领取今日奖励</ActionButton>
        <p v-else-if="card.claimed_today" class="card-claimed"><Check :size="15" />今天已经领过了，明天再来吧</p>
        <p v-else class="card-hint">月卡生效期间，每天登录可领取以上奖励</p>
      </section>

      <section class="card-redeem">
        <label for="monthly-card-code">激活码</label>
        <input
          id="monthly-card-code"
          v-model="code"
          class="card-input"
          placeholder="XXXX-XXXX-XXXX-XXXX"
          autocomplete="off"
          spellcheck="false"
          @keyup.enter="redeem"
        />
        <p v-if="capReached" class="card-capped">剩余天数已达到 {{ card.max_days }} 天上限，暂时无法兑换。</p>
        <ActionButton
          action-key="monthly-card:redeem"
          :disabled="!canRedeem"
          :reason="canRedeem ? undefined : '请输入完整的激活码'"
          @click="redeem"
        >激活</ActionButton>
      </section>
    </div>
  </ModalSheet>
</template>

<style scoped>
.card-body { display: grid; gap: 14px; }
.card-status { display: flex; align-items: center; gap: 16px; padding: 15px; border: 1px solid var(--line); border-radius: 16px 5px 16px 5px; background: #ffffff05; }
.card-status.active { border-color: color-mix(in srgb, var(--gold) 40%, transparent); background: linear-gradient(140deg, rgba(215, 173, 88, .12), #ffffff04); }
.card-days { display: grid; justify-items: center; min-width: 68px; }
.card-days strong { color: var(--gold); font: 700 30px/1 Georgia, 'Noto Serif SC', serif; font-variant-numeric: tabular-nums; }
.card-days small { margin-top: 4px; color: #7f8a80; font-size: 11px; }
.card-meta { display: grid; gap: 5px; }
.card-meta p { margin: 0; color: #9ba69d; font-size: 12px; line-height: 1.6; }
.card-meta p.muted { color: #6f7a71; }
.card-meta b { color: var(--cream); }
.card-daily, .card-redeem { display: grid; gap: 10px; padding: 15px; border: 1px solid var(--line); border-radius: 16px 5px 16px 5px; background: #ffffff04; }
.card-daily header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.card-daily h3 { margin: 0; font: 700 14px Georgia, 'Noto Serif SC', serif; }
.card-daily header small { color: #6f7a71; font-size: 11px; font-variant-numeric: tabular-nums; }
.card-rewards { display: flex; flex-wrap: wrap; gap: 7px; }
.reward { display: flex; align-items: center; gap: 6px; padding: 7px 11px; color: var(--gold); font-size: 12px; font-weight: 700; border: 1px solid color-mix(in srgb, var(--gold) 24%, transparent); border-radius: 99px; background: rgba(215, 173, 88, .07); }
.card-claimed { display: flex; align-items: center; gap: 6px; margin: 0; color: var(--leaf-bright); font-size: 12px; }
.card-hint { margin: 0; color: #6f7a71; font-size: 12px; line-height: 1.6; }
.card-redeem label { color: #8b968c; font-size: 12px; }
.card-input {
  width: 100%;
  min-height: 44px;
  padding: 0 13px;
  color: var(--cream);
  font: 700 15px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  letter-spacing: .08em;
  text-transform: uppercase;
  border: 1px solid var(--line);
  border-radius: 11px 4px 11px 4px;
  background: #111914;
}
.card-input:focus-visible { outline: 2px solid var(--leaf); outline-offset: 1px; }
.card-input::placeholder { color: #4d5850; letter-spacing: .08em; }
.card-capped { margin: 0; color: #d8c79c; font-size: 12px; line-height: 1.6; }
</style>
