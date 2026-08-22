<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ChevronDown, Lock } from 'lucide-vue-next'

import PartnerAvatar from '@/components/PartnerAvatar.vue'
import PartnerChip from '@/components/PartnerChip.vue'
import { usePartnerRoster } from '@/composables/usePartnerRoster'
import { useGameStore } from '@/stores/game'
import { useUiStore } from '@/stores/ui'
import type { IndustryId, OwnedPartner } from '@/types'

const props = defineProps<{
  pickerId: string
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
}>()

const emit = defineEmits<{ (event: 'select', partnerId: string | null): void }>()

const game = useGameStore()
const ui = useUiStore()
const { partners, ability, isBusyElsewhere } = usePartnerRoster(() => props.industry)
const root = ref<HTMLElement | null>(null)
const dropUp = ref(false)

const open = computed(() => ui.openPickerId === props.pickerId)
const pending = computed(() => game.isPending(props.actionKey))
const subtitle = computed(() => {
  if (props.locked) return props.lockedLabel || '任务中 · 已锁定'
  if (props.assigned) return `能力 ${ability(props.assigned)}`
  return props.placeholderHint || ''
})

function toggle() {
  if (props.locked || pending.value) return
  if (open.value) {
    ui.closePicker()
    return
  }
  const rect = root.value?.getBoundingClientRect()
  dropUp.value = Boolean(rect && window.innerHeight - rect.bottom < 260 && rect.top > 260)
  ui.togglePicker(props.pickerId, true)
}

function choose(partner: OwnedPartner | null) {
  ui.closePicker()
  emit('select', partner ? partner.partner_id : null)
}

function onPointerDown(event: PointerEvent) {
  if (!open.value) return
  if (root.value && !root.value.contains(event.target as Node)) ui.closePicker()
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && open.value) ui.closePicker()
}

onMounted(() => {
  document.addEventListener('pointerdown', onPointerDown)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onPointerDown)
  document.removeEventListener('keydown', onKeydown)
  if (open.value) ui.closePicker()
})
</script>

<template>
  <div ref="root" class="partner-picker" :class="{ open, locked }">
    <button
      class="picker-trigger"
      :class="{ assigned: Boolean(assigned), 'is-pending': pending }"
      :disabled="locked || pending"
      @click="toggle"
    >
      <PartnerChip :partner="assigned" :title="placeholder || '安排伙伴'" :subtitle="subtitle" :size="31" />
      <Lock v-if="locked" :size="13" />
      <ChevronDown v-else :size="14" class="picker-caret" />
    </button>

    <div v-if="open" class="picker-panel" :class="{ up: dropUp }">
      <button v-if="assigned" class="picker-option" @click="choose(null)">
        <PartnerAvatar :size="30" />
        <span><strong>{{ soloLabel || '撤下伙伴' }}</strong><small v-if="soloHint">{{ soloHint }}</small></span>
      </button>
      <button
        v-for="partner in partners"
        :key="partner.partner_id"
        class="picker-option"
        :disabled="isBusyElsewhere(partner, assigned?.partner_id || null)"
        @click="choose(partner)"
      >
        <PartnerAvatar :artwork="partner.artwork" :crop="partner.avatar_crop" :name="partner.name" :size="30" />
        <span>
          <strong>{{ partner.name }}</strong>
          <small>能力 {{ ability(partner) }}{{ isBusyElsewhere(partner, assigned?.partner_id || null) ? ' · 其他任务中' : '' }}</small>
        </span>
        <Lock v-if="isBusyElsewhere(partner, assigned?.partner_id || null)" :size="12" />
      </button>
      <p v-if="!partners.length" class="picker-empty">{{ emptyHint || '仓库里还没有适合这个产业的伙伴。' }}</p>
    </div>
  </div>
</template>

<style scoped>
.partner-picker { position: relative; margin: 12px 0 9px; }
.partner-picker.open { z-index: 14; }
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
.picker-panel {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 6px);
  z-index: 20;
  max-height: 244px;
  overflow: auto;
  padding: 7px;
  border: 1px solid #ffffff1a;
  border-radius: 12px;
  background: #111a15;
  box-shadow: 0 18px 45px #0009;
}
.picker-panel.up { top: auto; bottom: calc(100% + 6px); }
.picker-option {
  width: 100%;
  min-height: 44px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 9px;
  padding: 5px 7px;
  text-align: left;
  color: #d9e1d7;
  border: 0;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
}
.picker-option:hover:not(:disabled) { background: #ffffff08; }
.picker-option:disabled { opacity: .45; cursor: default; }
.picker-option strong, .picker-option small { display: block; }
.picker-option strong { font-size: 13px; }
.picker-option small { margin-top: 2px; color: #6f7c73; font-size: 12px; }
.picker-empty { padding: 14px 8px; margin: 0; color: #6f7b72; font-size: 12px; line-height: 1.6; }
</style>
