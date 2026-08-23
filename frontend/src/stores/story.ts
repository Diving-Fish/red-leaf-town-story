import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { api } from '@/api'
import type {
  ActionResult,
  StoryAsset,
  StoryCueResult,
  StoryDialogueStep,
  StoryPortraitSlot,
  StoryPortraitStep,
  StoryScript,
} from '@/types'

const API_ROOT = '/api/red-leaf-town'

export interface StoryPortraitState {
  asset: StoryAsset
  scale: number
  offsetX: number
  offsetY: number
}

function emptyPortraits(): Record<StoryPortraitSlot, StoryPortraitState | null> {
  return { left: null, right: null }
}

export const useStoryStore = defineStore('story', () => {
  const queue = ref<StoryScript[]>([])
  const script = ref<StoryScript | null>(null)
  const background = ref<StoryAsset | null>(null)
  const portraits = ref(emptyPortraits())
  const line = ref<StoryDialogueStep | null>(null)
  const previewing = ref(false)
  const locked = ref(false)
  const requested = new Set<string>()
  let cursor = 0
  // 剧情播完可能带来奖励（伙伴加入、种子到手），上报时服务端会回结算结果和新存档。
  let onSettled: ((result: ActionResult) => void) | null = null

  function bindState(handler: (result: ActionResult) => void) {
    onSettled = handler
  }

  const active = computed(() => script.value !== null)
  const mode = computed(() => script.value?.mode || 'inline')
  const speaker = computed(() => line.value?.speaker || '')
  const focus = computed<StoryPortraitSlot | 'none'>(() => line.value?.focus || 'none')

  async function cue(code: string) {
    try {
      const result = await api<StoryCueResult>(`${API_ROOT}/story/cue`, {
        method: 'POST',
        body: JSON.stringify({ cue: code }),
      })
      enqueue(result.stories)
    } catch {
      // 剧情演出不应该打断玩家正在做的事，取不到就当这次没有插话。
    }
  }

  function enqueue(scripts: StoryScript[]) {
    for (const entry of scripts) {
      if (script.value?.id === entry.id || queue.value.some((queued) => queued.id === entry.id)) continue
      // 一次性剧本在本次会话里只排一次队，避免 seen 回写前被另一个信号重复带出来。
      if (!entry.repeatable && requested.has(entry.id)) continue
      requested.add(entry.id)
      queue.value.push(entry)
    }
    if (!script.value) startNext()
  }

  function preview(entry: StoryScript, options: { locked?: boolean } = {}) {
    queue.value = []
    previewing.value = true
    start(entry)
    // 调整立绘布局时不希望点一下就把预览翻过去。
    locked.value = Boolean(options.locked)
  }

  function setPortraitLayout(slot: StoryPortraitSlot, layout: Partial<StoryPortraitState>) {
    const current = portraits.value[slot]
    if (current) portraits.value[slot] = { ...current, ...layout }
  }

  function startNext() {
    const next = queue.value.shift()
    if (!next) {
      clearStage()
      return
    }
    previewing.value = false
    start(next)
  }

  function start(entry: StoryScript) {
    clearStage()
    script.value = entry
    cursor = 0
    advance()
  }

  function advance() {
    const steps = script.value?.steps || []
    while (cursor < steps.length) {
      const step = steps[cursor]
      cursor += 1
      if (step.type === 'background') {
        background.value = step.asset
        continue
      }
      if (step.type === 'portrait') {
        applyPortrait(step)
        continue
      }
      line.value = step
      return
    }
    finish()
  }

  function applyPortrait(step: StoryPortraitStep) {
    if (!step.visible || !step.asset) {
      portraits.value[step.slot] = null
      return
    }
    const layout = step.asset.layouts?.[script.value?.mode || 'inline']
    portraits.value[step.slot] = {
      asset: step.asset,
      scale: layout?.scale ?? 1,
      offsetX: layout?.offset_x ?? 0,
      offsetY: layout?.offset_y ?? 0,
    }
  }

  function finish() {
    const finished = script.value
    const wasPreview = previewing.value
    clearStage()
    if (finished && !wasPreview) {
      api<ActionResult>(`${API_ROOT}/story/${encodeURIComponent(finished.id)}/seen`, { method: 'POST' })
        .then((result) => onSettled?.(result))
        .catch(() => undefined)
    }
    startNext()
  }

  function clearStage() {
    script.value = null
    background.value = null
    portraits.value = emptyPortraits()
    line.value = null
    previewing.value = false
    locked.value = false
    cursor = 0
  }

  return {
    queue,
    script,
    background,
    portraits,
    line,
    previewing,
    locked,
    active,
    mode,
    speaker,
    focus,
    cue,
    bindState,
    enqueue,
    preview,
    setPortraitLayout,
    advance,
    skip: finish,
  }
})
