const POOL_NAMES: Record<string, string> = {
  'standard-1': '常驻招募',
}

export function poolDisplayName(poolId: string): string {
  return POOL_NAMES[poolId] || '招募池'
}
