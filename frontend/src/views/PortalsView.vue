<script setup lang="ts">
import { computed } from 'vue'
import { Check, DoorOpen, Lock } from 'lucide-vue-next'

import ActionButton from '@/components/ActionButton.vue'
import GameIcon from '@/components/GameIcon.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import QualityTag from '@/components/QualityTag.vue'
import RewardChips from '@/components/RewardChips.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { useGameStore } from '@/stores/game'
import type { PortalState, PortalTribute } from '@/types'

const game = useGameStore()

const portals = computed(() => game.state?.portals || [])
const openedCount = computed(() => portals.value.filter((portal) => portal.completed).length)

function tributeProgress(tribute: PortalTribute) {
  return (tribute.delivered / tribute.quantity) * 100
}

function deliverLabel(tribute: PortalTribute) {
  if (tribute.completed) return '已交齐'
  if (!tribute.deliverable) return '数量不足'
  return `交付 ×${tribute.deliverable}`
}

function deliver(portal: PortalState, tribute: PortalTribute) {
  if (!tribute.deliverable) return
  game.deliverTribute(portal.portal_id, tribute.id, tribute.deliverable)
}
</script>

<template>
  <section v-if="game.state" class="view-section">
    <ViewHeader eyebrow="PORTALS" title="传送门">
      <template #chip><DoorOpen :size="18" /> 已开启 {{ openedCount }} / {{ portals.length }}</template>
    </ViewHeader>

    <StateBlock v-if="!portals.length" title="山谷里还没有传送门" />

    <div v-else class="portal-grid">
      <article
        v-for="portal in portals"
        :key="portal.portal_id"
        class="portal-card"
        :class="{ 'portal-card--locked': !portal.unlocked, 'portal-card--done': portal.completed }"
        :style="{ '--portal-accent': portal.accent }"
      >
        <header>
          <div class="portal-seal"><DoorOpen v-if="portal.unlocked" :size="20" /><Lock v-else :size="18" /></div>
          <div>
            <strong>{{ portal.name }}</strong>
            <small>{{ portal.completed_tribute_count }} / {{ portal.tribute_count }} 项贡品</small>
          </div>
          <span v-if="portal.completed" class="portal-chip portal-chip--done"><Check :size="13" />已开启</span>
          <span v-else-if="portal.unlocked" class="portal-chip">进行中</span>
          <span v-else class="portal-chip portal-chip--locked">未开启</span>
        </header>

        <p class="portal-copy">{{ portal.description }}</p>

        <div v-if="!portal.unlocked" class="portal-locked">
          <Lock :size="15" />
          <span>{{ portal.locked_reason }}</span>
        </div>

        <ul v-else class="tribute-list">
          <li v-for="tribute in portal.tributes" :key="tribute.id" :class="{ done: tribute.completed }">
            <div class="tribute-heading">
              <GameIcon :name="tribute.icon" :size="17" />
              <strong>{{ tribute.name }}</strong>
              <QualityTag v-if="tribute.min_quality" :quality="tribute.min_quality" :name="`${tribute.min_quality_name}以上`" />
              <small>{{ tribute.delivered }} / {{ tribute.quantity }}</small>
            </div>
            <ProgressBar
              class="tribute-track"
              :value="tributeProgress(tribute)"
              :height="5"
              :color="tribute.completed ? 'var(--leaf-bright)' : 'var(--portal-accent)'"
            />
            <div class="tribute-footer">
              <RewardChips :reward="tribute.reward" />
              <ActionButton
                v-if="!tribute.completed"
                variant="secondary"
                :action-key="`portal:${portal.portal_id}:${tribute.id}`"
                :disabled="!tribute.deliverable"
                :reason="tribute.deliverable ? undefined : `仓库里够格的${tribute.name}不够`"
                @click="deliver(portal, tribute)"
              >
                {{ deliverLabel(tribute) }}
              </ActionButton>
              <span v-else class="tribute-done"><Check :size="14" />已交齐</span>
            </div>
          </li>
        </ul>

        <footer v-if="!portal.completion_reward.empty">
          <small>{{ portal.completed ? '开启回礼' : '全部交齐后' }}</small>
          <RewardChips :reward="portal.completion_reward" />
        </footer>

        <div v-if="portal.prerequisites.length" class="portal-roots">
          <span v-for="entry in portal.prerequisites" :key="entry.portal_id" :class="{ met: entry.completed }">
            <Check v-if="entry.completed" :size="12" /><Lock v-else :size="12" />{{ entry.name }}
          </span>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.portal-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 14px; }
.portal-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 22px 7px 22px 7px;
  background: linear-gradient(155deg, color-mix(in srgb, var(--portal-accent) 9%, #202a24), #18211c);
}
.portal-card--locked { border-style: dashed; background: #12191588; }
.portal-card--done { border-color: color-mix(in srgb, var(--portal-accent) 42%, transparent); }
.portal-card > header { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; }
.portal-seal {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  color: var(--portal-accent);
  border-radius: 13px 4px;
  background: color-mix(in srgb, var(--portal-accent) 16%, transparent);
}
.portal-card header strong { display: block; font-family: Georgia, 'Noto Serif SC', serif; font-size: 16px; }
.portal-card header small { color: #7f8b81; font-size: 12px; }
.portal-chip { padding: 4px 10px; color: #93a08f; font-size: 12px; border-radius: 99px; background: #ffffff0a; }
.portal-chip--done { display: inline-flex; align-items: center; gap: 4px; color: var(--leaf-bright); background: #8fb26f18; }
.portal-chip--locked { color: #6f7b72; }
.portal-copy { margin: 0; color: #8b968b; font-size: 13px; line-height: 1.7; }
.portal-locked { display: flex; align-items: center; gap: 7px; padding: 12px; color: #7d8880; font-size: 12px; border: 1px dashed var(--line); border-radius: 11px; }
.tribute-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.tribute-list li { padding: 11px; border: 1px solid #ffffff0d; border-radius: 12px; background: #ffffff05; }
.tribute-list li.done { border-color: #8fb26f26; background: #8fb26f0a; }
.tribute-heading { display: flex; align-items: center; gap: 7px; color: var(--portal-accent); }
.tribute-heading strong { color: #dde5d9; font-size: 14px; }
.tribute-heading small { margin-left: auto; color: #8b968b; font-size: 12px; }
.tribute-track { margin: 9px 0 10px; }
.tribute-footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.tribute-done { display: inline-flex; align-items: center; gap: 4px; color: var(--leaf-bright); font-size: 12px; }
.portal-card > footer { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; padding-top: 12px; border-top: 1px solid #ffffff0d; }
.portal-card > footer small { color: #7f8b81; font-size: 12px; }
.portal-roots { display: flex; flex-wrap: wrap; gap: 6px; }
.portal-roots span { display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; color: #6f7b72; font-size: 12px; border-radius: 99px; background: #ffffff08; }
.portal-roots span.met { color: var(--leaf-bright); background: #8fb26f14; }
@media (max-width: 760px) { .portal-grid { grid-template-columns: 1fr; }.portal-card { padding: 16px; } }
</style>
