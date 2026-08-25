import type {
  CraftingStationState,
  GatheringSiteState,
  MiningSiteState,
  OwnedPartner,
  ProductionResultSnapshot,
  ProductionTaskSnapshot,
} from '@/types'

export type ProductionIndustry = 'gathering' | 'mining' | 'crafting'

export interface ProductionNode {
  industry: ProductionIndustry
  nodeId: string
  name: string
  description: string
  accent: string
  empty: boolean
  ready: boolean
  assignedPartnerId: string | null
  assignedPartner: OwnedPartner | null
  assignmentLocked: boolean
  taskSnapshot: ProductionTaskSnapshot | null
  taskResults: ProductionResultSnapshot[]
  activeName: string
  activeItemName: string
  activeItemIcon: string
}

export interface ProductionCopy {
  partnerLabel: string
  soloLabel: string
  lockedLabel: string
  readyTitle: string
  collectLabel: string
  collectVerb: string
  collectNoun: string
  cancelLabel: string
  cancelConfirmTitle: string
  cancelConfirmDescription: string
  startPayloadKey: string
  endpoint: string
}

export const PRODUCTION_COPY: Record<ProductionIndustry, ProductionCopy> = {
  gathering: {
    partnerLabel: '派驻伙伴',
    soloLabel: '未派驻',
    lockedLabel: '采集任务中 · 已锁定',
    readyTitle: '采集完成',
    collectLabel: '领取采集物',
    collectVerb: '带回了',
    collectNoun: '采集物',
    cancelLabel: '取消采集',
    cancelConfirmTitle: '取消这次采集？',
    cancelConfirmDescription: '消耗的体力会退回，伙伴仍留在这个采集点。',
    startPayloadKey: 'task_id',
    endpoint: 'gathering/sites',
  },
  mining: {
    partnerLabel: '协助伙伴（可选）',
    soloLabel: '玩家独自采矿',
    lockedLabel: '采矿任务中 · 已锁定',
    readyTitle: '开采完成',
    collectLabel: '收取矿石',
    collectVerb: '取得了',
    collectNoun: '矿石',
    cancelLabel: '取消采矿',
    cancelConfirmTitle: '取消这次采矿？',
    cancelConfirmDescription: '消耗的体力会退回，伙伴仍留在这个矿点。',
    startPayloadKey: 'task_id',
    endpoint: 'mining/sites',
  },
  crafting: {
    partnerLabel: '协助伙伴（可选）',
    soloLabel: '玩家独自加工',
    lockedLabel: '加工任务中 · 已锁定',
    readyTitle: '加工完成',
    collectLabel: '领取成品',
    collectVerb: '制成了',
    collectNoun: '加工品',
    cancelLabel: '取消加工',
    cancelConfirmTitle: '取消这次加工？',
    cancelConfirmDescription: '消耗的材料和体力会退回，伙伴仍留在这个工位。',
    startPayloadKey: 'recipe_id',
    endpoint: 'crafting/stations',
  },
}

function baseNode(
  industry: ProductionIndustry,
  nodeId: string,
  source: {
    definition: { name: string; description: string; accent: string } | null
    empty: boolean
    ready: boolean
    assigned_partner_ids: string[]
    assigned_partners: OwnedPartner[]
    assignment_locked: boolean
    task_snapshot: ProductionTaskSnapshot | null
    task_results: ProductionResultSnapshot[]
  },
  fallbackAccent: string,
): Omit<ProductionNode, 'activeName' | 'activeItemName' | 'activeItemIcon'> {
  return {
    industry,
    nodeId,
    name: source.definition?.name || nodeId,
    description: source.definition?.description || '',
    accent: source.definition?.accent || fallbackAccent,
    empty: source.empty,
    ready: source.ready,
    assignedPartnerId: source.assigned_partner_ids[0] || null,
    assignedPartner: source.assigned_partners[0] || null,
    assignmentLocked: source.assignment_locked,
    taskSnapshot: source.task_snapshot,
    taskResults: source.task_results || [],
  }
}

export function fromGatheringSite(site: GatheringSiteState): ProductionNode {
  return {
    ...baseNode('gathering', site.site_id, site, '#78906d'),
    activeName: site.task?.name || '',
    activeItemName: site.task?.item.name || '',
    activeItemIcon: site.task?.item.icon || '',
  }
}

export function fromMiningSite(site: MiningSiteState): ProductionNode {
  return {
    ...baseNode('mining', site.site_id, site, '#a47955'),
    activeName: site.task?.name || '',
    activeItemName: site.task?.item.name || '',
    activeItemIcon: site.task?.item.icon || '',
  }
}

export function fromCraftingStation(station: CraftingStationState): ProductionNode {
  return {
    ...baseNode('crafting', station.station_id, station, '#ad8159'),
    activeName: station.recipe?.name || '',
    activeItemName: station.recipe?.item.name || '',
    activeItemIcon: station.recipe?.item.icon || '',
  }
}

export function estimateDuration(
  baseDuration: number,
  timeDifficulty: number,
  totalAbility: number,
  minimumDuration = 1,
  durationMultiplier = 1,
): number {
  const denominator = totalAbility + timeDifficulty
  const efficiency = denominator > 0 ? 1 + (2 * totalAbility) / denominator : 1
  const duration = Math.max(minimumDuration, Math.ceil(baseDuration / efficiency))
  /* 与后端一致：缩时道具压在最小时长之后结算 */
  if (durationMultiplier === 1) return duration
  return Math.max(1, Math.ceil(duration * durationMultiplier))
}

export function taskItemDurationMultiplier(
  taskItems: { id: string; effect: string; value: number }[] | undefined,
  taskItemId: string,
): number {
  const item = (taskItems || []).find((entry) => entry.id === taskItemId)
  return item && item.effect === 'duration_multiplier' ? item.value : 1
}

export function estimateDrawCount(
  draws: { base_draws: number; ability_bonus: number; difficulty: number } | undefined,
  totalAbility: number,
): number {
  if (!draws) return 0
  const ability = Math.max(0, totalAbility)
  const multiplier = 1 + (draws.ability_bonus * ability) / (ability + draws.difficulty)
  return Math.max(1, Math.floor(draws.base_draws * multiplier + 0.5))
}

export function partnerAbility(partner: OwnedPartner | null | undefined, industry: string): number {
  const tendency = partner?.tendencies?.find((entry) => entry.industry === industry)
  return tendency?.effective_ability ?? tendency?.current_ability ?? 0
}
