import type {
  StoryAsset,
  StoryBackgroundTransition,
  StoryExample,
  StoryPortraitSlot,
  StoryPortraitTransition,
  StoryResources,
  StoryStep,
  StoryStepLayout,
} from '@/types'

export const DRAFT_FORMAT = 'red-leaf-town-story'
export const DRAFT_VERSION = 1
export const MAX_STEPS = 200
export const MAX_TEXT = 500
export const MAX_SPEAKER = 32
export const ID_PATTERN = /^[a-z][a-z0-9_-]{1,63}$/

/** 编辑器里的一步。和后端的 StoryStep 同构，只是不带解析好的 asset。 */
export interface DraftBackgroundStep {
  type: 'background'
  asset_id: string
  transition: StoryBackgroundTransition
  duration: number
}

export interface DraftPortraitStep {
  type: 'portrait'
  slot: StoryPortraitSlot
  visible: boolean
  asset_id: string
  partner_id: string
  breakthrough: number
  transition: StoryPortraitTransition
  duration: number
  flip: boolean
  layout: StoryStepLayout | null
}

export interface DraftDialogueStep {
  type: 'dialogue'
  speaker: string
  text: string
  focus: StoryPortraitSlot | 'none'
}

export type DraftStep = DraftBackgroundStep | DraftPortraitStep | DraftDialogueStep
export type DraftStepType = DraftStep['type']

/**
 * 触发条件和奖励不归编辑器管——它们要配合游戏进度决定，由维护者最后定。
 * 作者在这里用大白话写清楚建议，导出的文件原样带着。
 */
export interface DraftMetadata {
  author: string
  trigger_note: string
  reward_note: string
  note: string
}

export interface StoryDraft {
  format: typeof DRAFT_FORMAT
  version: number
  id: string
  title: string
  priority: number
  metadata: DraftMetadata
  steps: DraftStep[]
  updated_at: number
}

export const STEP_LABELS: Record<DraftStepType, string> = {
  dialogue: '对话',
  portrait: '立绘',
  background: '背景',
}

export function blankLayout(): StoryStepLayout {
  return { scale: 1, offset_x: 0, offset_y: 0 }
}

export function createStep(type: DraftStepType): DraftStep {
  if (type === 'background') return { type, asset_id: '', transition: 'fade', duration: 0.45 }
  if (type === 'portrait') {
    return {
      type,
      slot: 'left',
      visible: true,
      asset_id: '',
      partner_id: '',
      breakthrough: 0,
      transition: 'fade',
      duration: 0.28,
      flip: false,
      layout: null,
    }
  }
  return { type, speaker: '', text: '', focus: 'none' }
}

export function createDraft(id = ''): StoryDraft {
  return {
    format: DRAFT_FORMAT,
    version: DRAFT_VERSION,
    id: id || `untitled_${Date.now().toString(36)}`,
    title: '未命名剧本',
    priority: 0,
    metadata: { author: '', trigger_note: '', reward_note: '', note: '' },
    steps: [createStep('background'), createStep('dialogue')],
    updated_at: Date.now(),
  }
}

/** 编辑器只产出全屏剧本，所以至少要有一个选好图的背景步骤。 */
export function hasBackground(steps: DraftStep[]): boolean {
  return steps.some((step) => step.type === 'background' && step.asset_id)
}

/* ---------- 素材索引 ---------- */

export interface ResourceIndex {
  assets: Map<string, StoryAsset>
  backgrounds: StoryAsset[]
  portraits: StoryAsset[]
  partners: StoryResources['partners']
  partnerArtwork: Map<string, StoryAsset>
}

function partnerKey(partnerId: string, breakthrough: number) {
  return `partner:${partnerId}:${breakthrough}`
}

/** 自己传的图只有一套默认站位，两种模式共用。 */
function uploadAsAsset(upload: StoryResources['uploads'][number]): StoryAsset {
  const layout = upload.layout || blankLayout()
  return {
    id: upload.id,
    kind: upload.kind,
    name: upload.name,
    asset_key: upload.asset_key,
    width: upload.width,
    height: upload.height,
    url: upload.url,
    created_at: upload.created_at,
    source: 'upload',
    layouts: { inline: { ...layout }, stage: { ...layout } },
  }
}

