<script setup lang="ts">
import { computed, ref } from 'vue'
import { BookOpen, Fish, Lock, Sparkles, Zap } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import GameIcon from '@/components/GameIcon.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import PartnerPicker from '@/components/PartnerPicker.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import QualityTag from '@/components/QualityTag.vue'
import StateBlock from '@/components/StateBlock.vue'
import { rewardSummary } from '@/lib/rewards'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { AquaticState, FishingDrop, FishingSpotState } from '@/types'

const props = defineProps<{ aquatic: AquaticState }>()

const aquatic = computed(() => props.aquatic)
const game = useGameStore()
const ui = useUiStore()
const lastCatch = ref<{ spotId: string; drops: FishingDrop[] } | null>(null)
const codexOpen = ref(false)

async function releaseBigCatch() {
  const accepted = await ui.confirm({
    title: '放线并放弃这次大物？',
    description: '放线后将改收一条普通渔获，无法再挑战这次咬钩的大物。',
    confirmLabel: '放线',
    cancelLabel: '再想想',
  })
  if (accepted) await game.resolveBigCatch('release')
}

const QUALITY_NAMES = ['', '普通', '良品', '上品', '臻品', '奇迹']

const spots = computed(() => props.aquatic.spots.filter((spot) => spot.unlocked))
const pending = computed(() => props.aquatic.pending_big_catch)

/** 整句在脚本里拼好，模板里换行会在中文之间留下空格。 */
const pendingHint = computed(() => {
  const entry = pending.value
  if (!entry) return ''
  const chance = Math.round(entry.chance * 100)
  const quality = QUALITY_NAMES[entry.min_quality] || '普通'
  return `${entry.spot_name}的水下沉着一条大物。追加 ${entry.stamina_cost} 点体力搏一把，成功率 ${chance}%，钓上来的品质不低于${quality}；放线则改收一条寻常渔获。`
})

function comboFor(spot: FishingSpotState) {
  return props.aquatic.combo.spot_id === spot.id ? props.aquatic.combo.layers : 0
}

function affordable(spot: FishingSpotState) {
  return game.liveStamina >= spot.stamina_cost
}

/** 图鉴一行：钓过几次，最大多少厘米。体型不再是大物专属，所有鱼都记。 */
function codexLine(itemId: string | null) {
  const record = aquatic.value.codex.entries.find((entry) => entry.item_id === itemId)
  if (!record) return '已记录'
  const size = record.max_size ? ` · 最大 ${record.max_size} 厘米` : ''
  return `钓获 ${record.caught} 次${size}`
}

async function cast(spot: FishingSpotState) {
  const result = await game.castLine(spot.id)
  if (result && !result.duplicate) lastCatch.value = { spotId: spot.id, drops: result.drops }
}
</script>

