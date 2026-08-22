export const QUALITY_NAMES = ['', '普通', '良品', '上品', '臻品', '奇迹']

export const MAX_QUALITY = QUALITY_NAMES.length - 1

export function qualityName(quality: number | null | undefined, fallback = ''): string {
  if (!quality) return fallback
  return QUALITY_NAMES[quality] || fallback
}

export function qualityClass(quality: number | null | undefined): string {
  return quality ? `quality-${quality}` : ''
}
