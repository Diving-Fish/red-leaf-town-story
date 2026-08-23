<script setup lang="ts">
import { ChevronDown, LockKeyhole } from 'lucide-vue-next'

import ItemTile from '@/components/ItemTile.vue'
import QualityTag from '@/components/QualityTag.vue'
import { qualityClass } from '@/lib/quality'

defineProps<{
  icon?: string
  name: string
  quality?: number | null
  qualityName?: string | null
  meta?: string
  amount?: string | number
  amountUnit?: string
  locked?: boolean
  expandable?: boolean
  expanded?: boolean
  nested?: boolean
}>()

const emit = defineEmits<{ (event: 'toggle'): void }>()
</script>

<template>
  <article
    class="market-item"
    :class="[qualityClass(quality), { locked, nested, expandable, expanded }]"
    :role="expandable ? 'button' : undefined"
    :tabindex="expandable ? 0 : undefined"
    :aria-expanded="expandable ? expanded : undefined"
    @click="expandable && emit('toggle')"
    @keydown.enter.prevent="expandable && emit('toggle')"
    @keydown.space.prevent="expandable && emit('toggle')"
  >
    <ItemTile :icon="icon" :size="nested ? 34 : 46" tone="gold" />
    <div class="market-copy">
      <h3>{{ name }} <QualityTag :quality="quality" :name="qualityName" /></h3>
      <small v-if="meta"><LockKeyhole v-if="locked" :size="13" />{{ meta }}</small>
    </div>
    <strong v-if="amount !== undefined" class="market-amount">
      {{ amount }}<small v-if="amountUnit"> {{ amountUnit }}</small>
    </strong>
    <ChevronDown v-if="expandable" class="market-caret" :size="17" />
    <div v-if="$slots.actions" class="market-actions" @click.stop><slot name="actions" /></div>
  </article>
</template>

<style scoped>
.market-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 13px;
  padding: 13px 15px;
  border: 1px solid var(--line);
  border-radius: 15px 5px 15px 5px;
  background: var(--surface);
}
.market-item.expandable { grid-template-columns: auto minmax(0, 1fr) auto auto; cursor: pointer; }
.market-item.expandable:hover { border-color: rgba(236, 221, 187, .2); }
.market-item.expanded { border-bottom-left-radius: 4px; border-bottom-right-radius: 0; }
.market-item.nested { padding: 9px 13px; border-radius: 11px 4px 11px 4px; background: #ffffff05; }
.market-item.nested .market-copy h3 { font-size: 14px; }
.market-item.locked { filter: saturate(.35); opacity: .62; }
.market-item.quality-2 { border-color: color-mix(in srgb, var(--quality-2) 32%, transparent); }
.market-item.quality-3 { border-color: color-mix(in srgb, var(--quality-3) 38%, transparent); }
.market-item.quality-4 { border-color: color-mix(in srgb, var(--quality-4) 42%, transparent); }
.market-item.quality-5 { border-color: color-mix(in srgb, var(--quality-5) 50%, transparent); box-shadow: inset 0 0 22px #d7a8430a; }
.market-copy { min-width: 0; }
.market-copy h3 { display: flex; align-items: center; gap: 6px; margin: 0; font-size: 15px; }
.market-copy small { display: flex; align-items: center; gap: 5px; margin-top: 4px; color: #7f8a81; font-size: 12px; }
.market-amount { color: var(--gold); white-space: nowrap; }
.market-amount small { color: #778279; font-weight: 400; }
.market-caret { color: #7b867d; transition: transform .18s ease; }
.market-item.expanded .market-caret { transform: rotate(180deg); }
.market-actions { grid-column: 2 / -1; display: flex; align-items: center; justify-content: flex-end; gap: 6px; }
.market-actions :deep(.primary-button) { min-height: 32px; }
</style>