<template>
  <section class="fishing">
    <header class="fishing-heading">
      <div>
        <h2><Fish :size="18" /> 垂钓</h2>
        <p>消耗体力可垂钓一轮，结果当场结算，不占用生产格，也没有等待时间。一轮之内会多次得手，连续在同一处垂钓则提高聚鱼度：聚鱼度越高，单轮所得越多，稀有渔获也越容易出现。更换钓点会使聚鱼度立即清零，长时间不下钓则逐层回落。</p>
      </div>
      <button class="codex-button" @click="codexOpen = true">
        <BookOpen :size="15" />
        鱼类图鉴 {{ aquatic.codex.recorded }}/{{ aquatic.codex.total }}
      </button>
    </header>

    <PartnerPicker
      industry="aquatic"
      action-key="aquatic:companion"
      :assigned="aquatic.companion"
      placeholder="带一位伙伴陪钓"
      dialog-title="陪钓伙伴"
      solo-label="自己去"
      @select="(partnerId) => game.assignFishingCompanion(partnerId)"
    />

    <div v-if="pending" class="big-catch">
      <div class="big-catch-copy">
        <strong><Sparkles :size="16" /> {{ pending.name }}咬钩了</strong>
        <span>{{ pendingHint }}</span>
      </div>
      <div class="big-catch-actions">
        <ActionButton
          action-key="aquatic:big-catch:fight"
          group="aquatic:big-catch"
          :disabled="game.liveStamina < pending.stamina_cost"
          :reason="game.liveStamina < pending.stamina_cost ? '体力不足' : undefined"
          @click="game.resolveBigCatch('fight')"
        >
          搏一把
        </ActionButton>
        <ActionButton
          action-key="aquatic:big-catch:release"
          group="aquatic:big-catch"
          variant="secondary"
          @click="releaseBigCatch"
        >
          放线
        </ActionButton>
      </div>
    </div>

    <StateBlock
      v-if="!spots.length"
      variant="card"
      :icon="Lock"
      title="还没有能垂钓的水面"
      :description="`居民等级 ${aquatic.next_spot_level || 2} 开放镇口小溪。`"
    />

    <div v-else class="spot-grid">
      <article
        v-for="spot in spots"
        :key="spot.id"
        class="spot-card surface-card"
        :style="{ '--spot-accent': spot.accent }"
      >
        <header>
          <div class="spot-title">
            <h3>{{ spot.name }}</h3>
            <span v-if="spot.event_badge" class="spot-badge">{{ spot.event_badge }}</span>
          </div>
          <small>{{ spot.description }}</small>
          <p v-if="spot.event_note" class="spot-note">{{ spot.event_note }}</p>
        </header>

        <dl class="spot-stats">
          <div><dt>体力</dt><dd>{{ spot.stamina_cost }}</dd></div>
          <div><dt>经验</dt><dd>{{ spot.cast_xp }}</dd></div>
          <div><dt>每轮</dt><dd>{{ spot.draws.expected }} 次</dd></div>
        </dl>

        <div class="combo">
          <div class="combo-line">
            <span>聚鱼度</span>
            <strong>{{ comboFor(spot) }} / {{ aquatic.combo_cap }}</strong>
          </div>
          <ProgressBar :value="(comboFor(spot) / aquatic.combo_cap) * 100" color="var(--spot-accent)" />
        </div>

        <ActionButton
          class="cast-button"
          :action-key="`aquatic:cast:${spot.id}`"
          group="aquatic:cast"
          :disabled="!affordable(spot) || Boolean(pending)"
          :reason="pending ? '先处理咬钩的大物' : (!affordable(spot) ? '体力不足' : undefined)"
          @click="cast(spot)"
        >
          <Zap :size="15" /> 垂钓一轮（{{ spot.stamina_cost }} 体力）
        </ActionButton>

        <transition name="catch">
          <ul v-if="lastCatch?.spotId === spot.id && lastCatch.drops.length" class="catch-list">
            <li v-for="drop in lastCatch.drops" :key="`${drop.item_id}:${drop.quality}`">
              <GameIcon :name="drop.icon" :size="14" />
              <span>{{ drop.name }}</span>
              <QualityTag v-if="drop.quality" :quality="drop.quality" :name="drop.quality_name" plain />
              <i v-if="drop.size">{{ drop.size }} 厘米</i>
              <b>×{{ drop.quantity }}</b>
            </li>
          </ul>
        </transition>
      </article>

      <StateBlock
        v-if="aquatic.next_spot_level"
        variant="card"
        :icon="Lock"
        title="更深的水面"
        :description="`等级 ${aquatic.next_spot_level} 解锁`"
      />
    </div>

    <ModalSheet
      :open="codexOpen"
      title="鱼类图鉴"
      :subtitle="`已记录 ${aquatic.codex.recorded} / ${aquatic.codex.total} 种`"
      @close="codexOpen = false"
    >
      <ul class="codex-list">
        <li v-for="(entry, index) in aquatic.codex.pool" :key="entry.item_id || `unknown-${index}`" :class="{ unknown: !entry.recorded }">
          <GameIcon :name="entry.item?.icon || 'fish'" :size="20" />
          <div>
            <strong>{{ entry.recorded ? entry.item?.name : '？？？' }}</strong>
            <small v-if="entry.recorded">{{ codexLine(entry.item_id) }}</small>
            <small v-else>还没有钓上来过</small>
          </div>
        </li>
      </ul>

      <div class="codex-milestones">
        <h4>完成度奖励</h4>
        <p class="codex-reward-hint">收齐指定种类时，奖励自动发放，无需手动领取。</p>
        <div v-for="milestone in aquatic.codex.milestones" :key="milestone.id" class="milestone" :class="{ claimed: milestone.claimed }">
          <div>
            <strong>{{ milestone.name }}</strong>
            <small>收齐 {{ milestone.required }} 种</small>
            <p class="milestone-reward">{{ rewardSummary(milestone.reward) }}</p>
          </div>
          <span v-if="milestone.claimed">已自动发放</span>
          <span v-else-if="aquatic.codex.recorded >= milestone.required">即将发放</span>
          <span v-else>还差 {{ milestone.required - aquatic.codex.recorded }} 种</span>
        </div>
      </div>
    </ModalSheet>
  </section>
