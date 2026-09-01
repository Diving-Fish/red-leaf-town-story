<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronRight } from 'lucide-vue-next'

import GameIcon from '@/components/GameIcon.vue'
import ItemPickerDialog from '@/components/ItemPickerDialog.vue'
import type { InventoryItem } from '@/types'

/** 和 PartnerPicker 同一套触发行：显示当前选择，点开走 ItemPickerDialog。 */
const props = defineProps<{
  label: string
  placeholder: string
  items: InventoryItem[]
  selected?: InventoryItem | null
  dialogTitle: string
  dialogSubtitle?: string
  clearLabel?: string
  emptyText?: string
  blocked?: Record<string, string>
  summary?: string
  hint?: string
  fallbackIcon?: string
  elevated?: boolean
}>()

const emit = defineEmits<{ (event: 'select', item: InventoryItem | null): void }>()

const open = ref(false)
// 没选东西时副标题给提示，不重复标题本身。
const subtitle = computed(() => props.summary || (props.selected ? '' : props.hint || ''))
</script>

<template>
  <div class="item-picker">
    <span class="ui-label">{{ label }}</span>
    <button class="picker-trigger" :class="{ assigned: Boolean(selected) }" @click="open = true">
      <span class="trigger-icon"><GameIcon :name="selected?.icon || fallbackIcon" :size="19" /></span>
      <span class="trigger-copy">
        <strong>{{ selected?.name || placeholder }}</strong>
        <small v-if="subtitle">{{ subtitle }}</small>
      </span>
      <ChevronRight :size="16" class="picker-caret" />
    </button>

    <ItemPickerDialog
      :open="open"
      :title="dialogTitle"
      :subtitle="dialogSubtitle"
      :items="items"
      :selected-key="selected?.inventory_key"
      :clear-label="clearLabel"
      :empty-text="emptyText"
      :blocked="blocked"
      :elevated="elevated"
      @select="(item) => emit('select', item)"
      @close="open = false"
    >
      <template #meta="{ item }"><slot name="meta" :item="item" /></template>
    </ItemPickerDialog>
  </div>
</template>

<style scoped>
.item-picker { display: grid; gap: 5px; min-width: 0; }
.picker-trigger {
  width: 100%;
  min-height: 46px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 9px;
  padding: 7px 10px;
  text-align: left;
  color: #8c998f;
  border: 1px dashed #ffffff14;
  border-radius: 10px;
  background: #0d141086;
  cursor: pointer;
}
.picker-trigger.assigned { color: #d9e2d6; border-style: solid; border-color: #8ead7130; background: #8ead710b; }
.trigger-icon { width: 30px; height: 30px; display: grid; place-items: center; color: var(--gold); border-radius: 10px 3px 10px 3px; background: #d7ad5812; }
.picker-trigger:not(.assigned) .trigger-icon { color: #7b867d; background: #ffffff07; }
.trigger-copy { display: grid; gap: 2px; min-width: 0; }
.trigger-copy strong { overflow: hidden; font-size: var(--font-copy); font-weight: 600; white-space: nowrap; text-overflow: ellipsis; }
.trigger-copy small { overflow: hidden; color: #7f8c81; font-size: var(--font-caption); white-space: nowrap; text-overflow: ellipsis; }
.picker-caret { color: #7b867d; }
</style>
