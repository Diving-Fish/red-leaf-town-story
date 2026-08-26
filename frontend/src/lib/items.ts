import type { InventoryItem } from '@/types'

export const ITEM_KIND_NAMES: Record<string, string> = {
  seed: '种子',
  produce: '农产品',
  material: '材料',
  product: '加工品',
}

export function itemKindName(kind: string): string {
  return ITEM_KIND_NAMES[kind] || '其他'
}

export interface InventoryGroup {
  itemId: string
  name: string
  icon: string
  kind: string
  quantity: number
  value: number
  topQuality: number | null
  sellable: boolean
  buckets: InventoryItem[]
}

/** Fold the flat inventory into one entry per item, keeping the per-quality buckets sorted high to low. */
export function groupInventory(items: InventoryItem[]): InventoryGroup[] {
  const groups = new Map<string, InventoryGroup>()
  for (const item of items) {
    let group = groups.get(item.item_id)
    if (!group) {
      group = {
        itemId: item.item_id,
        name: item.name,
        icon: item.icon,
        kind: item.kind,
        quantity: 0,
        value: 0,
        topQuality: null,
        sellable: false,
        buckets: [],
      }
      groups.set(item.item_id, group)
    }
    group.quantity += item.quantity
    group.value += item.sell_price * item.quantity
    group.topQuality = Math.max(group.topQuality || 0, item.quality || 0) || null
    group.sellable = group.sellable || item.sell_price > 0
    group.buckets.push(item)
  }
  for (const group of groups.values()) group.buckets.sort((left, right) => (right.quality || 0) - (left.quality || 0))
  return [...groups.values()]
}
