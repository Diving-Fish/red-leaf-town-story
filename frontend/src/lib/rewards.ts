import type { Reward } from '@/types'

export function rewardSummary(reward: Reward): string {
  const parts: string[] = []
  if (reward.maple_flame) parts.push(`枫火 ×${reward.maple_flame}`)
  if (reward.guide_leaves) parts.push(`引路枫叶 ×${reward.guide_leaves}`)
  if (reward.coins) parts.push(`红叶币 ×${reward.coins}`)
  if (reward.experience) parts.push(`经验 ×${reward.experience}`)
  if (reward.talent_points) parts.push(`天赋点 ×${reward.talent_points}`)
  parts.push(...reward.items.map((item) => `${item.name} ×${item.quantity}`))
  parts.push(...reward.partners.map((partner) => `${partner.name} 加入`))
  return parts.join('、')
}
