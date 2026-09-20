import type {
  StoryAsset,
  StoryBackgroundStep,
  StoryBackgroundTransition,
  StoryDialogueStep,
  StoryMode,
  StoryPortraitSlot,
  StoryPortraitStep,
  StoryPortraitTransition,
  StoryStep,
} from '@/types'

export const BACKGROUND_DURATION = 0.45
export const PORTRAIT_DURATION = 0.28

export interface StoryPortraitState {
  asset: StoryAsset
  scale: number
  offsetX: number
  offsetY: number
  transition: StoryPortraitTransition
  duration: number
  flip: boolean
}

export interface StoryBackgroundState {
  asset: StoryAsset
  transition: StoryBackgroundTransition
  duration: number
}

export type StoryCast = Record<StoryPortraitSlot, StoryPortraitState | null>

export interface StoryStageState {
  background: StoryBackgroundState | null
  portraits: StoryCast
  line: StoryDialogueStep | null
}

export function emptyCast(): StoryCast {
  return { left: null, center: null, right: null }
}

export function emptyStage(): StoryStageState {
  return { background: null, portraits: emptyCast(), line: null }
}

export function resolveBackground(step: StoryBackgroundStep): StoryBackgroundState | null {
  if (!step.asset) return null
  return {
    asset: step.asset,
    transition: step.transition || 'fade',
    duration: step.duration ?? BACKGROUND_DURATION,
  }
}

/** 立绘站位优先用这一步自己的覆盖值，没写才回落到素材调好的默认站位。 */
export function resolvePortrait(step: StoryPortraitStep, mode: StoryMode): StoryPortraitState | null {
  if (!step.visible || !step.asset) return null
  const layout = step.layout || step.asset.layouts?.[mode]
  return {
    asset: step.asset,
    scale: layout?.scale ?? 1,
    offsetX: layout?.offset_x ?? 0,
    offsetY: layout?.offset_y ?? 0,
    transition: step.transition || 'fade',
    duration: step.duration ?? PORTRAIT_DURATION,
    flip: Boolean(step.flip),
  }
}

/**
 * 把前 count 步叠起来，得到"停在这一步"的画面。
 * 编辑器点中某一步时用它定格；播放器是逐步推进的，不走这里。
 */
export function foldStage(steps: StoryStep[], count: number, mode: StoryMode): StoryStageState {
  const stage = emptyStage()
  for (const step of steps.slice(0, Math.max(0, count))) {
    if (step.type === 'background') stage.background = resolveBackground(step)
    else if (step.type === 'portrait') stage.portraits[step.slot] = resolvePortrait(step, mode)
    else stage.line = step
  }
  return stage
}
