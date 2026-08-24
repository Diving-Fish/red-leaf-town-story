export type RarityTier = 3 | 4 | 5

interface RarityMeta {
  tier: RarityTier
  label: string
  short: string
  epithet: string
}

const META: Record<RarityTier, RarityMeta> = {
  3: { tier: 3, label: '三星', short: '3', epithet: '寻常来客' },
  4: { tier: 4, label: '四星', short: '4', epithet: '灵光初现' },
  5: { tier: 5, label: '五星', short: '5', epithet: '红叶之约' },
}

export function normalizeRarity(value: number | null | undefined): RarityTier {
  if (value && value >= 5) return 5
  if (value && value >= 4) return 4
  return 3
}

export function rarityMeta(value: number | null | undefined): RarityMeta {
  return META[normalizeRarity(value)]
}

export function rarityClass(value: number | null | undefined): string {
  return `rarity-${normalizeRarity(value)}`
}
