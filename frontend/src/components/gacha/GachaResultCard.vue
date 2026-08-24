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
  defineProps<{ drop: GachaDrop; meta: GachaResultMeta; revealed: boolean; instant?: boolean; big?: boolean }>(),
  { instant: false, big: false },
)

const isPartner = computed(() => props.drop.kind === 'partner')
const isFive = computed(() => isPartner.value && normalizeRarity(props.meta.rarity) === 5)
</script>

<template>
  <div class="result-card" :class="{ big }">
    <div class="result-card-flip" :class="{ revealed, instant }">
      <div class="result-card-face result-card-back">
        <span class="result-card-seal"><Sparkles :size="big ? 30 : 18" /></span>
      </div>

      <div class="result-card-face result-card-front" :class="{ 'is-five': revealed && isFive }">
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

        <div class="result-card-caption">
          <strong>{{ meta.name }}</strong>
          <small v-if="isPartner && drop.duplicate"><Stamp :size="11" />印记 +{{ drop.companion_marks }}</small>
          <small v-else-if="isPartner">新伙伴加入</small>
          <small v-else>特殊道具 ×{{ drop.quantity }}</small>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.result-card { width: 100%; }
.result-card.big { max-width: 240px; margin: 0 auto; }
.result-card-flip {
  position: relative;
  width: 100%;
  aspect-ratio: 3 / 4;
  transform-style: preserve-3d;
  transition: transform .6s cubic-bezier(.2, .8, .2, 1);
}
.result-card-flip.instant { transition: none; }
.result-card-flip.revealed { transform: rotateY(180deg); }
.result-card-face { position: absolute; inset: 0; backface-visibility: hidden; -webkit-backface-visibility: hidden; }
.result-card-back {
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 20px 6px 20px 6px;
  background: linear-gradient(155deg, #1c2820, #12190f);
  color: var(--gold);
}
.result-card-back::before {
  content: '';
  position: absolute;
  inset: 8px;
  border: 1px dashed rgba(215, 173, 88, .35);
  border-radius: 15px 5px;
}
.result-card-front { transform: rotateY(180deg); display: flex; flex-direction: column; gap: 6px; }
.result-card-front.is-five :deep(.rarity-frame) { animation: result-pop .5s ease; }
.result-card-fallback, .result-card-item {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: #6f7d72;
}
.result-card-item {
  border: 1px solid var(--line);
  border-radius: 20px 6px 20px 6px;
  color: var(--gold);
  background: linear-gradient(155deg, #26301f, #171d17);
}
.result-card-caption { text-align: center; }
.result-card-caption strong { display: block; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-card-caption small { display: flex; align-items: center; justify-content: center; gap: 3px; margin-top: 2px; color: #849087; font-size: 10px; }
.result-card.big .result-card-caption strong { font-size: 15px; }
.result-card.big .result-card-caption small { font-size: 12px; }
</style>
