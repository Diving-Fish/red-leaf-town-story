<script setup lang="ts">
import { computed, watch } from 'vue'
import { ArrowUpCircle, Sparkles, Star, WandSparkles } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'

import PartnerAvatar from '@/components/PartnerAvatar.vue'
import ActionButton from '@/components/ActionButton.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import StateBlock from '@/components/StateBlock.vue'
import ViewHeader from '@/components/ViewHeader.vue'
import { partnerAssignmentLabel } from '@/lib/partners'
import { useGameStore } from '@/stores/game'
import type { OwnedPartner } from '@/types'

const game = useGameStore()
const route = useRoute()
const router = useRouter()

const selected = computed(() => {
  const requested = String(route.params.partnerId || '')
  return game.state?.partners.find((partner) => partner.partner_id === requested) || game.state?.partners[0] || null
})
const experienceProgress = computed(() => {
  if (!selected.value?.experience_to_next_level) return 100
  return Math.min(100, selected.value.experience / selected.value.experience_to_next_level * 100)
})

watch(
  () => [route.params.partnerId, game.state?.partners.length] as const,
  () => {
    if (!route.params.partnerId && game.state?.partners[0]) {
      router.replace({ name: 'partners', params: { partnerId: game.state.partners[0].partner_id } })
    }
  },
  { immediate: true },
)

function acquiredDate(timestamp: number) {
  return new Date(timestamp * 1000).toLocaleDateString('zh-CN')
}

function breakthroughName(stage: number) {
  return stage === 0 ? '未突破' : `${stage} 次突破`
}

function assignmentLabel(partner: OwnedPartner) {
  return partnerAssignmentLabel(partner, game.state || null) || '未派驻'
}

function rosterSubtitle(partner: OwnedPartner) {
  const assignment = partnerAssignmentLabel(partner, game.state || null)
  return `Lv.${partner.level} · ${assignment || breakthroughName(partner.breakthrough)}`
}
</script>

