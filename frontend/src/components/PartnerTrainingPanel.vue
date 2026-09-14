<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, BookOpen, Check, Gem, Star } from 'lucide-vue-next'
import ActionButton from '@/components/ActionButton.vue'
import QuantityStepper from '@/components/QuantityStepper.vue'
import ProgressBar from '@/components/ProgressBar.vue'
import GameIcon from '@/components/GameIcon.vue'
import PartnerAscensionPanel from '@/components/PartnerAscensionPanel.vue'
import { useGameStore } from '@/stores/game'
import type { OwnedPartner } from '@/types'

const props = defineProps<{ partner: OwnedPartner }>()
const game = useGameStore()
const tabs = [
  { id: 'experience', label: '升级', icon: BookOpen },
  { id: 'ascension', label: '突破', icon: Gem },
  { id: 'stars', label: '升星', icon: Star },
] as const
const activeTab = ref<string>('experience')
const selectedBook = ref('')
const books = computed(() => game.state?.partner_growth.experience_books || [])
const book = computed(() => books.value.find(item => item.item_id === selectedBook.value) || books.value.find(item => item.owned > 0) || books.value[0])
const quantity = ref(1)
const maxQuantity = computed(() => Math.min(99, book.value?.owned || 0))
watch(() => book.value?.item_id, () => { quantity.value = 1 })
watch(maxQuantity, max => { quantity.value = Math.max(1, Math.min(quantity.value, max)) })
const experienceGain = computed(() => (book.value?.experience || 0) * Math.min(quantity.value, maxQuantity.value))
const preview = computed(() => {
  let level = props.partner.level
  let experience = props.partner.experience + experienceGain.value
  const cap = props.partner.level_cap || 20
  const costs = game.state?.partner_growth.level_experience_costs || {}
  while (level < cap && costs[level] && experience >= costs[level]!) {
    experience -= costs[level]!
    level += 1
  }
  const cost = level < cap ? costs[level] : undefined
  return { level, experience, cost, capped: level >= cap }
})
const currentProgress = computed(() => props.partner.experience_to_next_level ? Math.min(100, props.partner.experience / props.partner.experience_to_next_level * 100) : 100)
const previewProgress = computed(() => preview.value.cost ? Math.min(100, preview.value.experience / preview.value.cost * 100) : 100)
const marks = computed(() => game.player?.companion_marks || 0)
const stars = computed(() => props.partner.stars || props.partner.rarity || 3)
const starReady = computed(() => props.partner.star_up_available && marks.value >= (props.partner.star_up_cost || 0))

function moveTab(event: KeyboardEvent, index: number) {
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : -1
  if (next < 0) return
  event.preventDefault()
  activeTab.value = tabs[next]!.id
  const list = (event.currentTarget as HTMLElement).parentElement
  ;(list?.children[next] as HTMLButtonElement)?.focus()
}
</script>

