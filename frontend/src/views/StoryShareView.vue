<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/api'
import StoryOverlay from '@/components/story/StoryOverlay.vue'
import { useStoryStore } from '@/stores/story'
import type { StoryScript } from '@/types'

const route = useRoute()
const story = useStoryStore()
const script = ref<StoryScript | null>(null)
const error = ref('')
let requestVersion = 0

watch(() => route.params.id, async (id) => {
  const version = ++requestVersion
  if (story.active) await story.skip()
  script.value = null
  error.value = ''
  try {
    const result = await api<StoryScript>(`/api/red-leaf-town/story/shares/${encodeURIComponent(String(id))}`)
    if (version === requestVersion) script.value = result
  } catch (caught) {
    if (version === requestVersion) error.value = caught instanceof Error ? caught.message : '剧情加载失败'
  }
}, { immediate: true })

onBeforeUnmount(() => {
  requestVersion++
  if (story.active) void story.skip()
})
</script>

<template>
  <main class="shared-story">
    <h1>{{ script?.title || '分享剧情' }}</h1>
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-else-if="script">
      <p>玩家创作的剧情 · 仅供欣赏，不影响游戏进度</p>
      <button type="button" @click="story.preview(script)">播放剧情</button>
    </template>
    <p v-else>正在加载剧情……</p>
    <RouterLink to="/story-editor">创作自己的剧情</RouterLink>
  </main>
  <StoryOverlay />
</template>

<style scoped>
.shared-story { min-height: 100dvh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 24px; padding: 32px; text-align: center; background: #101b17; color: #f6eddb; }
.shared-story h1 { overflow-wrap: anywhere; }
.shared-story button { padding: 14px 32px; border-radius: 12px; background: #ebc985; color: #241f17; cursor: pointer; }
.shared-story a { color: #ebc985; }
</style>