<template>
  <section v-if="game.state" class="view-section partner-view">
    <ViewHeader eyebrow="PARTNER ARCHIVE" title="伙伴仓库">
      <template #chip><Sparkles :size="18" /> {{ game.state.partner_count }} 位伙伴</template>
    </ViewHeader>

    <StateBlock
      v-if="!game.state.partners.length"
      :icon="WandSparkles"
      title="还没有伙伴来到这里"
    />

    <div v-else class="partner-warehouse">
      <aside class="partner-roster">
        <p>我的伙伴</p>
        <RouterLink
          v-for="partner in game.state.partners"
          :key="partner.partner_id"
          :to="{ name: 'partners', params: { partnerId: partner.partner_id } }"
          :class="{ active: selected?.partner_id === partner.partner_id }"
        >
          <PartnerAvatar :artwork="partner.artwork" :crop="partner.avatar_crop" :name="partner.name" :size="43" />
          <span><strong>{{ partner.name }}</strong><small>{{ rosterSubtitle(partner) }}</small></span>
          <i>{{ partner.stars ? `${partner.stars}★` : '?' }}</i>
        </RouterLink>
      </aside>

      <article v-if="selected" class="partner-detail">
        <div class="partner-illustration">
          <img v-if="selected.artwork?.url" :src="selected.artwork.url" :alt="selected.name" />
          <div v-else><Sparkles :size="46" /><span>暂无当前形态插画</span></div>
          <span class="rarity-ribbon"><Star :size="14" fill="currentColor" />{{ selected.stars || selected.rarity || '?' }} 星</span>
        </div>

        <div class="partner-profile">
          <p class="eyebrow">{{ selected.partner_id }}</p>
          <div class="profile-title"><h2>{{ selected.name }}</h2><span>Lv.{{ selected.level }} / {{ selected.level_cap || 20 }}</span></div>
          <p class="partner-description">{{ selected.description || '这位伙伴的故事尚未记录。' }}</p>

          <div class="partner-xp">
            <span><strong>伙伴经验 {{ selected.experience }}{{ selected.experience_to_next_level ? ` / ${selected.experience_to_next_level}` : '' }}</strong><small>{{ selected.experience_to_next_level ? '距离下一级' : '当前突破阶段已满级，溢出经验会保留' }}</small></span>
            <ProgressBar :value="experienceProgress" :height="7" />
          </div>

          <div class="profile-meta">
            <span><small>突破阶段</small><strong>{{ breakthroughName(selected.breakthrough) }}</strong></span>
            <span><small>成长曲线</small><strong>{{ selected.growth_curve_name || '—' }}</strong></span>
            <span><small>结缘日期</small><strong>{{ acquiredDate(selected.acquired_at) }}</strong></span>
            <span><small>当前派驻</small><strong>{{ assignmentLabel(selected) }}</strong></span>
          </div>

          <section class="profile-section">
            <h3>产业倾向</h3>
            <div class="tendency-list">
              <div v-for="tendency in selected.tendencies || []" :key="tendency.industry">
                <span>{{ tendency.name }}</span><strong>{{ tendency.current_ability }}</strong><small>当前能力</small>
              </div>
            </div>
          </section>

          <section class="profile-section">
            <h3>特性</h3>
            <div v-if="selected.traits?.length" class="owned-traits">
              <div v-for="trait in selected.traits" :key="trait.code"><strong>{{ trait.name }}</strong><span>{{ trait.description }}</span></div>
            </div>
            <p v-else class="section-placeholder">当前没有已配置特性。</p>
          </section>

          <section class="profile-section">
            <h3>培养</h3>
            <div class="training-books">
              <ActionButton
                v-for="book in game.state.partner_growth.experience_books"
                :key="book.item_id"
                variant="secondary"
                :action-key="`partner:${selected.partner_id}:train:${book.item_id}`"
                :disabled="!book.owned"
                reason="仓库里没有这本札记"
                @click="game.trainPartner(selected.partner_id, book.item_id)"
              ><ArrowUpCircle :size="16" />{{ book.item.name }} ×{{ book.owned }}</ActionButton>
            </div>
          </section>

          <div class="reserved-actions">
            <ActionButton
              :action-key="`partner:${selected.partner_id}:star-up`"
              :disabled="!selected.star_up_available || (game.player?.companion_marks || 0) < (selected.star_up_cost || 0)"
              :reason="selected.star_up_available ? '同行印记不足' : '已达到五星'"
              @click="game.starUpPartner(selected.partner_id)"
            ><Star :size="17" /><span><strong>升星</strong><small>{{ selected.star_up_available ? `消耗 ${selected.star_up_cost} 同行印记` : '已达到五星' }}</small></span></ActionButton>
            <ActionButton
              :action-key="`partner:${selected.partner_id}:breakthrough`"
              :disabled="!selected.breakthrough_available"
              :reason="selected.breakthrough_reason || undefined"
              @click="game.breakthroughPartner(selected.partner_id)"
            ><WandSparkles :size="17" /><span><strong>突破</strong><small>{{ selected.breakthrough_reason || `突破至阶段 ${selected.breakthrough + 1}` }}</small></span></ActionButton>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.partner-warehouse {
  /* 顶栏 72 + 等级条 34；未滚动时列表上方还有页面内边距与标题块，滚动条高度按最紧的那一刻算 */
  --roster-top: 106px;
  --roster-lead: 152px;
  display: grid; grid-template-columns: 245px minmax(0, 1fr); gap: 16px; align-items: start;
}
.partner-roster { position: sticky; top: var(--roster-top); max-height: calc(100vh - var(--roster-top) - var(--roster-lead)); overflow-y: auto; overscroll-behavior: contain; padding: 13px; border: 1px solid var(--line); border-radius: 19px 6px; background: var(--surface); }.partner-roster > p { position: sticky; top: -13px; z-index: 1; margin: 0 7px 13px; padding: 4px 0 6px; color: #77837a; font-size: 12px; font-weight: 800; letter-spacing: .12em; background: var(--surface); }.partner-roster a { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 9px; padding: 9px; margin-top: 4px; border: 1px solid transparent; border-radius: 11px; }.partner-roster a.active { border-color: #9abb7833; background: #9abb7811; }.partner-roster strong,.partner-roster small { display: block; }.partner-roster strong { font-size: 12px; }.partner-roster small { margin-top: 3px; color: #768178; font-size: 12px; }.partner-roster i { color: var(--gold); font-size: 12px; font-style: normal; }
.partner-detail { min-width: 0; display: grid; grid-template-columns: minmax(230px, 330px) minmax(0, 1fr); gap: clamp(24px, 4vw, 48px); padding: clamp(18px, 3vw, 34px); border: 1px solid var(--line); border-radius: 25px 8px; background: linear-gradient(145deg, #1b271f, #151e19); }.partner-illustration { position: relative; width: 100%; overflow: hidden; aspect-ratio: 9 / 16; display: grid; place-items: center; color: #708078; border-radius: 22px 7px; background: #0d1410; box-shadow: 0 22px 60px #0005; }.partner-illustration > img { width: 100%; height: 100%; object-fit: cover; }.partner-illustration > div { display: grid; place-items: center; gap: 9px; font-size: 12px; }.rarity-ribbon { position: absolute; left: 12px; top: 12px; display: flex; align-items: center; gap: 4px; padding: 6px 9px; color: #2a2113; font-size: 12px; font-weight: 800; border-radius: 99px; background: #e2bd6f; }
.partner-profile { padding: 10px 0; }.partner-profile > .eyebrow { margin: 0; }.profile-title { display: flex; align-items: baseline; gap: 13px; }.profile-title h2 { margin: 5px 0 0; font: 700 clamp(2rem, 4vw, 3rem) Georgia, 'Noto Serif SC', serif; }.profile-title > span { color: var(--leaf-bright); font-weight: 700; }.partner-description { max-width: 620px; margin: 16px 0 22px; color: #9ba69c; font-size: 13px; line-height: 1.8; }.profile-meta { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }.profile-meta > span { padding: 11px; border: 1px solid var(--line); border-radius: 10px; background: #ffffff04; }.profile-meta small,.profile-meta strong { display: block; }.profile-meta small { color: #6f7b72; font-size: 12px; }.profile-meta strong { margin-top: 4px; font-size: 12px; }
.profile-section { margin-top: 25px; }.profile-section h3 { margin: 0 0 10px; font-size: 13px; }.tendency-list { display: grid; grid-template-columns: repeat(3, minmax(100px, 1fr)); gap: 8px; }.tendency-list > div { display: grid; grid-template-columns: 1fr auto; align-items: end; padding: 11px; border: 1px solid #87a96b24; border-radius: 10px; background: #87a96b0b; }.tendency-list span { font-size: 12px; }.tendency-list strong { color: var(--leaf-bright); font-size: 17px; }.tendency-list small { grid-column: 1 / -1; margin-top: 3px; color: #6e7a71; font-size: 12px; }.owned-traits { display: grid; gap: 7px; }.owned-traits > div { padding: 10px 12px; border-left: 2px solid var(--gold); background: #ffffff04; }.owned-traits strong,.owned-traits span { display: block; }.owned-traits strong { font-size: 12px; }.owned-traits span { margin-top: 4px; color: #7e8a81; font-size: 12px; }.section-placeholder { color: #707c73; font-size: 12px; }
.partner-xp { display: grid; gap: 8px; margin: 18px 0; }.partner-xp > span { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; }.partner-xp small { color: #7e8a81; }.training-books { display: flex; flex-wrap: wrap; gap: 7px; }.training-books :deep(button) { display: flex; align-items: center; gap: 6px; }.reserved-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 28px; }.reserved-actions :deep(button) { min-height: 53px; display: flex; align-items: center; gap: 9px; padding: 0 13px; text-align: left; }.reserved-actions span { flex: 1; }.reserved-actions strong,.reserved-actions small { display: block; }.reserved-actions small { margin-top: 2px; font-size: 12px; }
@media (max-width: 900px) { .partner-warehouse { grid-template-columns: 1fr; }.partner-roster { position: static; max-height: none; display: flex; overflow-x: auto; }.partner-roster > p { display: none; }.partner-roster a { min-width: 205px; }.partner-detail { grid-template-columns: minmax(190px, 270px) 1fr; } }
@media (max-width: 650px) { .partner-detail { grid-template-columns: 1fr; }.partner-illustration { width: min(280px, 100%); margin: auto; }.profile-meta { grid-template-columns: 1fr 1fr; }.tendency-list { grid-template-columns: 1fr 1fr; } }
</style>
