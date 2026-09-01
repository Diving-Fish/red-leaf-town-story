<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, PackageOpen, Search } from 'lucide-vue-next'

import GameIcon from '@/components/GameIcon.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import QualityTag from '@/components/QualityTag.vue'
import type { InventoryItem } from '@/types'

/** 从仓库里挑一件物品。装备槽、战斗道具共用这一个选择器。 */
const props = defineProps<{
  open: boolean
  title: string
  subtitle?: string
  items: InventoryItem[]
  /** 当前选中的 inventory_key；留空表示没有选。 */
  selectedKey?: string
  clearLabel?: string
  emptyText?: string
  /** 不可选的条目与原因，例如同一件装备已经给了别人。 */
  blocked?: Record<string, string>
  elevated?: boolean
  searchable?: boolean
}>()

const emit = defineEmits<{
  (event: 'select', item: InventoryItem | null): void
  (event: 'close'): void
}>()

const keyword = ref('')

watch(
  () => props.open,
  (open) => {
    if (open) keyword.value = ''
  },
)

const showSearch = computed(() => props.searchable !== false && props.items.length > 6)
const visible = computed(() => {
  const text = keyword.value.trim().toLowerCase()
  if (!text) return props.items
  return props.items.filter((item) => item.name.toLowerCase().includes(text))
})

function reason(item: InventoryItem) {
  return props.blocked?.[item.inventory_key] || ''
}

function choose(item: InventoryItem | null) {
  if (item && reason(item)) return
  emit('select', item)
  emit('close')
}
</script>

<template>
  <ModalSheet :open="open" :title="title" :subtitle="subtitle" :elevated="elevated" @close="emit('close')">
    <template v-if="showSearch" #toolbar>
      <label class="search-field">
        <Search :size="16" />
        <input v-model="keyword" type="search" placeholder="搜索物品名字" />
      </label>
    </template>

    <div class="option-list">
      <button v-if="clearLabel" class="item-option bare" @click="choose(null)">
        <span class="option-mark"><PackageOpen :size="18" /></span>
        <span class="option-copy"><strong>{{ clearLabel }}</strong></span>
        <Check v-if="!selectedKey" :size="16" class="option-check" />
      </button>

      <button
        v-for="item in visible"
        :key="item.inventory_key"
        class="item-option"
        :class="{ current: item.inventory_key === selectedKey }"
        :disabled="Boolean(reason(item))"
        :title="reason(item) || undefined"
        @click="choose(item)"
      >
        <span class="option-icon"><GameIcon :name="item.icon" :size="22" /></span>
        <span class="option-copy">
          <strong>
            {{ item.name }}
            <QualityTag v-if="item.quality" :quality="item.quality" :name="item.quality_name" plain />
          </strong>
          <small><slot name="meta" :item="item">仓库中有 {{ item.quantity }} 个</slot></small>
          <em v-if="reason(item)">{{ reason(item) }}</em>
        </span>
        <Check v-if="item.inventory_key === selectedKey" :size="16" class="option-check" />
      </button>

      <p v-if="!visible.length" class="option-empty">{{ emptyText || '仓库里没有可用的物品' }}</p>
    </div>
  </ModalSheet>
</template>

<style scoped>
.search-field { display: flex; align-items: center; gap: 8px; padding: 0 11px; color: #7f8a80; border: 1px solid var(--line); border-radius: 10px; background: #0f1712; }
.search-field input { flex: 1; min-width: 0; height: 38px; color: var(--cream); border: 0; background: transparent; outline: none; }
.option-list { display: grid; gap: 6px; }
.item-option {
  width: 100%;
  min-height: 56px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 11px;
  padding: 9px 11px;
  text-align: left;
  color: inherit;
  border: 1px solid var(--line);
  border-radius: 13px 4px 13px 4px;
  background: #ffffff05;
  cursor: pointer;
  transition: border-color .16s ease, background .16s ease;
}
.item-option:hover:not(:disabled), .item-option:focus-visible { border-color: color-mix(in srgb, var(--leaf-bright) 38%, transparent); background: #a8c9850f; }
.item-option.current { border-color: color-mix(in srgb, var(--leaf-bright) 46%, transparent); background: #a8c9851a; }
.item-option:disabled { opacity: .5; cursor: not-allowed; }
.option-icon, .option-mark { width: 40px; height: 40px; display: grid; place-items: center; color: var(--gold); border-radius: 12px 4px 12px 4px; background: #d7ad5814; }
.option-mark { color: #9aa59c; background: #ffffff08; }
.option-copy { display: grid; gap: 3px; min-width: 0; }
.option-copy strong { display: inline-flex; align-items: center; gap: 6px; font-size: var(--font-body); }
.option-copy small { color: #849087; font-size: var(--font-caption); line-height: 1.5; }
.option-copy em { color: var(--danger); font-size: var(--font-caption); font-style: normal; }
.option-check { color: var(--leaf-bright); }
.option-empty { margin: 18px 0; color: #78857b; font-size: var(--font-copy); text-align: center; }
</style>
