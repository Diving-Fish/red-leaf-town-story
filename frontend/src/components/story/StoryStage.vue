<script setup lang="ts">
import { computed, ref } from 'vue'

import StoryPortrait from '@/components/story/StoryPortrait.vue'
import { BACKGROUND_DURATION, type StoryBackgroundState, type StoryCast } from '@/lib/story-stage'
import type { StoryDialogueStep, StoryMode } from '@/types'

const props = withDefaults(defineProps<{
  mode: StoryMode
  background: StoryBackgroundState | null
  portraits: StoryCast
  line: StoryDialogueStep | null
  /** 嵌在编辑器里时不铺满视口，由外层容器决定尺寸。 */
  embedded?: boolean
  /** 定格预览不需要那个一直在跳的推进箭头。 */
  hideCaret?: boolean
}>(), { embedded: false, hideCaret: false })

const frame = ref<HTMLElement | null>(null)
const speakerSide = computed(() => (props.line?.focus === 'right' ? 'right' : 'left'))
const duration = computed(() => {
  const state = props.background
  if (!state) return BACKGROUND_DURATION
  return state.transition === 'cut' ? 0 : state.duration
})

defineExpose({ frame })
</script>

<template>
  <div
    class="story-stage-root"
    :class="[`story-stage-root--${mode}`, { 'is-embedded': embedded }]"
    :style="{ '--background-duration': `${duration}s` }"
  >
    <div v-if="mode === 'stage'" ref="frame" class="story-stage">
      <Transition name="story-background">
        <img
          v-if="background?.asset?.url"
          :key="background.asset.id"
          class="story-background"
          :src="background.asset.url"
          :alt="background.asset.name"
          draggable="false"
        />
      </Transition>
      <div class="story-cast">
        <StoryPortrait side="left" :state="portraits.left" />
        <StoryPortrait side="center" :state="portraits.center" />
        <StoryPortrait side="right" :state="portraits.right" />
      </div>

      <div v-if="line" class="story-box" :class="`story-box--${speakerSide}`">
        <span v-if="line.speaker" class="story-speaker">{{ line.speaker }}</span>
        <p class="story-text" :class="{ 'story-text--aside': !line.speaker }">{{ line.text }}</p>
        <i v-if="!hideCaret" class="story-advance" />
      </div>
      <slot name="overlay" />
    </div>

    <div v-else ref="frame" class="story-inline">
      <StoryPortrait side="left" :state="portraits.left" />
      <StoryPortrait side="center" :state="portraits.center" />
      <div v-if="line" class="story-box" :class="`story-box--${speakerSide}`">
        <span v-if="line.speaker" class="story-speaker">{{ line.speaker }}</span>
        <p class="story-text" :class="{ 'story-text--aside': !line.speaker }">{{ line.text }}</p>
        <i v-if="!hideCaret" class="story-advance" />
      </div>
      <StoryPortrait side="right" :state="portraits.right" />
      <slot name="overlay" />
    </div>
  </div>
</template>

<style scoped>
.story-stage-root { width: 100%; height: 100%; }
.story-stage-root--stage { display: grid; place-items: center; }
.story-stage-root--inline { display: flex; align-items: flex-end; justify-content: center; }

