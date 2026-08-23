export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  if (total >= 86400) {
    const days = Math.floor(total / 86400)
    const hours = Math.floor((total % 86400) / 3600)
    return hours ? `${days}天${hours}小时` : `${days}天`
  }
  if (total >= 3600) {
    const hours = Math.floor(total / 3600)
    const minutes = Math.floor((total % 3600) / 60)
    return minutes ? `${hours}小时${minutes}分` : `${hours}小时`
  }
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  if (!minutes) return `${rest}秒`
  return rest ? `${minutes}分${rest}秒` : `${minutes}分`
}

export function formatClock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}
