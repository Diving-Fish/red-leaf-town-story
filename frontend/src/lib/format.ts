export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  if (!minutes) return `${rest}秒`
  return rest ? `${minutes}分${rest}秒` : `${minutes}分`
}

export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}
