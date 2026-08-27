<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { Check, Flame, Gift, Medal, Sparkles, Trophy, X } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { AchievementEntry, AchievementTier } from '@/types'

const game = useGameStore()
const ui = useUiStore()

const tierOrder: AchievementTier[] = ['blue', 'purple', 'gold']
const tierCopy: Record<AchievementTier, { name: string; subtitle: string }> = {
  blue: { name: '蓝色成就', subtitle: '初次踏上的每一条路' },
  purple: { name: '紫色成就', subtitle: '在小镇扎根的印记' },
  gold: { name: '金色成就', subtitle: '值得被长久记住的时刻' },
}

const achievements = computed(() => game.state?.achievements || null)
const groups = computed(() => tierOrder.map((tier) => ({
  tier,
  ...tierCopy[tier],
  entries: achievements.value?.entries.filter((entry) => entry.tier === tier) || [],
})))

watch(
  () => ui.achievementOpen,
  (open) => {
    document.body.style.overflow = open ? 'hidden' : ''
    if (open) document.addEventListener('keydown', onKeydown)
    else document.removeEventListener('keydown', onKeydown)
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') ui.achievementOpen = false
}

function progress(entry: AchievementEntry) {
  return entry.target ? Math.min(100, (entry.current / entry.target) * 100) : 0
}

async function claim(entry: AchievementEntry) {
  await game.claimAchievement(entry.achievement_id)
}

async function claimAll() {
  await game.claimAllAchievements()
}
</script>

<template>
  <Teleport to="body">
    <Transition name="achievement-panel">
      <div v-if="ui.achievementOpen" class="achievement-backdrop" @click.self="ui.achievementOpen = false">
        <section class="achievement-sheet" role="dialog" aria-modal="true" aria-label="成就">
          <header class="achievement-heading">
            <span class="achievement-seal"><Trophy :size="21" /></span>
            <div>
              <p class="eyebrow">TOWN ACHIEVEMENTS</p>
              <h2>红叶镇成就</h2>
            </div>
            <div v-if="achievements" class="achievement-summary">
              <strong>{{ achievements.completed }} / {{ achievements.total }}</strong>
              <small v-if="achievements.claimable"><Gift :size="13" />{{ achievements.claimable }} 项奖励待领取</small>
              <small v-else><Flame :size="13" />累计领取 {{ achievements.maple_flame_earned }} 枫火</small>
            </div>
            <ActionButton
              v-if="achievements?.claimable"
              variant="secondary"
              class="claim-all-button"
              action-key="achievement:claim-all"
              @click="claimAll"
            >
              一键领取 {{ achievements.claimable_maple_flame }} 枫火
            </ActionButton>
            <button class="icon-button" aria-label="关闭成就" @click="ui.achievementOpen = false"><X :size="19" /></button>
          </header>

          <div class="achievement-scroll">
            <section v-for="group in groups" :key="group.tier" class="tier-section" :class="`tier-${group.tier}`">
              <header>
                <span class="tier-medal"><Medal :size="19" /></span>
                <div><h3>{{ group.name }}</h3><small>{{ group.subtitle }}</small></div>
                <em>{{ group.entries.filter((entry) => entry.completed).length }} / {{ group.entries.length }}</em>
              </header>

              <div class="achievement-grid">
                <article v-for="entry in group.entries" :key="entry.achievement_id" class="achievement-card" :class="{ completed: entry.completed, claimable: entry.claimable }">
                  <span class="card-mark"><Check v-if="entry.claimed" :size="18" /><Gift v-else-if="entry.claimable" :size="17" /><Sparkles v-else :size="17" /></span>
                  <div class="card-copy">
                    <div class="card-title"><h4>{{ entry.name }}</h4><b><Flame :size="13" />{{ entry.reward_maple_flame }}</b></div>
                    <p>{{ entry.description }}</p>
                    <div class="card-progress">
                      <ProgressBar :value="progress(entry)" :height="5" track="#0d1410" color="var(--tier-color)" />
                      <small>{{ entry.claimed ? '已领取' : entry.claimable ? '待领取' : `${entry.current} / ${entry.target}` }}</small>
                    </div>
                    <ActionButton
                      v-if="entry.claimable"
                      variant="secondary"
                      class="claim-button"
                      :action-key="`achievement:claim:${entry.achievement_id}`"
                      @click="claim(entry)"
                    >领取 {{ entry.reward_maple_flame }} 枫火</ActionButton>
                  </div>
                </article>
              </div>
            </section>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.achievement-backdrop { position: fixed; inset: 0; z-index: 76; display: grid; place-items: center; padding: 22px; background: rgba(5, 8, 6, .76); backdrop-filter: blur(6px); }
.achievement-sheet { display: flex; flex-direction: column; width: min(980px, 100%); height: min(720px, calc(100dvh - 44px)); overflow: hidden; border: 1px solid var(--line); border-radius: 26px 8px 26px 8px; background: #151f19; box-shadow: 0 40px 110px #000a; }
.achievement-heading { display: grid; grid-template-columns: auto 1fr auto auto auto; align-items: center; gap: 14px; padding: 17px 19px; border-bottom: 1px solid var(--line); background: #1a251e; }
.achievement-seal { width: 42px; height: 42px; display: grid; place-items: center; color: var(--gold); border: 1px solid #d7ad5840; border-radius: 14px 5px 14px 5px; background: #d7ad580d; }
.achievement-heading h2 { margin: 3px 0 0; font: 700 20px Georgia, 'Noto Serif SC', serif; }
.achievement-summary { display: grid; justify-items: end; gap: 3px; }
.achievement-summary strong { color: var(--gold); font-size: 18px; }
.achievement-summary small { display: flex; align-items: center; gap: 4px; color: #869188; }
.claim-all-button { white-space: nowrap; }
.achievement-scroll { flex: 1; min-height: 0; overflow: auto; padding: 22px; }
.tier-section { --tier-color: #6ea8d9; --tier-soft: #6ea8d918; margin-bottom: 28px; }
.tier-section:last-child { margin-bottom: 0; }
.tier-purple { --tier-color: #a47ad7; --tier-soft: #a47ad718; }
.tier-gold { --tier-color: #d7ad58; --tier-soft: #d7ad5818; }
.tier-section > header { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; margin-bottom: 12px; }
.tier-section h3 { margin: 0; color: var(--tier-color); font: 700 18px Georgia, 'Noto Serif SC', serif; }
.tier-section header small { color: #78837a; }
.tier-section header em { color: var(--tier-color); font-style: normal; font-weight: 700; }
.tier-medal { width: 36px; height: 36px; display: grid; place-items: center; color: var(--tier-color); border-radius: 50%; background: var(--tier-soft); }
.achievement-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.achievement-card { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 11px; min-height: 112px; padding: 14px; color: #909b92; border: 1px solid #ffffff0d; border-radius: 14px 5px 14px 5px; background: #0e1611aa; }
.achievement-card.completed { color: #dfe5dc; border-color: color-mix(in srgb, var(--tier-color) 35%, transparent); background: var(--tier-soft); }
.achievement-card.claimable { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tier-color) 18%, transparent); }
.card-mark { width: 34px; height: 34px; display: grid; place-items: center; color: #5d6960; border-radius: 50%; background: #ffffff08; }
.completed .card-mark { color: #101711; background: var(--tier-color); }
.card-copy { min-width: 0; }
.card-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.card-title h4 { margin: 2px 0 0; font-size: 15px; }
.card-title b { display: flex; align-items: center; gap: 3px; color: var(--tier-color); font-size: 13px; }
.card-copy p { min-height: 36px; margin: 6px 0 10px; color: #7f8a81; font-size: 12px; line-height: 1.5; }
.card-progress { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 10px; }
.card-progress small { color: #6f7b72; font-size: 11px; }
.completed .card-progress small { color: var(--tier-color); }
.claim-button { width: 100%; min-height: 34px; margin-top: 10px; }
.achievement-panel-enter-active,.achievement-panel-leave-active { transition: opacity .18s ease; }
.achievement-panel-enter-active .achievement-sheet,.achievement-panel-leave-active .achievement-sheet { transition: transform .18s ease; }
.achievement-panel-enter-from,.achievement-panel-leave-to { opacity: 0; }
.achievement-panel-enter-from .achievement-sheet,.achievement-panel-leave-to .achievement-sheet { transform: translateY(12px) scale(.99); }
@media (max-width: 700px) {
  .achievement-backdrop { padding: 0; }
  .achievement-sheet { width: 100%; height: 100dvh; border: 0; border-radius: 0; }
  .achievement-heading { grid-template-columns: auto 1fr auto; padding: 14px; }
  .achievement-summary { grid-column: 1 / -1; grid-row: 2; justify-items: start; padding-left: 56px; }
  .claim-all-button { grid-column: 1 / -1; grid-row: 3; width: 100%; }
  .achievement-scroll { padding: 16px 14px calc(24px + env(safe-area-inset-bottom)); }
  .achievement-grid { grid-template-columns: 1fr; }
}
</style>
