<script setup lang="ts">
import { computed } from 'vue'
import { UserRound } from 'lucide-vue-next'

import CroppedImage from '@/components/CroppedImage.vue'
import type { CropRect, PartnerArtwork } from '@/types'

const props = withDefaults(
  defineProps<{ artwork?: PartnerArtwork | null; crop?: CropRect | null; name?: string; size?: number }>(),
  { size: 34 },
)

const radius = computed(() => `${Math.round(props.size * 0.27)}px ${Math.round(props.size * 0.09)}px`)
</script>

<template>
  <span class="partner-avatar" :style="{ width: `${size}px`, height: `${size}px`, borderRadius: radius }">
    <CroppedImage
      v-if="artwork?.url && crop"
      :image-url="artwork.url"
      :image-width="artwork.width"
      :image-height="artwork.height"
      :crop="crop"
      :alt="`${name || '伙伴'}头像`"
    />
    <slot v-else><UserRound :size="Math.round(size * 0.48)" /></slot>
  </span>
</template>

<style scoped>
.partner-avatar { flex: 0 0 auto; overflow: hidden; display: grid; place-items: center; color: #9fbc86; background: #243128; }
</style>