<template>
  <section class="partner-training">
    <div class="training-tabs" role="tablist" aria-label="伙伴培养">
      <button v-for="(tab, index) in tabs" :id="`training-tab-${tab.id}`" :key="tab.id" role="tab" :aria-selected="activeTab === tab.id" :aria-controls="`training-panel-${tab.id}`" :tabindex="activeTab === tab.id ? 0 : -1" @click="activeTab = tab.id" @keydown="moveTab($event, index)">
        <component :is="tab.icon" :size="16" /><span>{{ tab.label }}</span>
      </button>
    </div>

    <div v-show="activeTab === 'experience'" id="training-panel-experience" class="training-panel" role="tabpanel" aria-labelledby="training-tab-experience" tabindex="0">
      <div class="training-heading"><span class="training-symbol"><BookOpen :size="23" /></span><div><p>伙伴成长</p><h3>伙伴升级</h3></div><span class="training-badge">Lv.{{ partner.level }} / {{ partner.level_cap }}</span></div>
      <div class="experience-preview" aria-live="polite">
        <div><span>当前 · Lv.{{ partner.level }}</span><strong>{{ partner.experience.toLocaleString() }}<small>{{ partner.experience_to_next_level ? ` / ${partner.experience_to_next_level.toLocaleString()}` : ' · 留存经验' }}</small></strong><ProgressBar :value="currentProgress" :height="5" /></div>
        <ArrowRight :size="16" />
        <div><span>使用后 · Lv.{{ preview.level }}</span><strong>{{ preview.experience.toLocaleString() }}<small>{{ preview.cost ? ` / ${preview.cost.toLocaleString()}` : ' · 留存经验' }}</small></strong><ProgressBar :value="previewProgress" :height="5" /></div>
      </div>
      <p class="training-description">经验 +{{ experienceGain.toLocaleString() }}<template v-if="preview.level > partner.level"> · 提升 {{ preview.level - partner.level }} 级</template><template v-if="preview.capped"> · 达到等级上限，溢出经验保留</template></p>
      <div class="book-options" role="group" aria-label="选择经验书">
        <button v-for="item in books" :key="item.item_id" :aria-pressed="book?.item_id === item.item_id" @click="selectedBook = item.item_id">
          <GameIcon :name="item.item.icon" :size="23" /><span><strong>{{ item.item.name }}</strong><small>经验 +{{ item.experience }}</small></span><span class="book-stock">×{{ item.owned }}<Check v-if="book?.item_id === item.item_id" :size="14" /></span>
        </button>
      </div>
      <div class="book-quantity"><span>使用数量</span><QuantityStepper v-model="quantity" :max="Math.max(1, maxQuantity)" :disabled="!maxQuantity || game.isPendingPrefix(`partner:${partner.partner_id}:`)" /><button class="text-button" :disabled="!maxQuantity || game.isPendingPrefix(`partner:${partner.partner_id}:`)" @click="quantity = maxQuantity">最多</button></div>
      <div class="training-footer"><small>{{ book ? `持有 ${book.owned} 本 · 本次使用 ${Math.min(quantity, maxQuantity)} 本` : '暂无可用札记' }}</small><ActionButton :action-key="`partner:${partner.partner_id}:train:${book?.item_id || ''}`" :group="`partner:${partner.partner_id}:`" :disabled="!maxQuantity" :reason="!maxQuantity ? '仓库里没有这本札记' : undefined" @click="book && game.trainPartner(partner.partner_id, book.item_id, quantity)">使用札记 <ArrowRight :size="15" /></ActionButton></div>
    </div>

    <div v-show="activeTab === 'ascension'" id="training-panel-ascension" class="training-panel" role="tabpanel" aria-labelledby="training-tab-ascension" tabindex="0">
      <PartnerAscensionPanel :partner="partner" />
    </div>

    <div v-show="activeTab === 'stars'" id="training-panel-stars" class="training-panel" role="tabpanel" aria-labelledby="training-tab-stars" tabindex="0">
      <div class="training-heading"><span class="training-symbol"><Star :size="23" /></span><div><p>星级成长</p><h3>{{ partner.star_up_available ? '伙伴升星' : '已达到五星' }}</h3></div><span class="training-badge">{{ stars }} 星<template v-if="partner.star_up_available"><ArrowRight :size="12" />{{ stars + 1 }} 星</template></span></div>
      <p class="training-description">{{ partner.star_up_available ? '以同行印记，点亮下一颗星。' : '五颗星已全部点亮。' }}</p>
      <div class="training-stars" aria-hidden="true"><Star v-for="index in 5" :key="index" :size="25" :class="{ lit: index <= stars, next: partner.star_up_available && index === stars + 1 }" /></div>
      <div v-if="partner.star_up_available" class="star-material"><span><Star :size="20" />同行印记</span><strong :class="{ enough: starReady }">{{ marks.toLocaleString() }} <small>/ {{ partner.star_up_cost?.toLocaleString() }}</small></strong></div>
      <div class="training-footer"><small>{{ partner.star_up_available ? (starReady ? '材料已备齐' : `还差 ${(partner.star_up_cost || 0) - marks} 枚同行印记`) : '当前星级已满' }}</small><ActionButton :action-key="`partner:${partner.partner_id}:star-up`" :group="`partner:${partner.partner_id}:`" :disabled="!starReady" :reason="!starReady ? (partner.star_up_available ? '同行印记不足' : '已达到五星') : undefined" @click="game.starUpPartner(partner.partner_id)">确认升星 <ArrowRight :size="15" /></ActionButton></div>
    </div>
  </section>
