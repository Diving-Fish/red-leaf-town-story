<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import ActionButton from '@/components/ActionButton.vue'
import GameIcon from '@/components/GameIcon.vue'
import ModalSheet from '@/components/ModalSheet.vue'
import QualityTag from '@/components/QualityTag.vue'

const props = defineProps<{
  open: boolean
  title: string
  subtitle?: string
  icon: string
  speciesName: string
  quality?: number | null
  actionKey: string
  confirmLabel: string
  lines: Array<{ label: string; value: string }>
}>()

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'confirm', nickname: string): void
}>()

const NAME_LIMIT = 12

const nickname = ref('')

watch(
  () => props.open,
  (open) => {
    if (open) nickname.value = ''
  },
)

const trimmed = computed(() => nickname.value.trim())
const tooLong = computed(() => [...trimmed.value].length > NAME_LIMIT)
const displayName = computed(() => trimmed.value || props.speciesName)
</script>

<template>
  <ModalSheet :open="open" :title="title" :subtitle="subtitle" @close="emit('close')">
    <div class="name-body">
      <div class="name-preview">
        <span class="name-icon"><GameIcon :name="icon" :size="26" /></span>
        <div>
          <strong>{{ displayName }}</strong>
          <small>
            {{ speciesName }}
            <QualityTag v-if="quality" :quality="quality" plain />
          </small>
        </div>
      </div>

      <label class="name-field">
        <span>起个名字</span>
        <input
          v-model="nickname"
          type="text"
          :maxlength="NAME_LIMIT * 2"
          placeholder="留空则用物种名"
          @keyup.enter="!tooLong && emit('confirm', trimmed)"
        >
      </label>
      <p v-if="tooLong" class="name-error">名字最多 {{ NAME_LIMIT }} 个字</p>

      <dl class="name-lines">
        <div v-for="line in lines" :key="line.label">
          <dt>{{ line.label }}</dt>
          <dd>{{ line.value }}</dd>
        </div>
      </dl>
    </div>

    <template #footer>
      <ActionButton
        :action-key="actionKey"
        :disabled="tooLong"
        :reason="tooLong ? `名字最多 ${NAME_LIMIT} 个字` : undefined"
        @click="emit('confirm', trimmed)"
      >{{ confirmLabel }}</ActionButton>
    </template>
  </ModalSheet>
</template>

<style scoped>
.name-body { display: flex; flex-direction: column; gap: 14px; }

.name-preview { display: flex; align-items: center; gap: 11px; padding: 12px; border: 1px solid var(--line); border-radius: 13px; background: #ffffff05; }
.name-icon { display: grid; place-items: center; width: 44px; height: 44px; border: 1px solid var(--line); border-radius: 14px 4px 14px 4px; background: var(--surface); }
.name-preview strong { font-size: 15px; }
.name-preview small { display: flex; align-items: center; gap: 6px; margin-top: 3px; color: #7d887f; font-size: 12px; }

.name-field { display: flex; flex-direction: column; gap: 6px; }
.name-field span { color: #849087; font-size: 12px; }
.name-field input { height: 38px; padding: 0 12px; color: inherit; border: 1px solid var(--line); border-radius: 10px; background: #ffffff06; font-size: 14px; }
.name-field input:focus-visible { outline: none; border-color: color-mix(in srgb, var(--leaf-bright) 45%, transparent); }
.name-error { margin: -8px 0 0; color: #cf8c80; font-size: 12px; }

.name-lines { display: grid; gap: 7px; margin: 0; }
.name-lines div { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.name-lines dt { color: #849087; font-size: 12px; }
.name-lines dd { margin: 0; font-size: 13px; }
</style>
