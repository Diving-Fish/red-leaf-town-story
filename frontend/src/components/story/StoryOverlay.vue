<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RotateCw, SkipForward } from 'lucide-vue-next'

import StoryStage from '@/components/story/StoryStage.vue'
import { useLandscapeStage } from '@/composables/useLandscapeStage'
import { useStoryStore } from '@/stores/story'

const story = useStoryStore()
const stage = ref<InstanceType<typeof StoryStage> | null>(null)
const { isPortrait, isTouch, lockLandscape, releaseLandscape } = useLandscapeStage()

const onStage = computed(() => story.active && story.mode === 'stage')
const needsRotation = computed(() => onStage.value && isTouch.value && isPortrait.value)

watch(onStage, async (staged) => {
  if (!staged) {
    await releaseLandscape()
    return
  }
  await nextTick()
  await lockLandscape(stage.value?.frame ?? null)
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
        <StoryStage
          ref="stage"
          :mode="story.mode"
          :background="story.background"
          :portraits="story.portraits"
          :line="story.line"
        >
          <template #overlay>
            <button class="story-skip" type="button" @click.stop="story.skip()">
              <SkipForward :size="15" />跳过
            </button>
          </template>
        </StoryStage>

        <div v-if="needsRotation" class="story-rotate">
          <span class="rotate-frame"><RotateCw :size="30" /></span>
          <strong>把手机横过来</strong>
          <p>这段剧情按横屏演出。点下面的按钮进入全屏，如果系统没有自动旋转，请手动把屏幕横过来。</p>
          <button type="button" @click.stop="lockLandscape(stage?.frame ?? null)">进入横屏</button>
          <button class="rotate-skip" type="button" @click.stop="story.skip()">先跳过这段</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.story-layer { position: fixed; inset: 0; z-index: 300; }
.story-layer--stage { background: #050706; }
.story-layer--inline {
  background: linear-gradient(transparent 42%, rgba(6, 10, 8, .74));
  cursor: pointer;
}
.story-layer--stage :deep(.story-stage) { cursor: pointer; }

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
.story-layer--inline .story-skip { top: -34px; right: 12px; font-size: 12px; padding: 5px 11px; }

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
@media (prefers-reduced-motion: reduce) {
  .story-layer-enter-active, .story-layer-leave-active { transition-duration: .01ms; }
  .rotate-frame { animation: none; }
}
</style>
