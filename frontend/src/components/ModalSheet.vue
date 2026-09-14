<script lang="ts">
const stack: symbol[] = []
let previousOverflow = ''

function pushSheet(id: symbol) {
  if (stack.includes(id)) return
  if (!stack.length) {
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
  }
  stack.push(id)
}

function popSheet(id: symbol) {
  const index = stack.indexOf(id)
  if (index < 0) return
  stack.splice(index, 1)
  if (!stack.length) document.body.style.overflow = previousOverflow
}

function isTopSheet(id: symbol) {
  return stack[stack.length - 1] === id
}
</script>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { X } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    subtitle?: string
    elevated?: boolean
    presentation?: 'sheet' | 'dialog'
    closeOnBackdrop?: boolean
    size?: 'default' | 'wide'
  }>(),
  { elevated: false, presentation: 'sheet', closeOnBackdrop: true },
)

const emit = defineEmits<{ (event: 'close'): void }>()
const id = Symbol('modal-sheet')
const titleId = useId()
const panel = ref<HTMLElement>()
const closeButton = ref<HTMLButtonElement>()
let returnFocus: HTMLElement | null = null

function onKeydown(event: KeyboardEvent) {
  if (!isTopSheet(id)) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  }
  if (event.key !== 'Tab' || !panel.value) return
  const focusable = Array.from(panel.value.querySelectorAll<HTMLElement>(
    'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
  )).filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0)
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const active = document.activeElement
  if (!panel.value.contains(active) || (event.shiftKey ? active === first : active === last)) {
    event.preventDefault()
    ;(event.shiftKey ? last : first)?.focus()
  }
}

async function bindSheet() {
  returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  pushSheet(id)
  document.addEventListener('keydown', onKeydown)
  await nextTick()
  if (props.open && isTopSheet(id)) closeButton.value?.focus()
}

function unbindSheet() {
  const wasTop = isTopSheet(id)
  popSheet(id)
  document.removeEventListener('keydown', onKeydown)
  if (wasTop && returnFocus?.isConnected) returnFocus.focus()
  returnFocus = null
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
      <div v-if="open" class="sheet-backdrop" :class="{ elevated, 'centered-dialog': presentation === 'dialog' }" @click.self="closeOnBackdrop && emit('close')">
        <section ref="panel" class="sheet-panel" :class="{ 'sheet-wide': size === 'wide' }" role="dialog" aria-modal="true" :aria-labelledby="titleId">
          <header class="sheet-heading">
            <div class="sheet-title-group">
              <slot name="icon" />
              <div class="sheet-title-copy">
              <h2 :id="titleId">{{ title }}</h2>
              <small v-if="subtitle">{{ subtitle }}</small>
              </div>
            </div>
            <button ref="closeButton" class="icon-button sheet-close" aria-label="关闭" @click="emit('close')"><X :size="19" /></button>
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
.sheet-panel.sheet-wide { width: min(860px, 100%); max-height: min(860px, calc(100dvh - 48px)); }
.sheet-heading {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 18px 18px 13px;
  border-bottom: 1px solid var(--line);
}
.sheet-heading h2 { margin: 0; font: 700 17px Georgia, 'Noto Serif SC', serif; }
.sheet-heading small { display: block; margin-top: 4px; color: #7f8a80; }
.sheet-title-group { display: flex; align-items: center; gap: 12px; min-width: 0; }
.sheet-title-copy { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.sheet-title-group :slotted(*) { flex-shrink: 0; }
.sheet-heading, .sheet-toolbar, .sheet-footer { flex-shrink: 0; }
.sheet-close { width: 44px; height: 44px; display: grid; place-items: center; color: #9aa59c; border: 1px solid var(--line); border-radius: 10px; background: #ffffff05; cursor: pointer; }
.sheet-close:focus-visible { outline: 2px solid var(--leaf-bright); outline-offset: 2px; }
.sheet-toolbar { padding: 12px 16px; border-bottom: 1px solid var(--line); background: #ffffff03; }
.sheet-body { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; padding: 12px 14px; }
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
.sheet-backdrop.centered-dialog { place-items: center; padding: max(16px, env(safe-area-inset-top)) max(16px, env(safe-area-inset-right)) max(16px, env(safe-area-inset-bottom)) max(16px, env(safe-area-inset-left)); }
.centered-dialog .sheet-panel { width: min(460px, 100%); max-height: min(720px, calc(100dvh - 32px - env(safe-area-inset-top) - env(safe-area-inset-bottom))); border: 1px solid #a8c98530; border-radius: 22px; background: var(--surface); }
.centered-dialog .sheet-heading h2 { font-size: 19px; font-weight: 600; font-family: inherit; }
.centered-dialog .sheet-body { padding: 20px; }
.centered-dialog .sheet-footer { padding-bottom: 13px; }
.sheet-enter-from.centered-dialog .sheet-panel, .sheet-leave-to.centered-dialog .sheet-panel { transform: translateY(14px) scale(.98); }
@media (prefers-reduced-motion: reduce) { .sheet-enter-active, .sheet-leave-active, .sheet-enter-active .sheet-panel, .sheet-leave-active .sheet-panel { transition: none; } }
</style>
