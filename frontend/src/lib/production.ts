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
  taskResult: ProductionResultSnapshot | null
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
    task_result?: ProductionResultSnapshot | null
    task_results?: ProductionResultSnapshot[]
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
    taskResult: source.task_result || null,
    taskResults: source.task_results || (source.task_result ? [source.task_result] : []),
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
): number {
  const denominator = totalAbility + timeDifficulty
  const efficiency = denominator > 0 ? 1 + (2 * totalAbility) / denominator : 1
  return Math.max(minimumDuration, Math.ceil(baseDuration / efficiency))
}

export function partnerAbility(partner: OwnedPartner | null | undefined, industry: string): number {
  const tendency = partner?.tendencies?.find((entry) => entry.industry === industry)
  return tendency?.effective_ability ?? tendency?.current_ability ?? 0
}
