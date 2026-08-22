import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { useGameStore } from '@/stores/game'
import type { IndustryId, OwnedPartner } from '@/types'

export function usePartnerRoster(industry: MaybeRefOrGetter<IndustryId>) {
  const game = useGameStore()

  const partners = computed(() =>
    (game.state?.partners || []).filter(
      (partner) => !partner.missing && partner.tendencies?.some((entry) => entry.industry === toValue(industry)),
    ),
  )

  function ability(partner: OwnedPartner | null | undefined) {
    const tendency = partner?.tendencies?.find((entry) => entry.industry === toValue(industry))
    return tendency?.effective_ability ?? tendency?.current_ability ?? 0
  }

  function isBusyElsewhere(partner: OwnedPartner, currentId: string | null) {
    return partner.locked && partner.partner_id !== currentId
  }

  return { partners, ability, isBusyElsewhere }
}
