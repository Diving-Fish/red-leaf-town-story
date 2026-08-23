export const ITEM_KIND_NAMES: Record<string, string> = {
  seed: '种子',
  produce: '农产品',
  material: '材料',
  product: '加工品',
}

export function itemKindName(kind: string): string {
  return ITEM_KIND_NAMES[kind] || '其他'
}
