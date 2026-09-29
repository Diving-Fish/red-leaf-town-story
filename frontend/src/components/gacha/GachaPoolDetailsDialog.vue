<script setup lang="ts">
import { computed } from 'vue'
import { Sparkles, Stamp } from 'lucide-vue-next'

import ModalSheet from '@/components/ModalSheet.vue'
import CroppedImage from '@/components/CroppedImage.vue'
import { rarityClass, rarityMeta } from '@/lib/rarity'
import type { GachaCatalogPartner, GachaPoolState } from '@/types'

const props = defineProps<{ open: boolean; pool: GachaPoolState | null }>()
defineEmits<{ (event: 'close'): void }>()

interface DetailRow extends GachaCatalogPartner {
  probability: number
  featured: boolean
}

interface RarityGroup {
  rarity: 3 | 4 | 5
  probability: number
  rows: DetailRow[]
}

const groups = computed<RarityGroup[]>(() => {
  const pool = props.pool
  if (!pool) return []
  const byRarity: Record<3 | 4 | 5, GachaCatalogPartner[]> = { 3: [], 4: [], 5: [] }
  for (const partner of pool.catalog) byRarity[partner.rarity].push(partner)

  const result: RarityGroup[] = []
  for (const rarity of [5, 4, 3] as const) {
    const partners = byRarity[rarity]
    if (!partners.length) continue
    const rarityProbability = pool.rarity_probabilities[rarity] || 0

    const featuredId = rarity === 5 ? pool.featured_partner_id : rarity === 4 ? pool.featured_four_star_partner_id : null
    const featuredRate = rarity === 5 ? pool.featured_rate : pool.featured_four_star_rate
    const featured = featuredId ? partners.find((entry) => entry.partner_id === featuredId) : undefined

    let rows: DetailRow[]
    if (featured) {
      const others = partners.filter((entry) => entry.partner_id !== featuredId)
      rows = others.length
        ? [
            { ...featured, probability: rarityProbability * featuredRate, featured: true },
            ...others.map((entry) => ({
              ...entry,
              probability: (rarityProbability * (1 - featuredRate)) / others.length,
              featured: false,
            })),
          ]
        : [{ ...featured, probability: rarityProbability, featured: true }]
    } else {
      rows = partners.map((entry) => ({ ...entry, probability: rarityProbability / partners.length, featured: false }))
    }

    rows.sort((a, b) => b.probability - a.probability)
    result.push({ rarity, probability: rarityProbability, rows })
  }
  return result
})

const itemProbability = computed(() => props.pool?.item_probability || 0)
const maxProbability = computed(() =>
  Math.max(...groups.value.flatMap((group) => group.rows.map((row) => row.probability)), 0.0001),
)

function pct(value: number) {
  return `${(value * 100).toFixed(3)}%`
}

function barWidth(value: number) {
  return `${Math.max(2, (value / maxProbability.value) * 100)}%`
}
</script>

