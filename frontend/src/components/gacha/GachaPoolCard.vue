<script setup lang="ts">
import { Check, DoorOpen, Lock } from 'lucide-vue-next'

export interface GachaPoolSummary {
  id: string
  title: string
  subtitle: string
  unlocked: boolean
  fiveStarRate?: string
}

defineProps<{ pool: GachaPoolSummary; active: boolean }>()
defineEmits<{ (event: 'select'): void }>()
</script>

<template>
  <button type="button" class="pool-card" :class="{ active }" :disabled="!pool.unlocked" @click="$emit('select')">
    <span class="pool-card-icon"><DoorOpen v-if="pool.unlocked" :size="18" /><Lock v-else :size="16" /></span>
    <span class="pool-card-copy">
      <strong>{{ pool.title }}</strong>
      <small>{{ pool.unlocked ? pool.subtitle : '尚未开放' }}</small>
    </span>
    <span v-if="pool.fiveStarRate && pool.unlocked" class="pool-card-rate">{{ pool.fiveStarRate }}</span>
    <span v-if="active" class="pool-card-active"><Check :size="13" /></span>
  </button>
</template>

<style scoped>
.pool-card {
  position: relative;
  width: 100%;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 11px;
  padding: 12px;
  text-align: left;
  border: 1px solid var(--line);
  border-radius: 15px 5px;
  background: #ffffff03;
  cursor: pointer;
  transition: border-color .18s, background .18s;
}
.pool-card:disabled { cursor: not-allowed; opacity: .55; }
.pool-card:not(:disabled):hover { background: #ffffff07; }
.pool-card.active {
  border-color: color-mix(in srgb, var(--gold) 55%, var(--line));
  background: linear-gradient(120deg, color-mix(in srgb, var(--gold) 14%, transparent), transparent);
  box-shadow: inset 3px 0 var(--gold);
}
.pool-card-icon {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  color: var(--gold);
  border-radius: 11px 4px;
  background: color-mix(in srgb, var(--gold) 14%, transparent);
}
.pool-card-copy { min-width: 0; }
.pool-card-copy strong { display: block; font-size: 13px; }
.pool-card-copy small { display: block; margin-top: 2px; color: #7c877e; font-size: 11px; }
.pool-card-rate { color: #8a9589; font-size: 11px; }
.pool-card-active {
  position: absolute;
  right: -1px;
  top: -1px;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  color: #241d14;
  border-radius: 0 5px 0 8px;
  background: var(--gold);
}
</style>