</template>

<style scoped>
.partner-training { margin: 0; overflow: hidden; border: 1px solid #c7af7045; border-radius: 18px 6px; background: radial-gradient(ellipse at top right, #bda05d12, transparent 75%), #ffffff03; }
.training-tabs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4px; padding: 6px; border-bottom: 1px solid var(--line); background: #0002; }
.training-tabs button { display: flex; align-items: center; justify-content: center; gap: 7px; min-height: 44px; padding: 8px 4px; border: 1px solid transparent; border-radius: 10px 4px; background: transparent; color: #99a598; font: inherit; font-size: 13px; cursor: pointer; }
.training-tabs button[aria-selected="true"] { color: #dfcf99; border-color: #c7af7045; background: #c7af7014; }
.training-tabs button:focus-visible, .book-options button:focus-visible { outline: 2px solid var(--leaf-bright); outline-offset: -2px; }
.training-panel { padding: 18px; min-width: 0; }
.training-heading { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.training-symbol { display: grid; place-items: center; width: 43px; height: 43px; flex-shrink: 0; color: #d7c58e; border: 1px solid #d7c58e38; border-radius: 13px; background: #d7c58e0c; }
.training-heading p { margin: 0 0 4px; color: #b6a477; font-size: 10px; letter-spacing: .14em; }
.training-heading h3 { margin: 0; font-size: 16px; font-family: 'Noto Serif SC', serif; }
.training-badge { display: flex; align-items: center; gap: 5px; margin-left: auto; color: #d8c796; font-size: 12px; }
.training-description { margin: 12px 0; color: #a4afa4; font-size: 12px; line-height: 1.6; }
.experience-preview { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); align-items: center; gap: 10px; margin-top: 16px; padding: 12px; border: 1px solid var(--line); border-radius: 10px; background: #0002; }
.experience-preview > div { display: grid; gap: 8px; min-width: 0; }
.experience-preview span { color: #a4afa4; font-size: 12px; }
.experience-preview strong { color: #d8c796; font-size: 15px; overflow-wrap: anywhere; }
.experience-preview small { color: #a4afa4; font-size: 11px; font-weight: normal; }
.experience-preview > svg { color: #a4afa4; }
.book-quantity { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
.book-quantity > span { margin-right: auto; color: #a4afa4; font-size: 12px; }
.book-options { display: grid; gap: 7px; }
.book-options button { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px; border: 1px solid var(--line); border-radius: 9px; background: #0002; color: #b4beb2; text-align: left; cursor: pointer; }
.book-options button[aria-pressed="true"] { border-color: #c7af7066; background: #c7af7010; }
.book-options strong, .book-options small { display: block; font-size: 12px; }
.book-options small { margin-top: 4px; color: #a4afa4; }
.book-stock { display: flex; align-items: center; gap: 6px; margin-left: auto; color: #d8c796; font-size: 12px; }
.training-stars { display: flex; justify-content: center; gap: 12px; padding: 14px 0 20px; color: #566052; }
.training-stars .lit { color: #d8c796; fill: #d8c796; }
.training-stars .next { color: #d8c796; }
.star-material, .star-material > span { display: flex; align-items: center; gap: 8px; }
.star-material { flex-wrap: wrap; justify-content: space-between; padding: 12px; border: 1px solid var(--line); border-radius: 9px; background: #0002; font-size: 12px; }
.star-material svg { color: #d8c796; }
.star-material small { color: #9aa799; font-weight: normal; }
.enough { color: var(--leaf-bright); }
.training-footer, :deep(.ascension-card-bottom) { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-top: 16px; }
.training-footer small { color: #9aa799; font-size: 12px; }
.training-footer :deep(button), :deep(.review-button) { display: flex; justify-content: center; align-items: center; gap: 8px; min-height: 44px; }
:deep(.ascension-card) { margin: 0; padding: 0; border: 0; border-radius: 0; background: none; }
:deep(.ascension-next) { margin: 0; min-height: 100px; align-items: center; justify-content: center; }
@media (max-width: 400px) { .training-panel { padding: 13px; }.training-tabs button { font-size: 12px; gap: 5px; }.training-footer :deep(button), :deep(.review-button) { width: 100%; } }
</style>
