import type { Component } from 'vue'
import { Archive, Hammer, LayoutDashboard, Pickaxe, ShoppingBasket, Sparkles, Sprout, Trees } from 'lucide-vue-next'

export type ReadyGroup = 'plots' | 'gathering' | 'mining' | 'crafting'

export interface NavItem {
  to: string
  label: string
  icon: Component
  primary: boolean
  readyGroup?: ReadyGroup
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: '总览', icon: LayoutDashboard, primary: true },
  { to: '/farm', label: '农场', icon: Sprout, primary: true, readyGroup: 'plots' },
  { to: '/gathering', label: '采集', icon: Trees, primary: true, readyGroup: 'gathering' },
  { to: '/crafting', label: '加工', icon: Hammer, primary: false, readyGroup: 'crafting' },
  { to: '/mining', label: '矿产', icon: Pickaxe, primary: false, readyGroup: 'mining' },
  { to: '/shop', label: '种子商店', icon: ShoppingBasket, primary: false },
  { to: '/inventory', label: '仓库', icon: Archive, primary: true },
  { to: '/partners', label: '伙伴', icon: Sparkles, primary: false },
]
