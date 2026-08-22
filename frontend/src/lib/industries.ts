import type { Component } from 'vue'
import { Compass, Hammer, PawPrint, Pickaxe, Sprout, Trees, Waves } from 'lucide-vue-next'

import type { IndustryId } from '@/types'

export interface IndustryMeta {
  id: IndustryId
  name: string
  description: string
  icon: Component
  accent: string
}

export const INDUSTRIES: IndustryMeta[] = [
  { id: 'farming', name: '农作', description: '作物、土地与收获', icon: Sprout, accent: '#8ead71' },
  { id: 'gathering', name: '采集', description: '林野派遣与采集编制', icon: Trees, accent: '#78906d' },
  { id: 'mining', name: '矿产', description: '矿脉、开采与矿石品质', icon: Pickaxe, accent: '#a47955' },
  { id: 'aquatic', name: '水产', description: '垂钓、养殖与捕捞', icon: Waves, accent: '#6f93a6' },
  { id: 'livestock', name: '畜牧', description: '动物、饲料与畜产品', icon: PawPrint, accent: '#b0925f' },
  { id: 'crafting', name: '加工', description: '配方、工位与成品', icon: Hammer, accent: '#ad8159' },
  { id: 'exploration', name: '探索', description: '派遣、地点与特殊事件', icon: Compass, accent: '#8d84ab' },
]

export const INDUSTRY_MAP = INDUSTRIES.reduce((map, entry) => {
  map[entry.id] = entry
  return map
}, {} as Record<IndustryId, IndustryMeta>)

export function industryMeta(id: IndustryId): IndustryMeta {
  return INDUSTRY_MAP[id]
}

export function industryName(id: IndustryId): string {
  return INDUSTRY_MAP[id]?.name || id
}

export function industryAccent(id: IndustryId): string {
  return INDUSTRY_MAP[id]?.accent || '#78906d'
}