export function indexResources(resources: StoryResources): ResourceIndex {
  const assets = new Map<string, StoryAsset>()
  for (const asset of resources.assets) assets.set(asset.id, { ...asset, source: 'official' })
  for (const upload of resources.uploads || []) assets.set(upload.id, uploadAsAsset(upload))
  const partnerArtwork = new Map<string, StoryAsset>()
  for (const partner of resources.partners) {
    for (const artwork of partner.artworks) {
      // 伙伴插画没有素材记录，站位一律用默认值，和服务端 serialize_step 保持一致。
      partnerArtwork.set(partnerKey(partner.id, artwork.breakthrough), {
        id: partnerKey(partner.id, artwork.breakthrough),
        name: partner.name,
        asset_key: artwork.asset_key,
        width: artwork.width,
        height: artwork.height,
        url: artwork.url,
        layouts: { inline: blankLayout(), stage: blankLayout() },
      })
    }
  }
  const all = [...assets.values()]
  return {
    assets,
    backgrounds: all.filter((asset) => asset.kind === 'background'),
    portraits: all.filter((asset) => asset.kind === 'portrait'),
    partners: resources.partners,
    partnerArtwork,
  }
}

export function stepAsset(step: DraftStep, index: ResourceIndex): StoryAsset | null {
  if (step.type === 'dialogue') return null
  if (step.asset_id) return index.assets.get(step.asset_id) || null
  if (step.type === 'portrait' && step.partner_id) {
    return index.partnerArtwork.get(partnerKey(step.partner_id, step.breakthrough)) || null
  }
  return null
}

/** 把草稿步骤补上解析好的素材，变成播放器认得的 StoryStep。 */
export function hydrate(steps: DraftStep[], index: ResourceIndex): StoryStep[] {
  return steps.map((step) => {
    if (step.type === 'dialogue') return { ...step }
    return { ...step, asset: stepAsset(step, index) } as StoryStep
  })
}

/* ---------- 导入导出 ---------- */

/**
 * 导出的就是一份剧本 JSON，多带一个 metadata 块。
 * 后端 Pydantic 默认忽略多余字段，所以同一个文件既能导回编辑器继续改，
 * 也能在补好 trigger 之后直接放进 data/story/。
 */
export function toScriptFile(draft: StoryDraft, index?: ResourceIndex) {
  return {
    id: draft.id,
    title: draft.title,
    priority: draft.priority,
    trigger: { hook: 'cue', params: { cue: 'view:dashboard' } },
    steps: draft.steps.map(serializeStep),
    metadata: {
      ...draft.metadata,
      format: DRAFT_FORMAT,
      version: DRAFT_VERSION,
      // 剧本引用的社区图不在公共素材库里，维护者要先把它们收进去才能合并。
      community_assets: index ? communityAssets(draft.steps, index) : [],
    },
  }
}

function communityAssets(steps: DraftStep[], index: ResourceIndex) {
  const used = new Map<string, StoryAsset>()
  for (const step of steps) {
    if (step.type === 'dialogue' || !step.asset_id) continue
    const asset = index.assets.get(step.asset_id)
    if (asset?.source === 'upload') used.set(asset.id, asset)
  }
  return [...used.values()].map((asset) => ({
    id: asset.id,
    kind: asset.kind,
    name: asset.name,
    asset_key: asset.asset_key,
    width: asset.width,
    height: asset.height,
  }))
}

/** 新作者的起手草稿：直接拿游戏里现成的那段剧情当样板。 */
export function draftFromExample(example: StoryExample): StoryDraft {
  return parseScriptFile({
    id: example.id,
    title: example.title,
    priority: example.priority,
    steps: example.steps,
    metadata: { note: '示例草稿，取自游戏中现有剧情。可直接修改，或在草稿箱中新建空白剧本。' },
  })
}

