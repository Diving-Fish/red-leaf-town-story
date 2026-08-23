<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronRight, Lock } from 'lucide-vue-next'

import PartnerChip from '@/components/PartnerChip.vue'
import PartnerPickerDialog from '@/components/PartnerPickerDialog.vue'
import { usePartnerRoster } from '@/composables/usePartnerRoster'
import { useGameStore } from '@/stores/game'
import type { IndustryId, OwnedPartner } from '@/types'

const props = defineProps<{
  industry: IndustryId
  actionKey: string
  assigned?: OwnedPartner | null
  placeholder?: string
  placeholderHint?: string
  soloLabel?: string
  soloHint?: string
  locked?: boolean
  lockedLabel?: string
  emptyHint?: string
  dialogTitle?: string
  elevated?: boolean
}>()

const emit = defineEmits<{ (event: 'select', partnerId: string | null): void }>()

const game = useGameStore()
const { ability } = usePartnerRoster(() => props.industry)
const open = ref(false)

const pending = computed(() => game.isPending(props.actionKey))
const subtitle = computed(() => {
  if (props.locked) return props.lockedLabel || '任务中 · 已锁定'
  if (props.assigned) return `能力 ${ability(props.assigned)}`
  return props.placeholderHint || ''
})

function toggle() {
  if (props.locked || pending.value) return
  open.value = true
}
</script>

<template>
  <div class="partner-picker">
    <button
      class="picker-trigger"
      :class="{ assigned: Boolean(assigned), 'is-pending': pending }"
      :disabled="locked || pending"
      @click="toggle"
    >
      <PartnerChip :partner="assigned" :title="placeholder || '安排伙伴'" :subtitle="subtitle" :size="31" />
      <Lock v-if="locked" :size="13" />
      <ChevronRight v-else :size="16" class="picker-caret" />
    </button>

    <PartnerPickerDialog
      :open="open"
      :industry="industry"
      :assigned="assigned"
      :title="dialogTitle"
      :solo-label="soloLabel"
      :solo-hint="soloHint"
      :empty-hint="emptyHint"
      :elevated="elevated"
      @select="(partnerId) => emit('select', partnerId)"
      @close="open = false"
    />
  </div>
</template>

<style scoped>
.partner-picker { position: relative; margin: 12px 0 9px; }
.picker-trigger {
  width: 100%;
  min-height: 48px;
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  color: #8c998f;
  border: 1px dashed #ffffff14;
  border-radius: 10px;
  background: #0d141086;
  cursor: pointer;
}
.picker-trigger.assigned { color: #d9e2d6; border-style: solid; border-color: #8ead7130; background: #8ead710b; }
.picker-trigger:disabled { cursor: default; opacity: .72; }
.picker-caret { color: #7b867d; }
</style>
