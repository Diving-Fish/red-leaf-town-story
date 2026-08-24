<script setup lang="ts">
import { computed } from 'vue'
import { Sparkles, Stamp } from 'lucide-vue-next'

import CroppedImage from '@/components/CroppedImage.vue'
import RarityFrame from '@/components/RarityFrame.vue'
import { normalizeRarity } from '@/lib/rarity'
import type { AvatarCrop, GachaDrop, PartnerArtwork } from '@/types'

export interface GachaResultMeta {
  name: string
  rarity: number | null
  artwork?: PartnerArtwork | null
  crop?: AvatarCrop | null
}

const props = withDefaults(
  defineProps<{
    drop: GachaDrop
    meta: GachaResultMeta
    revealed: boolean
    instant?: boolean
    big?: boolean
    charging?: boolean
    dealDelay?: number
    interactive?: boolean
  }>(),
  { instant: false, big: false, charging: false, dealDelay: 0, interactive: false },
)
const emit = defineEmits<{ (event: 'reveal'): void }>()

const isPartner = computed(() => props.drop.kind === 'partner')
/* tier 0 = 道具，没有星级；伙伴按 3/4/5 归一 */
const tier = computed(() => (isPartner.value ? normalizeRarity(props.meta.rarity) : 0))
const isFive = computed(() => tier.value === 5)
const sparkIndexes = [0, 1, 2, 3, 4, 5]

function activate() {
  if (props.interactive && !props.revealed) emit('reveal')
}
</script>

<template>
  <div
    class="result-card"
    :class="[`tier-${tier}`, { big, instant, revealed, charging, interactive: interactive && !revealed }]"
    :style="{ '--deal-delay': `${dealDelay}ms` }"
    @click="activate"
  >
    <div class="result-card-stage">
      <span class="result-card-burst" />
      <span class="result-card-ring" />

      <div class="result-card-flip">
        <div class="result-card-face result-card-back">
          <span class="result-card-seal"><Sparkles :size="big ? 30 : 18" /></span>
          <span class="result-card-back-sheen" />
        </div>

        <div class="result-card-face result-card-front">
          <RarityFrame v-if="isPartner" :rarity="meta.rarity" aspect="3 / 4" :badge-size="big ? 'md' : 'xs'">
            <CroppedImage
              v-if="meta.artwork?.url && meta.crop"
              :image-url="meta.artwork.url"
              :image-width="meta.artwork.width"
              :image-height="meta.artwork.height"
              :crop="meta.crop"
              :alt="meta.name"
            />
            <div v-else class="result-card-fallback"><Sparkles :size="big ? 34 : 22" /></div>
          </RarityFrame>
          <div v-else class="result-card-item">
            <Sparkles :size="big ? 34 : 22" />
          </div>
        </div>
      </div>

      <template v-if="isFive">
        <span v-for="i in sparkIndexes" :key="i" class="result-card-spark" :style="{ '--spark': i }" />
      </template>
    </div>

    <div class="result-card-caption">
      <strong>{{ meta.name }}</strong>
      <small v-if="isPartner && drop.duplicate"><Stamp :size="11" />印记 +{{ drop.companion_marks }}</small>
      <small v-else-if="isPartner">新伙伴加入</small>
      <small v-else>特殊道具 ×{{ drop.quantity }}</small>
    </div>
  </div>
</template>

