<script setup lang="ts">
import { computed } from 'vue'

import type { StoryPortraitState } from '@/stores/story'
import type { StoryPortraitSlot } from '@/types'

const props = defineProps<{ side: StoryPortraitSlot; state: StoryPortraitState | null }>()

const style = computed(() => ({
  '--portrait-scale': String(props.state?.scale ?? 1),
  '--portrait-offset-x': `${(props.state?.offsetX ?? 0) * 100}%`,
  '--portrait-offset-y': `${(props.state?.offsetY ?? 0) * 100}%`,
}))
</script>

<template>
  <Transition name="story-portrait">
    <figure
      v-if="state?.asset?.url"
      class="story-portrait"
      :class="`story-portrait--${side}`"
      :style="style"
    >
      <img :src="state.asset.url" :alt="state.asset.name" draggable="false" />
    </figure>
  </Transition>
</template>

<style scoped>
.story-portrait {
  position: absolute;
  bottom: 0;
  margin: 0;
  /* scale 直接换算成高度，脚下的基线不动；offset 只负责平移。 */
  height: calc(var(--portrait-base, 100%) * var(--portrait-scale));
  pointer-events: none;
  transform: translate(var(--portrait-offset-x), var(--portrait-offset-y));
}
.story-portrait--left { left: 2%; }
.story-portrait--right { right: 2%; }
.story-portrait img { display: block; height: 100%; width: auto; object-fit: contain; }
.story-portrait-enter-active, .story-portrait-leave-active { transition: opacity .28s ease, transform .28s ease; }
.story-portrait-enter-from, .story-portrait-leave-to {
  opacity: 0;
  transform: translate(var(--portrait-offset-x), calc(var(--portrait-offset-y) + 12px));
}
</style>
