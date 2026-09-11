<script setup lang="ts">
import { computed } from 'vue'
import { TriangleAlert } from 'lucide-vue-next'

import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const request = computed(() => ui.confirmRequest)
</script>

<template>
  <Transition name="toast">
    <div v-if="request" class="modal-backdrop" @click.self="ui.settleConfirm(false)">
      <section class="confirm-card" :class="{ danger: request.tone === 'danger' }">
        <span class="confirm-mark"><TriangleAlert :size="21" /></span>
        <h2>{{ request.title }}</h2>
        <p v-if="request.description">{{ request.description }}</p>
        <div class="confirm-actions">
          <button class="secondary-button" @click="ui.settleConfirm(false)">{{ request.cancelLabel || '取消' }}</button>
          <button class="primary-button" @click="ui.settleConfirm(true)">{{ request.confirmLabel || '确认' }}</button>
        </div>
      </section>
    </div>
  </Transition>
</template>

<style scoped>
.modal-backdrop { z-index: 90; }
.confirm-card { width: min(400px, 100%); padding: 26px; text-align: center; border: 1px solid var(--line); border-radius: 24px 8px 24px 8px; background: #1a251e; box-shadow: 0 35px 100px #0008; }
.confirm-mark { width: 46px; height: 46px; display: grid; place-items: center; margin: 0 auto 14px; color: var(--gold); border-radius: 15px 5px; background: #d7ad5814; }
.confirm-card.danger .confirm-mark { color: var(--danger); background: #e38b7b14; }
.confirm-card h2 { margin: 0; font: 700 19px Georgia, 'Noto Serif SC', serif; }
.confirm-card p { margin: 10px 0 0; color: #9aa59c; font-size: 13px; line-height: 1.7; }
.confirm-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; margin-top: 22px; }
.confirm-card.danger .primary-button { color: #2a1a16; background: #e0a094; }
</style>
