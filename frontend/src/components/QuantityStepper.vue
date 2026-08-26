<script setup lang="ts">
import { computed } from 'vue'
import { Minus, Plus } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{ modelValue: number; min?: number; max: number; disabled?: boolean }>(),
  { min: 1, disabled: false },
)

const emit = defineEmits<{ (event: 'update:modelValue', value: number): void }>()

const clamped = computed(() => clamp(props.modelValue))

function clamp(value: number) {
  if (!Number.isFinite(value)) return props.min
  return Math.min(props.max, Math.max(props.min, Math.floor(value)))
}

function step(delta: number) {
  emit('update:modelValue', clamp(clamped.value + delta))
}

function onInput(event: Event) {
  emit('update:modelValue', clamp(Number((event.target as HTMLInputElement).value)))
}
</script>

<template>
  <div class="quantity-stepper" :class="{ disabled }">
    <button type="button" aria-label="减少" :disabled="disabled || clamped <= min" @click="step(-1)"><Minus :size="14" /></button>
    <input
      :value="clamped"
      type="number"
      inputmode="numeric"
      :min="min"
      :max="max"
      :disabled="disabled"
      @input="onInput"
      @blur="onInput"
    />
    <button type="button" aria-label="增加" :disabled="disabled || clamped >= max" @click="step(1)"><Plus :size="14" /></button>
  </div>
</template>

<style scoped>
.quantity-stepper {
  display: flex;
  align-items: center;
  height: 32px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: #0f1712;
}
.quantity-stepper.disabled { opacity: .5; }
.quantity-stepper button {
  width: 28px;
  height: 100%;
  display: grid;
  place-items: center;
  color: #9aa59c;
  border: 0;
  background: transparent;
  cursor: pointer;
}
.quantity-stepper button:disabled { color: #4d564e; cursor: default; }
.quantity-stepper input {
  width: 42px;
  height: 100%;
  color: var(--cream);
  border: 0;
  border-left: 1px solid var(--line);
  border-right: 1px solid var(--line);
  background: transparent;
  font-size: 13px;
  font-weight: 700;
  text-align: center;
  outline: none;
  -moz-appearance: textfield;
  appearance: textfield;
}
.quantity-stepper input::-webkit-outer-spin-button,
.quantity-stepper input::-webkit-inner-spin-button { margin: 0; -webkit-appearance: none; appearance: none; }
</style>
