<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, Clock3, UserRoundMinus } from 'lucide-vue-next'

import PartnerAvatar from '@/components/PartnerAvatar.vue'
import { useCountdown } from '@/composables/useCountdown'
import { formatDuration } from '@/lib/format'
import type { OwnedPartner } from '@/types'

/**
 * 资产格换人的排队提示。
 *
 * 周期开工之后换人不立刻生效，得让玩家一眼看出【谁换谁】和【什么时候】—— 光一行字说
 * 不清楚，所以用头像加箭头把交接画出来。
 */
const props = defineProps<{
  pendingIds: string[] | null
  pendingPartner: OwnedPartner | null
  assigned: OwnedPartner | null
  swapOpen: boolean
  readyAt: number
  cycleSeconds: number
  windowSeconds: number
}>()

const { label: countdown } = useCountdown(
  () => props.readyAt,
  () => props.cycleSeconds,
)

const queued = computed(() => props.pendingIds !== null)
const currentLabel = computed(() => props.assigned?.name || '自己照看')
const title = computed(() =>
  props.pendingPartner ? `${props.pendingPartner.name} 下个周期接手` : '下个周期起改为自己照看',
)
</script>

<template>
  <div v-if="queued" class="swap-queued">
    <div class="swap-flow">
      <PartnerAvatar
        class="swap-face is-current"
        :artwork="assigned?.artwork"
        :crop="assigned?.avatar_crop"
        :name="assigned?.name"
        :size="30"
      />
      <ArrowRight :size="14" class="swap-arrow" />
      <PartnerAvatar
        class="swap-face is-next"
        :artwork="pendingPartner?.artwork"
        :crop="pendingPartner?.avatar_crop"
        :name="pendingPartner?.name"
        :size="30"
      >
        <UserRoundMinus v-if="!pendingPartner" :size="14" />
      </PartnerAvatar>
    </div>
    <div class="swap-copy">
      <strong>{{ title }}</strong>
      <small>还有 {{ countdown }} · 这个周期仍按{{ currentLabel }}结算</small>
    </div>
  </div>

  <div v-else-if="!swapOpen" class="swap-hint">
    <Clock3 :size="14" class="swap-hint-icon" />
    <div class="swap-copy">
      <strong>这个周期已经开工，换人会排到下个周期</strong>
      <small>每个周期开工 {{ formatDuration(windowSeconds) }} 内可自由换</small>
    </div>
  </div>
</template>

<style scoped>
.swap-queued {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-top: -4px;
  padding: 10px 12px;
  border: 1px solid rgba(215, 173, 88, .22);
  border-radius: 13px;
  background: rgba(215, 173, 88, .05);
}

.swap-flow { flex: 0 0 auto; display: flex; align-items: center; gap: 5px; }
.swap-face.is-current { opacity: .5; }
.swap-face.is-next { box-shadow: 0 0 0 1px var(--gold); }
.swap-arrow { flex: 0 0 auto; color: var(--gold); opacity: .7; }

/* 两句话竖排，不去抢同一行的宽度：并排放在窄屏上只有左边那句会折行，很难看。 */
.swap-copy { min-width: 0; }
.swap-copy strong,
.swap-copy small { display: block; }
.swap-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12.5px; }
.swap-copy small { margin-top: 3px; color: #7d887f; font-size: 11.5px; line-height: 1.5; }
.swap-queued .swap-copy strong { color: var(--gold); }

.swap-hint { display: flex; align-items: flex-start; gap: 7px; margin-top: -4px; }
.swap-hint-icon { flex: 0 0 auto; margin-top: 1px; color: #7d887f; }
.swap-hint .swap-copy strong { color: #7d887f; font-size: 11.5px; white-space: normal; }
.swap-hint .swap-copy small { margin-top: 2px; color: #6f7a72; font-size: 11px; }
</style>