</template>

<style scoped>
.fishing-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 4px; }
.fishing-heading h2 { display: flex; align-items: center; gap: 8px; margin: 0; font: 600 18px Georgia, 'Noto Serif SC', serif; }
.fishing-heading p { margin: 6px 0 0; color: #849087; line-height: 1.6; font-size: 13px; }
.codex-button { display: inline-flex; align-items: center; gap: 7px; min-height: 34px; padding: 0 12px; color: #b6c3b6; border: 1px solid var(--line); border-radius: 99px; background: #ffffff05; cursor: pointer; white-space: nowrap; }

.big-catch {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 16px;
  margin-bottom: 16px;
  border: 1px solid rgba(215, 173, 88, .32);
  border-radius: 18px 6px;
  background: linear-gradient(140deg, rgba(215, 173, 88, .12), rgba(20, 27, 22, .9));
}
.big-catch-copy strong { display: flex; align-items: center; gap: 7px; color: var(--gold); }
.big-catch-copy span { display: block; margin-top: 5px; color: #a9b2a8; font-size: 13px; line-height: 1.6; }
.big-catch-actions { display: flex; gap: 9px; }

.spot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.spot-card { --spot-accent: #6f93a6; display: flex; flex-direction: column; gap: 13px; padding: 18px; border-color: color-mix(in srgb, var(--spot-accent) 30%, transparent); background: linear-gradient(150deg, color-mix(in srgb, var(--spot-accent) 8%, #141b16), #101713); }
.spot-card h3 { margin: 0; font: 600 17px Georgia, 'Noto Serif SC', serif; }
.spot-card header small { display: block; margin-top: 5px; color: #849087; line-height: 1.55; }
.spot-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.spot-badge { flex-shrink: 0; padding: 2px 9px; border-radius: 99px; background: color-mix(in srgb, var(--spot-accent) 24%, transparent); color: var(--spot-accent); font-size: 12px; }
/* 活动钓点的收益说明：文案由后端 event_note 提供，只在有内容时显示（蓝色与探索路线的领队备注一致） */
.spot-note { margin: 8px 0 0; color: #8ab4f8; font-size: 13px; font-weight: 600; letter-spacing: 0.02em; line-height: 1.55; }

.spot-stats { display: flex; gap: 18px; margin: 0; }
.spot-stats dt { color: #77837a; font-size: 12px; }
.spot-stats dd { margin: 3px 0 0; font-weight: 700; }

.combo-line { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 6px; }
.combo-line span { color: #77837a; font-size: 12px; }
.combo-line strong { color: var(--spot-accent); }


.cast-button { width: 100%; gap: 7px; margin-top: auto; }

.catch-list { display: grid; gap: 5px; margin: 0; padding: 11px; list-style: none; border-radius: 12px; background: #0b110d99; }
.catch-list li { display: flex; align-items: center; gap: 7px; color: #b6c0b5; font-size: 12px; }
.catch-list i { color: #7f8b81; font-style: normal; font-size: 11px; }
.catch-list b { margin-left: auto; }
.catch-enter-active { transition: opacity .25s ease; }
.catch-enter-from { opacity: 0; }

.codex-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.codex-list li { display: flex; align-items: center; gap: 11px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 12px; background: #ffffff04; }
.codex-list li.unknown { color: #6d786f; opacity: .7; }
.codex-list strong { display: block; font-size: 13px; }
.codex-list small { display: block; margin-top: 3px; color: #7d887f; }

.codex-milestones { margin-top: 18px; }
.codex-milestones h4 { margin: 0 0 9px; color: #9aa79b; font-size: 12px; font-weight: 600; letter-spacing: .1em; }
.milestone { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; margin-bottom: 7px; border: 1px solid var(--line); border-radius: 12px; }
.milestone strong { font-size: 13px; }
.milestone small { display: block; margin-top: 3px; color: #7d887f; }
.milestone span { color: #8d998e; font-size: 12px; }
.milestone.claimed { border-color: rgba(168, 201, 133, .26); }
.milestone.claimed span { color: var(--leaf-bright); }
.codex-reward-hint { margin: 0 0 12px; color: var(--text-muted); font-size: 12px; line-height: 1.6; }
.milestone > div { min-width: 0; }
.milestone > span { flex-shrink: 0; }
.milestone-reward { margin: 7px 0 0; color: var(--gold); font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
</style>
