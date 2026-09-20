<script setup lang="ts">
import { computed } from 'vue'

import type { StoryPortraitState } from '@/lib/story-stage'
import type { StoryPortraitSlot } from '@/types'

const props = defineProps<{ side: StoryPortraitSlot; state: StoryPortraitState | null }>()

const style = computed(() => ({
  '--portrait-scale': String(props.state?.scale ?? 1),
  '--portrait-offset-x': `${(props.state?.offsetX ?? 0) * 100}%`,
  '--portrait-offset-y': `${(props.state?.offsetY ?? 0) * 100}%`,
  '--portrait-flip': props.state?.flip ? '-1' : '1',
  '--portrait-duration': `${props.state?.duration ?? 0.28}s`,
}))
// 从外侧滑入：right 槽从右边来，left 和 center 从左边来（center 位移小一些）。
const enterShift = computed(() => {
  if (props.side === 'right') return '18%'
  return props.side === 'center' ? '-12%' : '-18%'
})
const name = computed(() => `story-portrait-${props.state?.transition || 'fade'}`)
</script>

<template>
  <Transition :name="name">
    <figure
      v-if="state?.asset?.url"
      class="story-portrait"
      :class="`story-portrait--${side}`"
      :style="{ ...style, '--portrait-enter-shift': enterShift }"
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
  /* --portrait-anchor 只有居中槽用：把自己往回挪半个身位 */
  transform: translate(calc(var(--portrait-anchor, 0%) + var(--portrait-offset-x)), var(--portrait-offset-y));
}
.story-portrait--left { left: 2%; }
.story-portrait--right { right: 2%; }
.story-portrait--center { left: 50%; --portrait-anchor: -50%; }
.story-portrait img {
  display: block;
  height: 100%;
  width: auto;
  object-fit: contain;
  transform: scaleX(var(--portrait-flip));
}

.story-portrait-fade-enter-active,
.story-portrait-fade-leave-active,
.story-portrait-slide-enter-active,
.story-portrait-slide-leave-active {
  transition: opacity var(--portrait-duration) ease, transform var(--portrait-duration) ease;
}
.story-portrait-fade-enter-from,
.story-portrait-fade-leave-to {
  opacity: 0;
  transform: translate(calc(var(--portrait-anchor, 0%) + var(--portrait-offset-x)), calc(var(--portrait-offset-y) + 12px));
}
.story-portrait-slide-enter-from,
.story-portrait-slide-leave-to {
  opacity: 0;
  transform: translate(calc(var(--portrait-anchor, 0%) + var(--portrait-offset-x) + var(--portrait-enter-shift)), var(--portrait-offset-y));
}

@media (prefers-reduced-motion: reduce) {
  .story-portrait-fade-enter-active,
  .story-portrait-fade-leave-active,
  .story-portrait-slide-enter-active,
  .story-portrait-slide-leave-active { transition-duration: .01ms; }
}
</style>
