import type { Component } from 'vue'
import { Archive, DoorOpen, Hammer, LayoutDashboard, Pickaxe, ShoppingBasket, Sparkles, Sprout, Trees } from 'lucide-vue-next'

import type { GameState } from '@/types'

export type ReadyGroup = 'plots' | 'gathering' | 'mining' | 'crafting'

export interface NavItem {
  to: string
  label: string
  icon: Component
  primary: boolean
  readyGroup?: ReadyGroup
  unlocked?: (state: GameState) => boolean
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: '总览', icon: LayoutDashboard, primary: true },
  { to: '/farm', label: '农场', icon: Sprout, primary: true, readyGroup: 'plots' },
  {
    to: '/gathering',
    label: '采集',
    icon: Trees,
    primary: true,
    readyGroup: 'gathering',
    unlocked: (state) => state.gathering_sites.length > 0,
  },
  {
    to: '/crafting',
    label: '加工',
    icon: Hammer,
    primary: false,
    readyGroup: 'crafting',
    unlocked: (state) => state.crafting_stations.length > 0,
  },
  {
    to: '/mining',
    label: '矿产',
    icon: Pickaxe,
    primary: false,
    readyGroup: 'mining',
    unlocked: (state) => state.mining_sites.length > 0,
  },
  {
    to: '/portals',
    label: '传送门',
    icon: DoorOpen,
    primary: false,
    unlocked: (state) => state.portals.some((portal) => portal.unlocked),
  },
  { to: '/shop', label: '种子商店', icon: ShoppingBasket, primary: false },
  { to: '/inventory', label: '仓库', icon: Archive, primary: true },
  { to: '/partners', label: '伙伴', icon: Sparkles, primary: false },
]

export function unlockedNavItems(state: GameState | null): NavItem[] {
  if (!state) return NAV_ITEMS.filter((item) => !item.unlocked)
  return NAV_ITEMS.filter((item) => !item.unlocked || item.unlocked(state))
}
