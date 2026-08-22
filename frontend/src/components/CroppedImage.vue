<script setup lang="ts">
import { computed } from 'vue'

import type { CropRect } from '@/types'

const props = defineProps<{
  imageUrl: string
  imageWidth: number
  imageHeight: number
  crop: CropRect
  alt?: string
}>()

const viewBox = computed(() => `${props.crop.x} ${props.crop.y} ${props.crop.w} ${props.crop.h}`)
</script>

<template>
  <svg class="cropped-image" :viewBox="viewBox" preserveAspectRatio="xMidYMid slice" role="img" :aria-label="alt || '裁剪图片'">
    <image :href="imageUrl" x="0" y="0" :width="imageWidth" :height="imageHeight" />
  </svg>
</template>

<style scoped>
.cropped-image { display: block; width: 100%; height: 100%; }
</style>
