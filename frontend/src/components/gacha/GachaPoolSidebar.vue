<script setup lang="ts">
import GachaPoolCard, { type GachaPoolSummary } from '@/components/gacha/GachaPoolCard.vue'

withDefaults(defineProps<{ pools: GachaPoolSummary[]; activeId?: string | null; heading?: string }>(), {
  heading: '招募池',
})
defineEmits<{ (event: 'select', id: string): void }>()
</script>

<template>
  <aside class="pool-sidebar">
    <p class="pool-sidebar-heading">{{ heading }}</p>
    <div class="pool-sidebar-list">
      <GachaPoolCard
        v-for="pool in pools"
        :key="pool.id"
        :pool="pool"
        :active="pool.id === activeId"
        @select="$emit('select', pool.id)"
      />
    </div>
    <div v-if="$slots.footer" class="pool-sidebar-footer"><slot name="footer" /></div>
  </aside>
</template>

<style scoped>
.pool-sidebar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 19px 6px;
  background: var(--surface);
}
.pool-sidebar-heading { margin: 2px 4px 0; color: #77837a; font-size: 12px; font-weight: 800; letter-spacing: .12em; }
.pool-sidebar-list { display: grid; gap: 8px; }
.pool-sidebar-footer { margin-top: 4px; padding-top: 12px; border-top: 1px solid var(--line); }

@media (max-width: 900px) {
  .pool-sidebar { flex-direction: row; align-items: center; overflow-x: auto; }
  .pool-sidebar-heading { display: none; }
  .pool-sidebar-list { grid-auto-flow: column; grid-auto-columns: minmax(220px, 1fr); }
  .pool-sidebar-footer { display: none; }
}
</style>