/** 默认值不写进文件，剧本 JSON 读起来才干净。 */
function serializeStep(step: DraftStep): Record<string, unknown> {
  if (step.type === 'dialogue') {
    return {
      type: 'dialogue',
      ...(step.speaker ? { speaker: step.speaker } : {}),
      text: step.text,
      ...(step.focus !== 'none' ? { focus: step.focus } : {}),
    }
  }
  if (step.type === 'background') {
    return {
      type: 'background',
      asset_id: step.asset_id,
      ...(step.transition !== 'fade' ? { transition: step.transition } : {}),
      ...(step.duration !== 0.45 ? { duration: round(step.duration) } : {}),
    }
  }
  if (!step.visible) return { type: 'portrait', slot: step.slot, visible: false }
  return {
    type: 'portrait',
    slot: step.slot,
    ...(step.asset_id
      ? { asset_id: step.asset_id }
      : { partner_id: step.partner_id, ...(step.breakthrough ? { breakthrough: step.breakthrough } : {}) }),
    ...(step.transition !== 'fade' ? { transition: step.transition } : {}),
    ...(step.duration !== 0.28 ? { duration: round(step.duration) } : {}),
    ...(step.flip ? { flip: true } : {}),
    ...(step.layout
      ? { layout: { scale: round(step.layout.scale), offset_x: round(step.layout.offset_x), offset_y: round(step.layout.offset_y) } }
      : {}),
  }
}

function round(value: number) {
  return Math.round(value * 100) / 100
}

export function parseScriptFile(raw: unknown): StoryDraft {
  if (!raw || typeof raw !== 'object') throw new Error('该文件不是剧本 JSON')
  const source = raw as Record<string, any>
  const steps = Array.isArray(source.steps) ? source.steps.map(parseStep) : []
  if (!steps.length) throw new Error('该文件不包含任何步骤')
  const metadata = (source.metadata || {}) as Partial<DraftMetadata>
  return {
    format: DRAFT_FORMAT,
    version: DRAFT_VERSION,
    id: String(source.id || '') || createDraft().id,
    title: String(source.title || '未命名剧本').slice(0, 64),
    priority: Number.isFinite(Number(source.priority)) ? clamp(Number(source.priority), -100, 100) : 0,
    metadata: {
      author: String(metadata.author || ''),
      trigger_note: String(metadata.trigger_note || ''),
      reward_note: String(metadata.reward_note || ''),
      note: String(metadata.note || ''),
    },
    steps,
    updated_at: Date.now(),
  }
}

function parseStep(raw: unknown): DraftStep {
  const source = (raw || {}) as Record<string, any>
  const type = String(source.type || '')
  if (type === 'background') {
    const base = createStep('background') as DraftBackgroundStep
    return {
      ...base,
      asset_id: String(source.asset_id || ''),
      transition: source.transition === 'cut' ? 'cut' : 'fade',
      duration: clamp(Number(source.duration ?? base.duration) || 0, 0, 3),
    }
  }
  if (type === 'portrait') {
    const base = createStep('portrait') as DraftPortraitStep
    const layout = source.layout && typeof source.layout === 'object' ? source.layout : null
    return {
      ...base,
      slot: ['left', 'right', 'center'].includes(source.slot) ? source.slot : 'left',
      visible: source.visible !== false,
      asset_id: String(source.asset_id || ''),
      partner_id: String(source.partner_id || ''),
      breakthrough: clamp(Number(source.breakthrough) || 0, 0, 2),
      transition: ['fade', 'slide', 'cut'].includes(source.transition) ? source.transition : 'fade',
      duration: clamp(Number(source.duration ?? base.duration) || 0, 0, 3),
      flip: Boolean(source.flip),
      layout: layout
        ? {
            scale: clamp(Number(layout.scale) || 1, 0.2, 4),
            offset_x: clamp(Number(layout.offset_x) || 0, -1.5, 1.5),
            offset_y: clamp(Number(layout.offset_y) || 0, -0.8, 0.8),
          }
        : null,
    }
  }
  const base = createStep('dialogue') as DraftDialogueStep
  return {
    ...base,
    speaker: String(source.speaker || '').slice(0, MAX_SPEAKER),
    text: String(source.text || '').slice(0, MAX_TEXT),
    focus: source.focus === 'left' || source.focus === 'right' ? source.focus : 'none',
  }
}

export function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}