.story-stage {
  --stage-width: min(100vw, calc(100dvh * 16 / 9));
  position: relative;
  width: var(--stage-width);
  height: calc(var(--stage-width) * 9 / 16);
  overflow: hidden;
  background: #0b0f0d;
  font-size: clamp(13px, calc(var(--stage-width) * .021), 23px);
  user-select: none;
}
/* 嵌进编辑器时改由外层容器定尺寸，16:9 靠 aspect-ratio 保住，字号跟着容器宽度走。 */
.story-stage-root.is-embedded { container-type: size; }
.is-embedded .story-stage {
  width: 100%;
  height: auto;
  aspect-ratio: 16 / 9;
  font-size: clamp(10px, 2.1cqi, 23px);
}
.story-background { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.story-cast { position: absolute; inset: 0; }

.story-box {
  position: absolute;
  left: 5%;
  right: 5%;
  bottom: 5%;
  min-height: 6.4em;
  padding: 1.1em 1.5em 1.3em;
  border: 1px solid rgba(236, 221, 187, .16);
  border-radius: 1.1em .3em 1.1em .3em;
  background: rgba(10, 15, 12, .82);
  backdrop-filter: blur(12px);
  box-shadow: 0 1.4em 3em rgba(0, 0, 0, .45);
}
.story-speaker {
  position: absolute;
  top: -1em;
  padding: .3em 1.1em;
  border: 1px solid rgba(224, 190, 116, .4);
  border-radius: .7em .2em .7em .2em;
  background: linear-gradient(140deg, #23301f, #16201a);
  color: var(--gold, #d6ad63);
  font-size: .82em;
  font-weight: 700;
  letter-spacing: .04em;
}
.story-box--left .story-speaker { left: 1.4em; }
.story-box--right .story-speaker { right: 1.4em; }
.story-text { margin: .35em 0 0; color: var(--cream, #ece6d9); font-size: 1em; line-height: 1.9; }
.story-text--aside { color: #cdd6cb; font-style: italic; }
.story-advance {
  position: absolute;
  right: 1.2em;
  bottom: .9em;
  width: .5em;
  height: .5em;
  border-right: 2px solid var(--gold, #d6ad63);
  border-bottom: 2px solid var(--gold, #d6ad63);
  transform: rotate(45deg);
  animation: story-advance 1.4s ease-in-out infinite;
}
@keyframes story-advance { 0%, 100% { opacity: .25; transform: rotate(45deg) translate(0, 0); } 50% { opacity: 1; transform: rotate(45deg) translate(.15em, .15em); } }

.story-inline {
  position: relative;
  width: min(940px, 100%);
  margin: 0 auto;
  padding: 0 12px var(--story-bottom, 22px);
  font-size: 14px;
  user-select: none;
}
/* 立绘不占对话框宽度，站在对话框后面，被半透明的对话框压住下半截。 */
.story-inline :deep(.story-portrait) {
  z-index: 0;
  bottom: var(--story-bottom, 22px);
  --portrait-base: min(40vh, 300px);
}
.is-embedded .story-inline :deep(.story-portrait) { --portrait-base: min(58cqh, 260px); }
.story-inline :deep(.story-portrait--left) { left: 10px; }
.story-inline :deep(.story-portrait--center) { left: 50%; }
.story-inline :deep(.story-portrait--right) { right: 10px; }
.story-inline .story-box {
  position: relative;
  z-index: 1;
  background: rgba(10, 15, 12, .78);
  left: auto;
  right: auto;
  bottom: auto;
  min-height: 0;
  padding: 15px 18px 17px;
  border-radius: 18px 5px 18px 5px;
}
.story-inline .story-speaker { top: -12px; font-size: 12px; }
.story-inline .story-text { font-size: 14px; line-height: 1.8; }
.story-inline .story-advance { right: 14px; bottom: 11px; width: 7px; height: 7px; }

.story-background-enter-active, .story-background-leave-active { transition: opacity var(--background-duration) ease; }
.story-background-enter-from, .story-background-leave-to { opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  .story-background-enter-active, .story-background-leave-active { transition-duration: .01ms; }
  .story-advance { animation: none; opacity: .7; }
}

@media (max-width: 760px) {
  .story-stage-root--inline:not(.is-embedded) { --story-bottom: calc(74px + env(safe-area-inset-bottom)); }
  .story-stage-root:not(.is-embedded) .story-inline :deep(.story-portrait) { --portrait-base: min(34vh, 220px); }
  .story-stage-root:not(.is-embedded) .story-inline .story-text { font-size: 13px; }
}
</style>
