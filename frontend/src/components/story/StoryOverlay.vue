<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RotateCw, SkipForward } from 'lucide-vue-next'

import StoryPortrait from '@/components/story/StoryPortrait.vue'
import { useLandscapeStage } from '@/composables/useLandscapeStage'
import { useStoryStore } from '@/stores/story'

const story = useStoryStore()
const stage = ref<HTMLElement | null>(null)
const { isPortrait, isTouch, lockLandscape, releaseLandscape } = useLandscapeStage()

const onStage = computed(() => story.active && story.mode === 'stage')
const needsRotation = computed(() => onStage.value && isTouch.value && isPortrait.value)
const speakerSide = computed(() => (story.focus === 'right' ? 'right' : 'left'))

watch(onStage, async (staged) => {
  if (!staged) {
    await releaseLandscape()
    return
  }
  await nextTick()
  await lockLandscape(stage.value)
})

function advance() {
  if (needsRotation.value || story.locked) return
  story.advance()
}

function onKey(event: KeyboardEvent) {
  if (!story.active || story.locked) return
  if (event.key === 'Escape') {
    story.skip()
    return
  }
  if (event.key === ' ' || event.key === 'Enter') {
    event.preventDefault()
    advance()
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  releaseLandscape()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="story-layer">
      <div v-if="story.active" class="story-layer" :class="`story-layer--${story.mode}`" @click="advance">
        <div v-if="onStage" ref="stage" class="story-stage">
          <Transition name="story-background">
            <img v-if="story.background?.url" :key="story.background.id" class="story-background" :src="story.background.url" :alt="story.background.name" draggable="false" />
          </Transition>
          <div class="story-cast">
            <StoryPortrait side="left" :state="story.portraits.left" />
            <StoryPortrait side="right" :state="story.portraits.right" />
          </div>

          <div v-if="story.line" class="story-box" :class="`story-box--${speakerSide}`">
            <span v-if="story.speaker" class="story-speaker">{{ story.speaker }}</span>
            <p class="story-text" :class="{ 'story-text--aside': !story.speaker }">{{ story.line.text }}</p>
            <i class="story-advance" />
          </div>

          <button class="story-skip" type="button" @click.stop="story.skip()">
            <SkipForward :size="15" />跳过
          </button>
        </div>

        <div v-else class="story-inline">
          <StoryPortrait side="left" :state="story.portraits.left" />
          <div v-if="story.line" class="story-box" :class="`story-box--${speakerSide}`">
            <span v-if="story.speaker" class="story-speaker">{{ story.speaker }}</span>
            <p class="story-text" :class="{ 'story-text--aside': !story.speaker }">{{ story.line.text }}</p>
            <i class="story-advance" />
          </div>
          <StoryPortrait side="right" :state="story.portraits.right" />
          <button class="story-skip" type="button" @click.stop="story.skip()">
            <SkipForward :size="14" />跳过
          </button>
        </div>

        <div v-if="needsRotation" class="story-rotate">
          <span class="rotate-frame"><RotateCw :size="30" /></span>
          <strong>把手机横过来</strong>
          <p>这段剧情按横屏演出。点下面的按钮进入全屏，如果系统没有自动旋转，请手动把屏幕横过来。</p>
          <button type="button" @click.stop="lockLandscape(stage)">进入横屏</button>
          <button class="rotate-skip" type="button" @click.stop="story.skip()">先跳过这段</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.story-layer { position: fixed; inset: 0; z-index: 300; }
.story-layer--stage { display: grid; place-items: center; background: #050706; }
.story-layer--inline {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  background: linear-gradient(transparent 42%, rgba(6, 10, 8, .74));
  cursor: pointer;
}

.story-stage {
  --stage-width: min(100vw, calc(100dvh * 16 / 9));
  position: relative;
  width: var(--stage-width);
  height: calc(var(--stage-width) * 9 / 16);
  overflow: hidden;
  background: #0b0f0d;
  font-size: clamp(13px, calc(var(--stage-width) * .021), 23px);
  cursor: pointer;
  user-select: none;
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
  color: var(--gold);
  font-size: .82em;
  font-weight: 700;
  letter-spacing: .04em;
}
.story-box--left .story-speaker { left: 1.4em; }
.story-box--right .story-speaker { right: 1.4em; }
.story-text { margin: .35em 0 0; color: var(--cream); font-size: 1em; line-height: 1.9; }
.story-text--aside { color: #cdd6cb; font-style: italic; }
.story-advance {
  position: absolute;
  right: 1.2em;
  bottom: .9em;
  width: .5em;
  height: .5em;
  border-right: 2px solid var(--gold);
  border-bottom: 2px solid var(--gold);
  transform: rotate(45deg);
  animation: story-advance 1.4s ease-in-out infinite;
}
@keyframes story-advance { 0%, 100% { opacity: .25; transform: rotate(45deg) translate(0, 0); } 50% { opacity: 1; transform: rotate(45deg) translate(.15em, .15em); } }

.story-skip {
  position: absolute;
  top: 1em;
  right: 1em;
  display: flex;
  align-items: center;
  gap: .4em;
  padding: .45em 1em;
  border: 1px solid rgba(236, 221, 187, .18);
  border-radius: .7em .2em .7em .2em;
  background: rgba(10, 15, 12, .72);
  color: #cbd4c8;
  font-size: .76em;
  cursor: pointer;
}
.story-skip:hover { color: var(--cream); border-color: rgba(224, 190, 116, .42); }

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
.story-inline :deep(.story-portrait--left) { left: 10px; }
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
.story-inline .story-skip { top: -34px; right: 12px; font-size: 12px; padding: 5px 11px; }

.story-rotate {
  position: fixed;
  inset: 0;
  z-index: 2;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 12px;
  padding: 32px;
  text-align: center;
  background: #080b09;
}
.rotate-frame {
  display: grid;
  place-items: center;
  width: 76px;
  height: 76px;
  border: 1px solid rgba(224, 190, 116, .4);
  border-radius: 24px 8px 24px 8px;
  color: var(--gold);
  animation: story-rotate-hint 2.4s ease-in-out infinite;
}
@keyframes story-rotate-hint { 0%, 55%, 100% { transform: rotate(0deg); } 25%, 45% { transform: rotate(90deg); } }
.story-rotate strong { font-family: Georgia, 'Noto Serif SC', serif; font-size: 19px; letter-spacing: .05em; }
.story-rotate p { max-width: 300px; margin: 0; color: var(--muted); font-size: 13px; line-height: 1.8; }
.story-rotate button {
  min-height: 44px;
  padding: 0 26px;
  margin-top: 6px;
  border: 0;
  border-radius: 12px;
  background: var(--cream);
  color: #1b251e;
  font-weight: 700;
  cursor: pointer;
}
.story-rotate .rotate-skip { margin-top: 0; background: transparent; color: #8b968c; font-weight: 400; font-size: 13px; min-height: 34px; }

.story-layer-enter-active, .story-layer-leave-active { transition: opacity .3s ease; }
.story-layer-enter-from, .story-layer-leave-to { opacity: 0; }
.story-background-enter-active, .story-background-leave-active { transition: opacity .45s ease; }
.story-background-enter-from, .story-background-leave-to { opacity: 0; }

@media (max-width: 760px) {
  .story-layer--inline { --story-bottom: calc(74px + env(safe-area-inset-bottom)); }
  .story-inline :deep(.story-portrait) { --portrait-base: min(34vh, 220px); }
  .story-inline .story-text { font-size: 13px; }
}
</style>
