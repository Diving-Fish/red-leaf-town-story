<script lang="ts">
const stack: symbol[] = []

function pushSheet(id: symbol) {
  stack.push(id)
  if (stack.length === 1) document.body.style.overflow = 'hidden'
}

function popSheet(id: symbol) {
  const index = stack.indexOf(id)
  if (index >= 0) stack.splice(index, 1)
  if (!stack.length) document.body.style.overflow = ''
}

function isTopSheet(id: symbol) {
  return stack[stack.length - 1] === id
}
</script>

<script setup lang="ts">
import { onBeforeUnmount, watch } from 'vue'
import { X } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{ open: boolean; title: string; subtitle?: string; elevated?: boolean }>(),
  { elevated: false },
)

const emit = defineEmits<{ (event: 'close'): void }>()
const id = Symbol('modal-sheet')

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && isTopSheet(id)) emit('close')
}

function bindSheet() {
  pushSheet(id)
  document.addEventListener('keydown', onKeydown)
}

function unbindSheet() {
  popSheet(id)
  document.removeEventListener('keydown', onKeydown)
}

watch(
  () => props.open,
  (value) => (value ? bindSheet() : unbindSheet()),
  { immediate: true },
)

onBeforeUnmount(unbindSheet)
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="open" class="sheet-backdrop" :class="{ elevated }" @click.self="emit('close')">
        <section class="sheet-panel" role="dialog" aria-modal="true">
          <header class="sheet-heading">
            <div>
              <h2>{{ title }}</h2>
              <small v-if="subtitle">{{ subtitle }}</small>
            </div>
            <button class="icon-button sheet-close" aria-label="关闭" @click="emit('close')"><X :size="19" /></button>
          </header>

          <div v-if="$slots.toolbar" class="sheet-toolbar"><slot name="toolbar" /></div>

          <div class="sheet-body"><slot /></div>

          <footer v-if="$slots.footer" class="sheet-footer"><slot name="footer" /></footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.sheet-backdrop {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(5, 8, 6, .72);
  backdrop-filter: blur(5px);
}
.sheet-backdrop.elevated { z-index: 80; }
.sheet-panel {
  display: flex;
  flex-direction: column;
  width: min(460px, 100%);
  max-height: min(640px, calc(100dvh - 48px));
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 24px 8px 24px 8px;
  background: #1a251e;
  box-shadow: 0 35px 100px #0008;
}
.sheet-heading {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 18px 18px 13px;
  border-bottom: 1px solid var(--line);
}
.sheet-heading h2 { margin: 0; font: 700 17px Georgia, 'Noto Serif SC', serif; }
.sheet-heading small { display: block; margin-top: 4px; color: #7f8a80; }
.sheet-close { width: 34px; height: 34px; display: grid; place-items: center; color: #9aa59c; border: 1px solid var(--line); border-radius: 10px; background: #ffffff05; cursor: pointer; }
.sheet-toolbar { padding: 12px 16px; border-bottom: 1px solid var(--line); background: #ffffff03; }
.sheet-body { flex: 1; min-height: 0; overflow: auto; padding: 12px 14px; }
.sheet-footer { padding: 13px 16px calc(13px + env(safe-area-inset-bottom)); border-top: 1px solid var(--line); background: #16201a; }
.sheet-enter-active, .sheet-leave-active { transition: opacity .18s ease; }
.sheet-enter-active .sheet-panel, .sheet-leave-active .sheet-panel { transition: transform .2s ease; }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet-panel, .sheet-leave-to .sheet-panel { transform: translateY(14px) scale(.98); }
@media (max-width: 620px) {
  .sheet-backdrop { place-items: end stretch; padding: 0; }
  .sheet-panel { width: 100%; max-height: 86dvh; border-radius: 20px 20px 0 0; border-bottom: 0; }
  .sheet-enter-from .sheet-panel, .sheet-leave-to .sheet-panel { transform: translateY(100%); }
}
</style>