<template>
  <ModalSheet :open="open" :title="pool?.title || '招募池'" subtitle="基础概率（不含保底）" @close="$emit('close')">
    <div v-if="pool" class="gacha-details">
      <p v-if="pool.featured_partner_id" class="ui-description">
        抽到非 UP 五星后，本池下一个五星必为 UP 角色（提前出五星也生效），获得 UP 后重置；各池独立计算。
        <strong v-if="pool.featured_guaranteed">当前下个五星必出 UP。</strong>
      </p>
      <p v-if="pool.featured_four_star_partner_id" class="ui-description">
        抽到四星时，有 {{ (pool.featured_four_star_rate * 100).toFixed(0) }}% 为四星 UP 角色；四星 UP 不设保底。
      </p>
      <div class="gacha-details-summary">
        <span v-for="group in groups" :key="`sum:${group.rarity}`" class="gacha-details-summary-chip">
          <i class="rarity-chip" :class="rarityClass(group.rarity)">{{ rarityMeta(group.rarity).short }}★</i>{{ pct(group.probability) }}
        </span>
        <span v-if="itemProbability > 0" class="gacha-details-summary-chip item">道具 {{ pct(itemProbability) }}</span>
      </div>

      <div v-for="group in groups" :key="group.rarity" class="gacha-details-group">
        <p class="gacha-details-group-heading">
          <span class="gacha-details-group-title">
            <i class="rarity-chip" :class="rarityClass(group.rarity)">{{ rarityMeta(group.rarity).short }}★</i>
            {{ rarityMeta(group.rarity).label }}
          </span>
          <span class="gacha-details-group-total">合计 {{ pct(group.probability) }}</span>
        </p>

        <div v-for="row in group.rows" :key="row.partner_id" class="gacha-details-row">
          <div class="gacha-details-avatar" :class="rarityClass(row.rarity)">
            <CroppedImage
              v-if="row.artwork?.url && row.avatar_crop"
              :image-url="row.artwork.url"
              :image-width="row.artwork.width"
              :image-height="row.artwork.height"
              :crop="row.avatar_crop"
              :alt="row.name"
            />
            <div v-else class="gacha-details-avatar-fallback"><Sparkles :size="16" /></div>
          </div>
          <div class="gacha-details-copy">
            <strong>
              {{ row.name }}
              <span v-if="row.featured" class="gacha-details-up"><Stamp :size="10" />UP</span>
            </strong>
            <div class="gacha-details-bar"><div class="gacha-details-bar-fill" :style="{ width: barWidth(row.probability) }" /></div>
          </div>
          <span class="gacha-details-pct">{{ pct(row.probability) }}</span>
        </div>
      </div>
    </div>
  </ModalSheet>
</template>

<style scoped>
.gacha-details-summary { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.gacha-details-summary-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  color: #c9d3c6;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #ffffff05;
}
.gacha-details-summary-chip.item { color: #91a090; }

.rarity-chip {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  font-style: normal;
  font-size: 10px;
  font-weight: 800;
  line-height: 1.6;
  border: 1px solid var(--line);
  border-radius: 6px;
}
.rarity-chip.rarity-3 { color: var(--rarity-3); border-color: color-mix(in srgb, var(--rarity-3) 55%, var(--line)); }
.rarity-chip.rarity-4 { color: var(--rarity-4); border-color: color-mix(in srgb, var(--rarity-4) 55%, var(--line)); }
.rarity-chip.rarity-5 { color: var(--rarity-5-a); border-color: color-mix(in srgb, var(--rarity-5-a) 55%, var(--line)); }

.gacha-details-group { margin-bottom: 16px; }
.gacha-details-group:last-child { margin-bottom: 0; }
.gacha-details-group-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
}
.gacha-details-group-title { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 700; }
.gacha-details-group-total { color: #8a9589; font-size: 11px; font-weight: 700; }

.gacha-details-row {
  display: grid;
  grid-template-columns: 34px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
}
.gacha-details-avatar {
  overflow: hidden;
  width: 34px;
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #0d1410;
}
.gacha-details-avatar :deep(img),
.gacha-details-avatar :deep(svg.cropped-image) { display: block; width: 100%; height: 100%; }
.gacha-details-avatar.rarity-3 { border-color: color-mix(in srgb, var(--rarity-3) 55%, var(--line)); }
.gacha-details-avatar.rarity-4 { border-color: color-mix(in srgb, var(--rarity-4) 55%, var(--line)); }
.gacha-details-avatar.rarity-5 { border-color: color-mix(in srgb, var(--rarity-5-a) 55%, var(--line)); }
.gacha-details-avatar-fallback { display: grid; place-items: center; width: 100%; height: 100%; color: #6f7d72; }
.gacha-details-copy { min-width: 0; }
.gacha-details-copy strong {
  display: flex;
  align-items: center;
  gap: 5px;
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gacha-details-up {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 1px 5px;
  color: #2a1608;
  font-size: 9px;
  font-weight: 800;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--rarity-5-a), var(--rarity-5-b));
}
.gacha-details-bar { height: 4px; margin-top: 5px; border-radius: 999px; background: #ffffff0a; overflow: hidden; }
.gacha-details-bar-fill { height: 100%; border-radius: 999px; background: var(--gold); }
.gacha-details-pct { color: #e6dcc0; font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
</style>
