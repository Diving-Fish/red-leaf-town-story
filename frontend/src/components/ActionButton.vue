<script setup lang="ts">
import { computed } from 'vue'

import { useGameStore } from '@/stores/game'

const props = withDefaults(
  defineProps<{
    actionKey: string
    group?: string
    disabled?: boolean
    reason?: string
    variant?: 'primary' | 'secondary' | 'text' | 'bare'
  }>(),
  { variant: 'primary' },
)

const emit = defineEmits<{ (event: 'click'): void }>()
const game = useGameStore()

const pending = computed(() => game.isPending(props.actionKey))
const blocked = computed(() => Boolean(props.disabled) || pending.value || (props.group ? game.isPendingPrefix(props.group) : false))
</script>

<template>
  <button
    :class="[variant === 'bare' ? null : `${variant}-button`, { 'is-pending': pending }]"
    :disabled="blocked"
    :title="reason || undefined"
    @click="emit('click')"
  >
    <slot />
  </button>
</template>