<style scoped>
/* 每张卡的星级配色，供光晕 / 冲光 / 迸发共用 */
.result-card {
  --tier-a: var(--rarity-3);
  --tier-b: var(--rarity-3);
  --tier-soft: var(--rarity-3-soft);
  --card-radius: 20px 6px 20px 6px;
  width: 100%;
  animation: card-deal .52s cubic-bezier(.2, .9, .25, 1) var(--deal-delay) both;
}
.result-card.tier-0 { --tier-a: var(--gold); --tier-b: var(--gold); --tier-soft: rgba(215, 173, 88, .34); }
.result-card.tier-4 { --tier-a: var(--rarity-4); --tier-b: #d9c2ff; --tier-soft: var(--rarity-4-soft); }
.result-card.tier-5 { --tier-a: var(--rarity-5-a); --tier-b: var(--rarity-5-b); --tier-soft: var(--rarity-5-soft); }
.result-card.big { max-width: 240px; margin: 0 auto; }
.result-card.instant { animation: none; }
.result-card.interactive { cursor: pointer; }
/* 已翻开的高星抬到同层之上，迸发光不被邻卡裁切 */
.result-card.revealed.tier-5 { z-index: 3; }
.result-card.revealed.tier-4 { z-index: 2; }

/* 舞台：卡面与卡背共用的唯一尺寸基准（3/4），文案已移到舞台之外 */
.result-card-stage {
  position: relative;
  width: 100%;
  aspect-ratio: 3 / 4;
  perspective: 1100px;
}
.result-card.charging .result-card-stage { animation: card-charge .42s ease-in-out infinite alternate; }

.result-card-flip {
  position: relative;
  width: 100%;
  height: 100%;
  transform-style: preserve-3d;
  transition: transform .62s cubic-bezier(.3, .9, .25, 1);
}
.result-card.instant .result-card-flip { transition: none; }
.result-card.revealed .result-card-flip { transform: rotateY(180deg); }
.result-card.revealed.tier-5 .result-card-flip { animation: card-hero .75s cubic-bezier(.2, .9, .25, 1); }
.result-card.revealed.tier-4 .result-card-flip { animation: card-pop .5s cubic-bezier(.2, .9, .25, 1); }
.result-card.instant .result-card-flip { animation: none; }

.result-card-face {
  position: absolute;
  inset: 0;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

/* ── 卡背：与卡面同尺寸同圆角，翻面前不泄露星级 ── */
.result-card-back {
  overflow: hidden;
  display: grid;
  place-items: center;
  border: 3px solid var(--line);
  border-radius: var(--card-radius);
  background:
    radial-gradient(circle at 50% 38%, rgba(215, 173, 88, .13), transparent 58%),
    linear-gradient(155deg, #1c2820, #12190f);
  color: var(--gold);
}
.result-card-back::before {
  content: '';
  position: absolute;
  inset: 7px;
  border: 1px dashed rgba(215, 173, 88, .35);
  border-radius: 14px 4px 14px 4px;
}
.result-card-seal { position: relative; z-index: 1; display: grid; place-items: center; }
.result-card.charging .result-card-seal { animation: rarity-pulse .5s ease-in-out infinite; }
.result-card-back-sheen {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(115deg, transparent 40%, rgba(244, 238, 223, .1) 50%, transparent 60%);
  background-size: 240% 240%;
  animation: rarity-sheen 6s ease-in-out infinite;
}
/* 冲光：翻面前一刻卡背透出该星级的颜色（高星更亮） */
.result-card.charging .result-card-back {
  border-color: color-mix(in srgb, var(--tier-a) 62%, var(--line));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--tier-a) 30%, transparent) inset,
    0 0 26px var(--tier-soft), 0 0 64px var(--tier-soft);
}
.result-card.charging.tier-5 .result-card-back { box-shadow: 0 0 0 2px var(--tier-a) inset, 0 0 40px var(--tier-a), 0 0 110px var(--tier-b); }

/* ── 卡面：RarityFrame 撑满舞台，不再与文案抢高度 ── */
.result-card-front { transform: rotateY(180deg); }
.result-card-front :deep(.rarity-frame) { width: 100%; height: 100%; }
.result-card-fallback, .result-card-item { width: 100%; height: 100%; display: grid; place-items: center; color: #6f7d72; }
.result-card-item {
  border: 3px solid var(--line);
  border-radius: var(--card-radius);
  color: var(--gold);
  background: linear-gradient(155deg, #26301f, #171d17);
}

/* ── 翻开瞬间的迸发 / 冲击环 / 火星 ── */
.result-card-burst, .result-card-ring {
  position: absolute;
  left: 50%;
  top: 50%;
  pointer-events: none;
  opacity: 0;
  transform: translate(-50%, -50%);
}
.result-card-burst {
  width: 240%;
  aspect-ratio: 1;
  border-radius: 50%;
  background: radial-gradient(circle, var(--tier-a) 0%, var(--tier-soft) 32%, transparent 62%);
}
.result-card-ring {
  width: 100%;
  aspect-ratio: 1;
  border: 2px solid var(--tier-a);
  border-radius: 50%;
}
.result-card.revealed.tier-5 .result-card-burst { animation: card-burst .95s ease-out; }
.result-card.revealed.tier-5 .result-card-ring { animation: card-shock .8s cubic-bezier(.1, .7, .3, 1); }
.result-card.revealed.tier-4 .result-card-burst { animation: card-burst .7s ease-out; }
.result-card.instant .result-card-burst, .result-card.instant .result-card-ring { animation: none; }

.result-card-spark {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  pointer-events: none;
  opacity: 0;
  background: var(--rarity-5-a);
  box-shadow: 0 0 10px 2px var(--rarity-5-a);
  transform: translate(-50%, -50%);
}
.result-card.revealed .result-card-spark {
  animation: spark-fly .9s cubic-bezier(.15, .8, .3, 1) calc(var(--spark) * 40ms) both;
  rotate: calc(var(--spark) * 60deg);
}
.result-card.instant .result-card-spark { animation: none; }

/* ── 文案：在舞台之外，翻开后淡入；预留高度避免网格跳动 ── */
.result-card-caption {
  min-height: 30px;
  margin-top: 7px;
  text-align: center;
  opacity: 0;
  transition: opacity .3s ease .18s, transform .3s ease .18s;
  transform: translateY(4px);
}
.result-card.revealed .result-card-caption { opacity: 1; transform: none; }
.result-card.instant .result-card-caption { transition: none; }
.result-card-caption strong { display: block; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-card.tier-5 .result-card-caption strong { color: var(--rarity-5-a); text-shadow: 0 0 14px var(--rarity-5-soft); }
.result-card.tier-4 .result-card-caption strong { color: #d9c2ff; }
.result-card-caption small { display: flex; align-items: center; justify-content: center; gap: 3px; margin-top: 2px; color: #849087; font-size: 10px; }
.result-card.big .result-card-caption { min-height: 44px; }
.result-card.big .result-card-caption strong { font-size: 15px; }
.result-card.big .result-card-caption small { font-size: 12px; }

@keyframes card-deal {
  from { opacity: 0; transform: translateY(26px) scale(.86) rotate(-5deg); }
  to { opacity: 1; transform: none; }
}
@keyframes card-charge {
  from { transform: scale(1); }
  to { transform: scale(1.035); }
}
@keyframes card-pop {
  0% { transform: rotateY(180deg) scale(1); }
  55% { transform: rotateY(180deg) scale(1.07); }
  100% { transform: rotateY(180deg) scale(1); }
}
@keyframes card-hero {
  0% { transform: rotateY(180deg) scale(1); }
  40% { transform: rotateY(180deg) scale(1.16) translateY(-6px); }
  70% { transform: rotateY(180deg) scale(1.04) translateY(-2px); }
  100% { transform: rotateY(180deg) scale(1); }
}
@keyframes card-burst {
  0% { opacity: 0; transform: translate(-50%, -50%) scale(.2); }
  25% { opacity: .95; }
  100% { opacity: 0; transform: translate(-50%, -50%) scale(1.15); }
}
@keyframes card-shock {
  0% { opacity: .9; transform: translate(-50%, -50%) scale(.35); }
  100% { opacity: 0; transform: translate(-50%, -50%) scale(2.4); }
}
@keyframes spark-fly {
  0% { opacity: 0; translate: 0 0; scale: .4; }
  20% { opacity: 1; }
  100% { opacity: 0; translate: 0 -78px; scale: .7; }
}

@media (prefers-reduced-motion: reduce) {
  .result-card,
  .result-card-flip,
  .result-card .result-card-burst,
  .result-card .result-card-ring,
  .result-card .result-card-spark,
  .result-card-back-sheen,
  .result-card.charging .result-card-stage,
  .result-card.charging .result-card-seal { animation: none !important; }
  .result-card-flip { transition-duration: .2s; }
}
</style>
