<script setup lang="ts">
import { computed } from 'vue'

import { useGameStore } from '@/stores/game'

const props = withDefaults(defineProps<{
  modelValue: string
  industry: string
  timing?: 'start' | 'active'
}>(), { timing: 'start' })
const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>()
const game = useGameStore()

const options = computed(() => (game.state?.task_items || []).filter((item) => (
  item.timing === props.timing
  && (!item.eligible_industries.length || item.eligible_industries.includes(props.industry))
)))
</script>

<template>
  <label v-if="options.length" class="task-item-select" @click.stop>
    <span>特殊道具</span>
    <select :value="modelValue" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
      <option value="">不使用</option>
      <option v-for="item in options" :key="item.id" :value="item.id">
        {{ item.name }} ×{{ item.quantity }}
      </option>
    </select>
  </label>
</template>

<style scoped>
.task-item-select { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 7px; margin-top: 7px; color: #78847b; font-size: 12px; }
.task-item-select select { min-width: 0; height: 29px; padding: 0 8px; color: #bdc8bd; font-size: 12px; border: 1px solid #ffffff12; border-radius: 7px; background: #151d18; }
</style>
